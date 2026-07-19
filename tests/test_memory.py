import tempfile
import unittest
from pathlib import Path

from src.memory import ConversationMemory
from src.orchestrator import DataAnalysisAgent


CSV = "data/retail.csv"


class OfflineLLM:
    available = False
    last_latency_seconds = None


class PersistentMemoryTests(unittest.TestCase):
    def test_turns_are_restored_by_session_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "memory.sqlite3"
            first_memory = ConversationMemory(database)
            first = DataAnalysisAgent(
                CSV,
                llm=OfflineLLM(),
                memory=first_memory,
                session_id="sales-review",
            )
            first.run("Compare revenue by city")
            first_memory.close()

            second_memory = ConversationMemory(database)
            resumed = DataAnalysisAgent(
                CSV,
                llm=OfflineLLM(),
                memory=second_memory,
                session_id="sales-review",
            )
            self.assertEqual(len(resumed.history), 1)
            self.assertEqual(resumed.history[0].question, "Compare revenue by city")
            second_memory.close()


if __name__ == "__main__":
    unittest.main()
