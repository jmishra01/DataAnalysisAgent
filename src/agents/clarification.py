from ..context import PromptContext
from ..errors import LLMError
from ..prompts import CLARIFICATION_SYSTEM_PROMPT
from ..schemas import ClarificationDecision
from ..tools.csv_profiler import CsvProfile
from .agent import SpecializedAgent

_VAGUE_REQUESTS = {"analyze", "analyse", "analyze this", "help", "insights", "overview"}
_ANALYSIS_TERMS = {
    "average",
    "compare",
    "comparison",
    "count",
    "highest",
    "lowest",
    "maximum",
    "mean",
    "minimum",
    "missing",
    "sum",
    "top",
    "total",
    "trend",
}


class ClarificationAgent(SpecializedAgent):
    name = "clarification_agent"

    def decide(
        self,
        question: str,
        profile: CsvProfile,
        context: PromptContext,
    ) -> ClarificationDecision:
        self.reset_diagnostics()
        if self._is_specific(question, profile):
            return ClarificationDecision(
                needs_clarification=False,
                resolved_request=question.strip(),
            )
        if self.llm.available:
            try:
                return self.llm.structured(
                    CLARIFICATION_SYSTEM_PROMPT,
                    context.text,
                    ClarificationDecision,
                )
            except LLMError as error:
                self._fallback_after(error)
        return self._fallback(question, profile)

    @staticmethod
    def _is_specific(question: str, profile: CsvProfile) -> bool:
        normalized_question = "".join(character for character in question.lower() if character.isalnum())
        mentions_column = any(
            "".join(character for character in column.lower() if character.isalnum())
            in normalized_question
            for column in profile.columns
        )
        words = set(question.lower().replace("?", "").split())
        mentions_operation = bool(words.intersection(_ANALYSIS_TERMS)) or " by " in question.lower()
        return mentions_column and mentions_operation

    @staticmethod
    def _fallback(question: str, profile: CsvProfile) -> ClarificationDecision:
        if question.strip().lower() not in _VAGUE_REQUESTS:
            return ClarificationDecision(
                needs_clarification=False,
                resolved_request=question.strip(),
            )
        metrics = ", ".join(list(profile.numeric_summary)[:3]) or "a key metric"
        return ClarificationDecision(
            needs_clarification=True,
            resolved_request=question.strip(),
            questions=[
                "What decision should this analysis support?",
                f"Which metric matters most: {metrics}?",
                "Do you want a comparison, trend, anomaly check, or data-quality review?",
            ],
        )
