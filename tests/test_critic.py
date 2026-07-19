import unittest

from src.agents.critic import CriticAgent
from src.schemas import AnalysisPlan, CritiqueResult
from src.tools.csv_profiler import profile_csv


class OvercautiousCriticLLM:
    available = True
    last_latency_seconds = 0.1

    def structured(self, _system_prompt, _user_prompt, _schema):
        return CritiqueResult(
            approved=False,
            issues=[
                "Category missing values are not checked.",
                "UnitsSold non-negative integer values are not validated.",
            ],
            revision_guidance="Add defensive checks.",
        )


class CriticProfileEvidenceTests(unittest.TestCase):
    def test_verified_profile_facts_do_not_block_plan(self):
        plan = AnalysisPlan(
            goal="Maximum units sold by category",
            assumptions=[],
            code=(
                "import pandas as pd\n"
                "df = pd.read_csv(CSV_PATH)\n"
                "print(df.groupby('Category')['UnitsSold'].max())\n"
            ),
            expected_output="Maximum UnitsSold by Category",
        )

        result = CriticAgent(OvercautiousCriticLLM()).review(
            plan,
            profile_csv("data/retail.csv"),
        )

        self.assertTrue(result.approved)
        self.assertEqual(result.issues, [])
        self.assertEqual(len(result.warnings), 2)


if __name__ == "__main__":
    unittest.main()
