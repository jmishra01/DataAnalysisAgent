import unittest

from src.context import ContextBuilder
from src.schemas import ConversationTurn
from src.tools.csv_profiler import profile_csv


class ContextBuilderTests(unittest.TestCase):
    def test_context_keeps_recent_turns_within_budget(self):
        history = [
            ConversationTurn(
                question=f"Question {index} " + ("x" * 100),
                status="completed",
                message="done",
                insights=["result"],
            )
            for index in range(10)
        ]
        context = ContextBuilder(max_tokens=600).build(
            profile_csv("data/retail.csv"),
            history,
            "What changed?",
        )
        self.assertLessEqual(context.approximate_tokens, 600)
        self.assertGreater(context.omitted_turns, 0)
        self.assertIn("What changed?", context.text)

    def test_large_profile_cells_are_truncated(self):
        profile = profile_csv("data/retail.csv")
        profile.sample_rows[0]["City"] = "x" * 20_000
        context = ContextBuilder(max_tokens=700).build(profile, [], "Summarize revenue")
        self.assertLessEqual(context.approximate_tokens, 700)
        self.assertIn("profile truncated", context.text)


if __name__ == "__main__":
    unittest.main()
