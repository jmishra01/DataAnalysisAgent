import unittest

from src.presentation import render_profile, render_terminal
from src.schemas import AgentResponse, AnalysisPlan
from src.tools.csv_profiler import profile_csv


class TerminalPresentationTests(unittest.TestCase):
    def test_csv_profile_is_human_readable(self):
        rendered = render_profile(profile_csv("data/retail.csv"))

        self.assertIn("CSV data profile", rendered)
        self.assertIn("300 rows x 8 columns", rendered)
        self.assertIn("Revenue: float64", rendered)

    def test_completed_response_is_human_readable(self):
        response = AgentResponse(
            status="completed",
            message="Revenue analysis complete.",
            session_id="test-session",
            trace_id="test-trace",
            insights=["Mumbai has the highest revenue."],
            analysis_output="Mumbai  428779.59",
            plan=AnalysisPlan(
                goal="Compare revenue",
                assumptions=[],
                code="print('result')",
                expected_output="Revenue by city",
            ),
        )

        rendered = render_terminal(response)

        self.assertIn("Revenue analysis complete.", rendered)
        self.assertIn("Mumbai has the highest revenue.", rendered)
        self.assertNotIn('"status"', rendered)
        self.assertNotIn("print('result')", rendered)
