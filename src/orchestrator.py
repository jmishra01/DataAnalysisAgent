"""Multi-agent orchestration for conversational CSV analysis."""

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .agents.clarification import ClarificationAgent
from .agents.critic import CriticAgent
from .agents.insight import InsightAgent
from .agents.planner import PlannerAgent
from .config import settings
from .context import ContextBuilder, PromptContext
from .errors import LLMRefusalError
from .guardrails import validate_csv_file, validate_question
from .llm_client import LLMClient
from .memory import ConversationMemory
from .schemas import AgentResponse, AnalysisPlan, ConversationTurn
from .tools.code_executor import UnsafeCodeError, execute_analysis
from .tools.csv_profiler import CsvProfile, profile_csv


class DataAnalysisAgent:
    """Coordinates specialized agents, tools, memory, and response handling."""

    def __init__(
        self,
        csv_path: str,
        llm: LLMClient | None = None,
        memory: ConversationMemory | None = None,
        session_id: str | None = None,
    ) -> None:
        validation = validate_csv_file(csv_path)
        if not validation.is_valid:
            raise ValueError(f"CSV validation failed: {validation.reason}")

        self.csv_path = str(Path(csv_path).resolve())
        self.profile: CsvProfile = profile_csv(self.csv_path)
        self.llm = llm or LLMClient()
        self.memory = memory or ConversationMemory(settings.memory_db_path)
        self._owns_memory = memory is None
        self.session_id = self.memory.open_session(self.csv_path, session_id)
        self.history = self.memory.load_turns(self.session_id, settings.memory_turn_limit)
        self.context_builder = ContextBuilder(settings.max_context_tokens)

        self.clarifier = ClarificationAgent(self.llm)
        self.planner = PlannerAgent(self.llm)
        self.critic = CriticAgent(self.llm)
        self.insight_agent = InsightAgent(self.llm)

        self.trace_id = uuid.uuid4().hex[:12]
        settings.log_dir.mkdir(parents=True, exist_ok=True)
        self.logger = self._make_logger()
        self._trace(
            "session",
            "Opened analysis session",
            session_id=self.session_id,
            restored_turns=len(self.history),
        )

    def _make_logger(self) -> logging.Logger:
        logger = logging.getLogger(f"csv_agent.{self.trace_id}")
        logger.setLevel(logging.INFO)
        handler = logging.FileHandler(
            settings.log_dir / f"trace-{self.trace_id}.jsonl",
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.propagate = False
        return logger

    def _trace(self, step: str, summary: str, **details: object) -> None:
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "step": step,
            "summary": summary,
            "details": details,
        }
        self.logger.info(json.dumps(event, default=str))

    def _trace_agent(self, agent: object, summary: str, **details: object) -> None:
        self._trace(
            getattr(agent, "name", "unknown_agent"),
            summary,
            fallback_reason=getattr(agent, "last_fallback_reason", None),
            llm_latency_seconds=getattr(self.llm, "last_latency_seconds", None),
            **details,
        )

    def run(self, question: str, *, allow_clarification: bool = True) -> AgentResponse:
        self._trace("orchestrator", "Received analysis request", question=question)
        validation_error = validate_question(question)
        if validation_error:
            return self._finish(
                question,
                self._response("failed", validation_error),
            )

        context = self.context_builder.build(self.profile, self.history, question)
        self._trace(
            "context_manager",
            "Prepared bounded session context",
            approximate_tokens=context.approximate_tokens,
            omitted_turns=context.omitted_turns,
        )

        try:
            resolved_request = question
            if allow_clarification:
                clarification = self.clarifier.decide(question, self.profile, context)
                self._trace_agent(
                    self.clarifier,
                    "Resolved whether clarification is required",
                    needs_clarification=clarification.needs_clarification,
                )
                if clarification.needs_clarification:
                    return self._finish(
                        question,
                        self._response(
                            "needs_clarification",
                            "I need a little more detail before running the analysis.",
                            questions=clarification.questions,
                        ),
                    )
                resolved_request = clarification.resolved_request
            else:
                self._trace(
                    "clarification_agent",
                    "Skipped clarification after receiving user answers",
                )

            plan, critique_error = self._create_approved_plan(
                resolved_request,
                context,
            )
            if plan is None:
                return self._finish(
                    question,
                    self._response(
                        "failed",
                        f"I could not produce a trustworthy analysis plan: {critique_error}",
                    ),
                )

            try:
                output = execute_analysis(plan.code, self.csv_path)
            except (UnsafeCodeError, RuntimeError, TimeoutError) as error:
                self._trace("code_executor", "Execution failed safely", error=str(error))
                return self._finish(
                    question,
                    self._response(
                        "failed",
                        f"The analysis could not be executed safely: {error}",
                        plan=plan,
                    ),
                )
            self._trace(
                "code_executor",
                "Executed approved analysis plan",
                output_preview=output[:500],
            )

            report = self.insight_agent.synthesize(plan, output, context)
            self._trace_agent(
                self.insight_agent,
                "Synthesized grounded findings from tool output",
                insight_count=len(report.insights),
            )
            return self._finish(
                question,
                self._response(
                    "completed",
                    report.summary,
                    insights=report.insights,
                    caveats=report.caveats,
                    analysis_output=output.strip(),
                    plan=plan,
                ),
            )
        except LLMRefusalError as error:
            self._trace("orchestrator", "Model refused the request", reason=str(error))
            return self._finish(
                question,
                self._response(
                    "refused",
                    "The model declined this request. Try narrowing it to a calculation about the CSV.",
                ),
            )

    def _create_approved_plan(
        self,
        request: str,
        context: PromptContext,
    ) -> tuple[AnalysisPlan | None, str]:
        revision_guidance = ""
        issues: list[str] = []
        for attempt in range(1, settings.max_plan_attempts + 1):
            plan = self.planner.plan(
                request,
                self.profile,
                context,
                revision_guidance=revision_guidance,
            )
            self._trace_agent(
                self.planner,
                "Created analysis plan",
                attempt=attempt,
                goal=plan.goal,
                assumptions=plan.assumptions,
            )
            critique = self.critic.review(plan, self.profile)
            self._trace_agent(
                self.critic,
                "Reviewed analysis plan",
                attempt=attempt,
                approved=critique.approved,
                issues=critique.issues,
                warnings=critique.warnings,
            )
            if critique.approved:
                return plan, ""
            issues = critique.issues
            revision_guidance = critique.revision_guidance or " ".join(issues)
        return None, "; ".join(issues) or "The critic did not approve the plan."

    def _response(self, status: str, message: str, **fields: object) -> AgentResponse:
        return AgentResponse(
            status=status,
            message=message,
            session_id=self.session_id,
            trace_id=self.trace_id,
            **fields,
        )

    def _finish(self, question: str, response: AgentResponse) -> AgentResponse:
        self.memory.append(self.session_id, question, response)
        self.history.append(
            ConversationTurn(
                question=question,
                status=response.status,
                message=response.message,
                insights=response.insights[:6],
                clarifications=response.questions,
            )
        )
        self.history = self.history[-settings.memory_turn_limit :]
        self._trace("memory", "Persisted conversation turn", status=response.status)
        return response

    def reset_conversation(self) -> None:
        self.memory.clear(self.session_id)
        self.history.clear()
        self._trace("memory", "Cleared persistent conversation history")

    def close(self) -> None:
        if self._owns_memory:
            self.memory.close()
        for handler in list(self.logger.handlers):
            handler.close()
            self.logger.removeHandler(handler)


DataAnalysisAI = DataAnalysisAgent
