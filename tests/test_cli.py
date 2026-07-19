import unittest

from cli import resolve_clarifications
from src.schemas import AgentResponse


class FakeAgent:
    def __init__(self) -> None:
        self.questions: list[str] = []

    def run(self, question: str, *, allow_clarification: bool = True) -> AgentResponse:
        self.questions.append(question)
        if len(self.questions) == 1:
            return AgentResponse(
                status="needs_clarification",
                message="I need more detail.",
                questions=["Which metric?", "Which grouping?"],
                session_id="test-session",
                trace_id="test-trace",
            )
        return AgentResponse(
            status="completed",
            message="Analysis complete.",
            insights=["Revenue grouped by City."],
            session_id="test-session",
            trace_id="test-trace",
        )


class ClarificationFlowTests(unittest.TestCase):
    def test_answers_are_sent_back_to_agent(self):
        agent = FakeAgent()
        answers = iter(["Revenue", "City"])

        response = resolve_clarifications(
            agent,
            "Analyze the data",
            input_fn=lambda _prompt: next(answers),
            output_fn=lambda _message: None,
        )

        self.assertEqual(response.status, "completed")
        self.assertIn("Clarification answer 1: Revenue", agent.questions[1])
        self.assertIn("Clarification answer 2: City", agent.questions[1])
        self.assertEqual(len(agent.questions), 2)


if __name__ == "__main__":
    unittest.main()
