from ..context import PromptContext
from ..errors import LLMError
from ..prompts import PLANNER_SYSTEM_PROMPT
from ..schemas import AnalysisPlan
from ..tools.csv_profiler import CsvProfile
from .agent import SpecializedAgent


class PlannerAgent(SpecializedAgent):
    name = "planner_agent"

    def plan(
        self,
        request: str,
        profile: CsvProfile,
        context: PromptContext,
        revision_guidance: str = "",
    ) -> AnalysisPlan:
        self.reset_diagnostics()
        if self.llm.available:
            prompt = f"Resolved request: {request}\n\n{context.text}"
            if revision_guidance:
                prompt += f"\n\n<critic_revision_guidance>\n{revision_guidance}\n</critic_revision_guidance>"
            try:
                return self.llm.structured(
                    PLANNER_SYSTEM_PROMPT,
                    prompt,
                    AnalysisPlan,
                )
            except LLMError as error:
                self._fallback_after(error)
        return self._fallback(request, profile)

    @staticmethod
    def _fallback(question: str, profile: CsvProfile) -> AnalysisPlan:
        numeric = list(profile.numeric_summary)
        categorical = [name for name in profile.columns if name not in numeric]
        lower_question = question.lower()
        normalized_question = "".join(
            character for character in lower_question if character.isalnum()
        )
        requested_metrics = [
            column
            for column in numeric
            if PlannerAgent._normalize(column) in normalized_question
        ]
        requested_groups = [
            column
            for column in categorical
            if PlannerAgent._normalize(column) in normalized_question
        ]
        metric = requested_metrics[0] if requested_metrics else (
            "Revenue" if "Revenue" in numeric else (numeric[0] if numeric else None)
        )
        group = requested_groups[-1] if requested_groups else (
            "Category" if "Category" in categorical else (categorical[0] if categorical else None)
        )
        assumptions = ["Used deterministic planning because model planning was unavailable."]

        if any(word in lower_question for word in {"quality", "missing", "null", "duplicate", "clean"}):
            code = """import pandas as pd
df = pd.read_csv(CSV_PATH)
print(f'Rows: {len(df):,}; columns: {len(df.columns)}')
print(f'Duplicate rows: {int(df.duplicated().sum()):,}')
print('\\nMissing values by column:')
print(df.isna().sum().to_string())
print('\\nColumn types:')
print(df.dtypes.to_string())
"""
            return AnalysisPlan(
                goal=question,
                assumptions=assumptions,
                code=code,
                expected_output="Row count, duplicates, missing values, and column types.",
            )

        if any(word in lower_question for word in {"trend", "month", "date"}):
            date_column = next((column for column in profile.columns if "date" in column.lower()), None)
            if date_column and metric:
                code = f"""import pandas as pd
df = pd.read_csv(CSV_PATH)
df[{date_column!r}] = pd.to_datetime(df[{date_column!r}], errors='coerce')
valid = df.dropna(subset=[{date_column!r}])
monthly = valid.groupby(valid[{date_column!r}].dt.to_period('M'))[{metric!r}].sum()
print('Monthly {metric} trend:')
print(monthly.sort_index().round(2).to_string())
"""
                return AnalysisPlan(
                    goal=question,
                    assumptions=assumptions,
                    code=code,
                    expected_output=f"Monthly {metric} trend.",
                )

        if metric and group:
            aggregation = PlannerAgent._requested_aggregation(lower_question)
            if aggregation:
                label, operation = aggregation
                code = f"""import pandas as pd
df = pd.read_csv(CSV_PATH)
summary = df.groupby({group!r})[{metric!r}].{operation}().sort_values(ascending=False)
print('{label} {metric} by {group}:')
print(summary.round(2).to_string())
"""
                return AnalysisPlan(
                    goal=question,
                    assumptions=assumptions,
                    code=code,
                    expected_output=f"{label} {metric} grouped by {group}.",
                )
            code = f"""import pandas as pd
df = pd.read_csv(CSV_PATH)
summary = df.groupby({group!r})[{metric!r}].agg(['sum', 'mean', 'count'])
print('Top groups by {metric}:')
print(summary.sort_values('sum', ascending=False).head(10).round(2).to_string())
"""
            return AnalysisPlan(
                goal=question,
                assumptions=assumptions,
                code=code,
                expected_output=f"{metric} totals, averages, and counts by {group}.",
            )

        code = "import pandas as pd\ndf = pd.read_csv(CSV_PATH)\nprint(df.describe(include='all').to_string())\n"
        return AnalysisPlan(
            goal=question,
            assumptions=assumptions,
            code=code,
            expected_output="Descriptive statistics for all columns.",
        )

    @staticmethod
    def _normalize(value: str) -> str:
        return "".join(character for character in value.lower() if character.isalnum())

    @staticmethod
    def _requested_aggregation(question: str) -> tuple[str, str] | None:
        if any(term in question for term in ("maximum", "highest", "max ")):
            return "Maximum", "max"
        if any(term in question for term in ("minimum", "lowest", "min ")):
            return "Minimum", "min"
        if any(term in question for term in ("average", "mean")):
            return "Average", "mean"
        if any(term in question for term in ("total", "sum")):
            return "Total", "sum"
        return None
