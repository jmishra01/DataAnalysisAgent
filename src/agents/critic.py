import re

from ..errors import LLMError
from ..prompts import CRITIC_SYSTEM_PROMPT
from ..schemas import AnalysisPlan, CritiqueResult
from ..tools.code_executor import UnsafeCodeError, validate_analysis_code
from ..tools.csv_profiler import CsvProfile
from .agent import SpecializedAgent


class CriticAgent(SpecializedAgent):
    name = "critic_agent"

    def review(self, plan: AnalysisPlan, profile: CsvProfile) -> CritiqueResult:
        self.reset_diagnostics()
        deterministic = self._deterministic_review(plan, profile)
        if not deterministic.approved:
            return deterministic
        if self.llm.available:
            prompt = (
                f"<dataset_profile>\n{profile.to_prompt_text(max_sample_rows=0)}"
                f"\n</dataset_profile>\n"
                f"Goal: {plan.goal}\nAssumptions: {plan.assumptions}\n"
                f"Expected output: {plan.expected_output}\n<generated_code>\n{plan.code}\n</generated_code>"
            )
            try:
                model_review = self.llm.structured(
                    CRITIC_SYSTEM_PROMPT,
                    prompt,
                    CritiqueResult,
                )
                return self._apply_profile_evidence(model_review, profile)
            except LLMError as error:
                self._fallback_after(error)
        return deterministic

    @staticmethod
    def _deterministic_review(plan: AnalysisPlan, profile: CsvProfile) -> CritiqueResult:
        issues: list[str] = []
        mentioned = set(re.findall(r"\[['\"]([^'\"]+)['\"]\]", plan.code))
        unknown = sorted(mentioned.difference(profile.columns))
        if unknown:
            issues.append(f"Unknown CSV columns: {', '.join(unknown)}.")
        if "pd.read_csv(CSV_PATH)" not in plan.code:
            issues.append("Code does not read from the approved CSV_PATH variable.")
        try:
            validate_analysis_code(plan.code)
        except UnsafeCodeError as error:
            issues.append(str(error))
        return CritiqueResult(
            approved=not issues,
            issues=issues,
            revision_guidance=" ".join(issues),
        )

    @staticmethod
    def _apply_profile_evidence(
        review: CritiqueResult,
        profile: CsvProfile,
    ) -> CritiqueResult:
        """Move objections contradicted by observed profile facts into warnings."""
        blocking_issues: list[str] = []
        verified_warnings = list(review.warnings)
        for issue in review.issues:
            if CriticAgent._is_verified_by_profile(issue, profile):
                verified_warnings.append(issue)
            else:
                blocking_issues.append(issue)

        return CritiqueResult(
            approved=not blocking_issues,
            issues=blocking_issues,
            warnings=verified_warnings,
            revision_guidance=(
                review.revision_guidance if blocking_issues else ""
            ),
        )

    @staticmethod
    def _is_verified_by_profile(issue: str, profile: CsvProfile) -> bool:
        normalized_issue = issue.lower()
        mentioned_columns = [
            column
            for column in profile.columns
            if re.search(rf"\b{re.escape(column)}\b", issue, flags=re.IGNORECASE)
        ]
        if not mentioned_columns:
            return False

        for column in mentioned_columns:
            checks_missing_values = "missing" in normalized_issue or "null" in normalized_issue
            if checks_missing_values and profile.null_counts[column] != 0:
                return False

            checks_integer_type = "integer" in normalized_issue
            if checks_integer_type and "int" not in profile.dtypes[column].lower():
                return False

            checks_non_negative = "non-negative" in normalized_issue or "negative" in normalized_issue
            if checks_non_negative:
                summary = profile.numeric_summary.get(column)
                if not summary or summary["min"] < 0:
                    return False

        return any(
            marker in normalized_issue
            for marker in ("missing", "null", "integer", "non-negative", "negative")
        )
