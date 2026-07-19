"""Human-readable terminal presentation for agent responses."""

from .schemas import AgentResponse
from .tools.csv_profiler import CsvProfile


def render_profile(profile: CsvProfile) -> str:
    """Render the initial CSV profile without exposing the full dataset."""
    return f"CSV data profile\n{'=' * 16}\n{profile.to_prompt_text(max_sample_rows=5)}"


def render_terminal(response: AgentResponse, *, show_code: bool = False) -> str:
    sections: list[str] = []

    if response.status == "completed":
        sections.append(response.message)
        if response.insights:
            findings = "\n".join(f"- {insight}" for insight in response.insights)
            sections.append(f"Findings:\n{findings}")
        if response.caveats:
            caveats = "\n".join(f"- {caveat}" for caveat in response.caveats)
            sections.append(f"Caveats:\n{caveats}")
        if response.analysis_output:
            sections.append(f"Supporting output:\n{response.analysis_output}")
    elif response.status == "needs_clarification":
        questions = "\n".join(f"- {question}" for question in response.questions)
        sections.append(response.message)
        if questions:
            sections.append(f"Questions still requiring answers:\n{questions}")
    elif response.status == "refused":
        sections.append(response.message)
    else:
        sections.append(f"The analysis could not be completed: {response.message}")

    if show_code and response.plan:
        sections.append(f"Python used for this analysis:\n{response.plan.code.rstrip()}")

    sections.append(f"Session: {response.session_id}")
    return "\n\n".join(sections)
