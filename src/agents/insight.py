from ..context import PromptContext
from ..errors import LLMError
from ..prompts import INSIGHT_SYSTEM_PROMPT
from ..schemas import AnalysisPlan, InsightReport
from .agent import SpecializedAgent


class InsightAgent(SpecializedAgent):
    name = "insight_agent"

    def synthesize(
        self,
        plan: AnalysisPlan,
        tool_output: str,
        context: PromptContext,
    ) -> InsightReport:
        self.reset_diagnostics()
        if self.llm.available:
            prompt = (
                f"Goal: {plan.goal}\nExpected output: {plan.expected_output}\n"
                f"<execution_output>\n{tool_output}\n</execution_output>\n\n"
                f"Session context for reference:\n{context.text}"
            )
            try:
                return self.llm.structured(
                    INSIGHT_SYSTEM_PROMPT,
                    prompt,
                    InsightReport,
                )
            except LLMError as error:
                self._fallback_after(error)
        return self._fallback(tool_output)

    @staticmethod
    def _fallback(tool_output: str) -> InsightReport:
        lines = [line.strip() for line in tool_output.splitlines() if line.strip()]
        return InsightReport(
            summary="Analysis complete.",
            insights=lines[:6] or ["The analysis ran but produced no displayable output."],
            caveats=["Insights are a direct rendering of computed output; no model synthesis was used."],
        )
