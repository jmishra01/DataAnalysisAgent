import argparse
import sys
from collections.abc import Callable

from src.orchestrator import DataAnalysisAgent
from src.presentation import render_profile, render_terminal
from src.schemas import AgentResponse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one analysis question against a CSV file")
    parser.add_argument("--csv", required=True, help="Path to the CSV file")
    parser.add_argument("--question", required=True, help="Analysis question")
    parser.add_argument(
        "--session",
        help="Session ID to create or resume (for example: retail-review)",
    )
    parser.add_argument("--show-code", action="store_true", help="Include generated code")
    return parser


def resolve_clarifications(
    agent: DataAnalysisAgent,
    initial_question: str,
    *,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> AgentResponse:
    """Ask for missing details and rerun the agent with the user's answers."""
    current_question = initial_question
    response = agent.run(current_question)
    if response.status != "needs_clarification":
        return response

    output_fn(f"\nAgent: {response.message}")
    answers: list[str] = []
    for number, question in enumerate(response.questions, start=1):
        answer = input_fn(f"\nQuestion {number}: {question}\nYou: ").strip()
        answers.append(answer or "No preference provided")

    clarification_text = "\n".join(
        f"Clarification answer {number}: {answer}"
        for number, answer in enumerate(answers, start=1)
    )
    resolved_question = (
        f"Original request: {initial_question}\n\n"
        f"User clarification answers:\n{clarification_text}"
    )
    return agent.run(resolved_question, allow_clarification=False)


def main() -> int:
    args = build_parser().parse_args()
    agent: DataAnalysisAgent | None = None
    try:
        agent = DataAnalysisAgent(args.csv, session_id=args.session)
        print(render_profile(agent.profile))
        response = resolve_clarifications(agent, args.question)
        print(f"\nAgent:\n{render_terminal(response, show_code=args.show_code)}")
        return 1 if response.status in {"failed", "needs_clarification"} else 0
    except (EOFError, KeyboardInterrupt):
        print("\nInput cancelled before the analysis was completed.", file=sys.stderr)
        return 130
    except ValueError as error:
        print(f"Input error: {error}", file=sys.stderr)
        return 2
    finally:
        if agent:
            agent.close()


if __name__ == "__main__":
    raise SystemExit(main())
