# Multi-Agent CSV Data Analysis

A conversational analysis application that profiles a CSV, clarifies intent, generates and critiques pandas code, executes the approved plan, and reports evidence-backed findings. Conversations can be resumed across process restarts through a named session.

## Architecture

```text
                         +-----------------------+
CSV + question --------->| Input guardrails      |
                         | file + prompt limits  |
                         +-----------+-----------+
                                     |
                   +-----------------v-----------------+
                   | Orchestrator                      |
                   | state machine, retries, tracing   |
                   +-----------------+-----------------+
                                     |
        +----------------------------+----------------------------+
        |                            |                            |
        v                            v                            v
+---------------+          +------------------+          +----------------+
| Context       |<-------->| SQLite memory    |          | CSV profiler   |
| bounded turns |          | durable sessions |          | schema/sample  |
+-------+-------+          +------------------+          +--------+-------+
        |                                                        |
        +--------------------------+-----------------------------+
                                   |
                                   v
                         +---------------------+
                         | Clarification Agent |
                         | resolve / ask       |
                         +----------+----------+
                                    |
                                    v
                         +---------------------+
                    +--->| Planning Agent      |
                    |    | typed pandas plan   |
                    |    +----------+----------+
                    |               |
                    |               v
                    |    +---------------------+
                    +----| Critic Agent        |
                  revise | semantic + policy   |
                         +----------+----------+
                                    | approved
                                    v
                         +---------------------+
                         | Code Executor Tool  |
                         | AST + subprocess    |
                         +----------+----------+
                                    |
                                    v
                         +---------------------+
                         | Insight Agent       |
                         | grounded synthesis  |
                         +----------+----------+
                                    |
                                    v
                         terminal response / JSONL trace
```

The agents run sequentially because each stage depends on evidence produced by the previous stage. Parallel agents would add cost and latency without improving this workflow. The critic is independent from the planner, and deterministic policy checks remain authoritative even when the critic model approves a plan.

## Architectural rationale

| Component           | Responsibility                                                               | Why it exists                                                     |
| ------------------- | ---------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| Clarification agent | Converts a follow-up into a standalone request or asks up to three questions | Prevents expensive analysis of ambiguous intent                   |
| Planning agent      | Produces a typed goal, assumptions, pandas code, and expected output         | Separates reasoning about the computation from execution          |
| Critic agent        | Checks goal alignment and unsupported assumptions                            | Detects hallucinated columns and weak plans before tool use       |
| Code executor       | Applies AST policy and runs code in a timed subprocess                       | The model proposes actions; deterministic code controls execution |
| Insight agent       | Explains only values present in execution output                             | Keeps narrative claims grounded in computed evidence              |
| Context manager     | Selects recent compact turns within a token budget                           | Supports follow-ups without unbounded prompts                     |
| SQLite memory       | Stores compact turns under a named session                                   | Survives CLI restarts without another service dependency          |

Pydantic models are the contracts between agents. The orchestrator owns control flow, bounded plan revision, tracing, persistence, and graceful terminal responses; individual agents do not call tools or mutate session state.

## Tool selection

- **pandas** handles heterogeneous tabular analysis and is familiar to reviewers.
- **AST validation** rejects unsupported imports, dynamic execution, alternate file reads, file writers, and dunder access before code starts.
- **Isolated subprocess execution** provides a hard timeout and keeps generated variables away from the host process. This is suitable for a take-home demonstration; production deployment should add a container sandbox with CPU, memory, filesystem, and network isolation.
- **SQLite** provides atomic, durable local memory with no infrastructure setup.
- **OpenAI structured responses** parse directly into Pydantic models, removing ad-hoc JSON extraction. This structure is internal; terminal responses are always human-readable.

## Prompt and context design

Each agent has a narrow system prompt in [`src/prompts.py`](src/prompts.py):

- role and single responsibility;
- explicit structured-output contract;
- instruction/data boundaries around dataset samples, generated code, and tool output;
- prohibitions against invented columns, unsupported claims, network access, and file writes;
- grounding instructions for the insight agent.

The CSV profile is supplied instead of the full file. Sample cells are length-limited. Recent turns contain only the question, status, short message, up to four insights, and clarification questions. The context manager fills the prompt newest-first until `MAX_CONTEXT_TOKENS` is reached and reports omitted-turn counts in the trace. Older turns remain in SQLite but are excluded from the model prompt when they no longer fit.

## Failure awareness

| Failure                                 | Behavior                                                                                |
| --------------------------------------- | --------------------------------------------------------------------------------------- |
| Hallucinated column or unsafe code      | deterministic critic rejects it; planner receives revision guidance for a bounded retry |
| Model refusal                           | returns a clear `refused` response and suggests narrowing the CSV question              |
| Invalid structured output               | classified separately; the specialized agent uses its deterministic fallback            |
| Context/token limit                     | bounded context is used first; provider context errors fall back locally                |
| Timeout, rate limit, connection, or 5xx | exponential backoff with bounded retries, then local fallback                           |
| Slow code                               | subprocess is terminated at the execution timeout                                       |
| Tool failure                            | error is logged and returned without exposing a stack trace to the user                 |
| Session ID reused for another CSV       | rejected to prevent cross-dataset memory contamination                                  |

Latency for the latest model call, fallback reason, agent decisions, tool output preview, context size, and memory events are recorded in `logs/trace-<id>.jsonl`. Logs contain concise decision summaries rather than private chain-of-thought.

## Run

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .example.env .env
# Set OPENAI_API_KEY in .env
```

### Makefile shortcuts

Run `make` or `make help` to list the available commands. Common examples:

```bash
make install
make test
make run QUESTION="Compare revenue by city" SESSION=retail-review
make run-code QUESTION="Show the monthly revenue trend"
make docker-build
make docker-run QUESTION="Check missing values and duplicates"
```

`CSV`, `QUESTION`, and `SESSION` can be overridden for each invocation. `make check` runs the unit tests, representative evaluation, and Compose validation.

Run a question in a durable session:

```bash
uv run python cli.py \
  --csv data/retail.csv \
  --question "Compare revenue across categories" \
  --session retail-review
```

If the request is ambiguous, the command pauses for one clarification round and asks the clarification agent’s questions directly in the terminal. Answers are added to the request context, clarification is then bypassed, and the workflow proceeds through planning, critique, execution, and final human-readable output.

Every command first prints a compact CSV profile containing the dataset shape, column types, missing-value counts, numeric summaries, and five sample rows. The complete CSV is never printed.

Run another command with the same session ID to ask a contextual follow-up. Previous turns are restored from SQLite before the request is processed:

```bash
uv run python cli.py \
  --csv data/retail.csv \
  --question "Now show the monthly trend" \
  --session retail-review
```

If `--session` is omitted, the application creates an ID and prints it so it can be resumed later. Without an API key, all roles use deterministic fallbacks and the application remains runnable.

Each invocation prints a readable terminal response:

```bash
uv run python cli.py \
  --csv data/retail.csv \
  --question "Compare revenue by city" \
  --session retail-review
```

## Run with Docker Compose

Build and run the agent:

```bash
docker compose build
docker compose run --rm csv-agent
```

Compose reads `OPENAI_API_KEY` and `OPENAI_MODEL` from the environment or the local `.env` file. The bundled retail CSV is used by default. Conversation memory and traces are stored in the named `agent-memory` and `agent-logs` volumes, so `--rm` removes only the temporary container—not the saved session.

To submit a follow-up question to a named session:

```bash
AGENT_SESSION_ID=retail-review \
ANALYSIS_QUESTION="Now show the monthly trend" \
docker compose run --rm csv-agent
```

To analyse another file, place it in the project’s `data/` directory and override the service command:

```bash
docker compose run --rm csv-agent \
  --csv /app/data/my-file.csv \
  --question "Check missing values and duplicates" \
  --session my-review
```

The container runs as an unprivileged user with all Linux capabilities dropped, a read-only root filesystem, read-only CSV mount, and a size-limited temporary directory. Only the memory and log volumes are writable.

## Evaluation

```bash
uv run python -m unittest discover -s tests -v
```

The suite covers interactive clarification handoff, specific analysis, multi-turn context, persistence across process-equivalent agent instances, bounded prompt context, refusal handling, context-limit fallback, prompt injection, unsafe imports, alternate file reads, and terminal rendering. A representative multi-agent trace is checked in at [`examples/full_run_trace.jsonl`](examples/full_run_trace.jsonl).

## Project layout

```text
src/agents/clarification.py  intent resolution
src/agents/planner.py        typed analysis planning
src/agents/critic.py         semantic and deterministic review
src/agents/insight.py        grounded result synthesis
src/orchestrator.py          multi-agent state machine
src/context.py               prompt-budget management
src/memory.py                durable SQLite sessions
src/llm_client.py            retries, timeouts, refusal/error classification
src/prompts.py               versioned role prompts
src/tools/                   CSV profiling and safe execution
src/presentation.py          human-readable terminal renderer
tests/                       behavior and failure-path tests
```
