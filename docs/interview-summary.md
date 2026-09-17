# BizIntel AI — Interview Summary

Talking points for explaining this project in an interview. Every answer reflects the actual implementation — nothing aspirational. Numbers cited are from real runs recorded in the repo.

## 30-second explanation

"BizIntel AI is an end-to-end business intelligence platform I built on a restaurant-sales dataset: PostgreSQL analytics, a scikit-learn revenue forecast, and a Next.js dashboard — plus a LangGraph AI agent that answers business questions by calling eight read-only tools across SQL, the forecast model, and a RAG policy store. It only answers from tool output, cites its sources, and I built a deterministic evaluator — no LLM-as-a-judge — that measures tool selection, numerical accuracy, and groundedness. Latest live run: 23/23 tool selection, 19/19 grounded answers, 226 backend and 70 frontend tests passing."

## 1-minute explanation

Same as above, plus: "The interesting engineering is in the honesty guarantees. The agent can't execute arbitrary SQL — tools are whitelisted, parameterized wrappers over a service layer. If data doesn't exist, like profit margins, it answers 'not available' instead of guessing — that's a tested behavior, not a hope. The forecast model extrapolates past its two-month training window and produces negative values at the month boundary; I display that as-is with a limitation note rather than clamping it, because hiding a model's real failure mode in a BI tool would be worse than showing it. Memory is a small PostgreSQL layer rather than a framework checkpointer so every conversation and every run is auditable — status, tools used, latency, model. And the evaluation harness is fully deterministic: strict numeric parsing, citations verified against actual retrieval metadata, prompt-injection cases included. One caveat I always give: it's a portfolio system — 254 transactions, 53 days, synthetic policy documents — so the metrics describe this test set, not universal accuracy."

## Architecture explanation

"Three tiers. PostgreSQL holds 254 sales transactions and 53 daily metrics. FastAPI exposes parameterized analytics, a forecast endpoint serving a frozen joblib artifact, and `/api/chat`. Behind chat sits a single LangGraph agent backed by GLM-5.3 that picks from eight tools — six SQL analytics, one forecast, one RAG retrieval over ChromaDB with local ONNX embeddings. The graph itself is stateless; conversation history comes from an `agent_messages` table injected per request, and every run lands in an `agent_runs` audit table. The Next.js dashboard visualizes the same data the agent queries, so answers can be cross-checked visually. One agent, one graph — I deliberately avoided multi-agent orchestration and MCP because routing from question to tool didn't need them, and a simpler graph is much easier to evaluate."

## Why LangGraph

"I needed controlled tool-calling loops with an explicit graph I could test, not an autonomous agent framework. LangGraph gives the model tool selection while keeping the workflow declarative and inspectable — and because the graph is stateless, multi-turn behavior is just history injection, which I test directly by capturing the prompt the model actually receives. The trade-off I evaluated: framework checkpointer (MemorySaver is process-local; checkpoint-postgres adds psycopg3 and pooling) versus a two-table PostgreSQL layer I control. I chose my own layer — simpler, container-friendly, and audit fields map cleanly."

## Why RAG

"Policy questions — promotion rules, inventory guidelines — can't come from a database or a forecast model. RAG gives document-grounded answers with citations, and the citation requirement is enforced twice: the system prompt says cite only what retrieval returned, and the evaluator verifies citations against actual retrieval metadata, so a fabricated citation fails the case. I used ChromaDB's default ONNX all-MiniLM-L6-v2 — fully local embeddings, no API key — with deterministic chunking (700/80) and a 0.30 similarity floor, below which the tool returns an honest empty result instead of forcing a weak match. And I'm upfront that the five documents are synthetic demos written for the project — the point is demonstrating the verified-retrieval architecture."

## Why PostgreSQL

"The analytics layer is the product — aggregate queries are what the agent serves. A relational store makes them exact, transactional, and inspectable, and it let me co-locate the agent's memory and audit tables with the business data under one idempotent schema. Everything is parameterized SQL through psycopg2; no ORM, because hiding the exact queries would obscure what the agent is actually allowed to call."

## Why ML forecasting

"A 'predict next week' question needs a model, and serving it as a frozen artifact keeps the API deterministic — no retraining in the request path, identical outputs asserted in tests (days=3 → 16,533.84 / 15,924.91 / −9,007.63). I compared Linear Regression, Random Forest, and XGBoost with a chronological split — no shuffling, that's the leakage trap with time series — and Linear Regression won on this data: MAPE 3.64% versus 8.15% and 9.05%. On 53 days, the simplest model generalizing best is itself the honest finding."

## Why Isolation Forest

"Anomaly detection here has no ground truth — nobody labeled fraud or data errors. Isolation Forest is unsupervised, works on small data, and gave 8 flagged dates from three daily features: revenue, quantity, transactions. I label them exploratory signals everywhere — the dashboard, README, docs — because a statistical outlier is not evidence of fraud."

## How tool calling works

"The model receives the tool schemas and a system prompt with explicit routing rules — including a map from phrasing to tools ('current situation' → get_kpi) and an enumerated list of what data exists and what doesn't. It emits tool calls; LangGraph executes them against whitelisted service functions; results go back to the model, which composes the final answer from tool output only. If a question has two explicit needs — current KPIs and a 3-day forecast — it calls both tools in one run, and the dashboard shows a chip per tool used. Routing was 87% initially; prompt-only rules took it to 100% on two consecutive runs, with no graph changes."

## How memory works

"Each chat tab gets a validated session_id. After every turn, the exchange is written to `agent_messages`; on the next request the graph — which is stateless — injects the last 20 messages of that session after the system message. So multi-turn context is a data flow I can test directly: my test LLM captures the prompt, and tests assert the earlier answer is actually in the context. Every run is separately audited in `agent_runs`: status, error type, tools used, latency, model. Failures are fail-closed — if the memory store is down, the request 503s rather than silently losing context."

## How evaluation works

"A deterministic harness — no LLM-as-a-judge. Twenty-three cases across SQL, ML, RAG, combinations, and out-of-domain; every expected value carries its source and tool arguments, so ground truth is re-verifiable through the actual tools. The checks: tool-selection set comparison, strict multi-format numeric parsing — mixed separators, Indonesian thousands format, approximation tolerance, one-step derived arithmetic — conservative groundedness, citations checked against retrieval metadata, prompt-injection cases, and retrieval Hit@k measured directly against ChromaDB. Latest run: 23/23 tool selection, 20/20 numeric, 19/19 groundedness, 8/9 citations, 4/4 out-of-domain. Two parser decisions worth mentioning: I allowed two-step derived arithmetic, measured it — the numeric universe blew up 58 to 922 entries and swallowed a genuinely wrong claim behind the tolerance window — and removed it. And a case that cites the right document with the wrong syntax is still flagged; I didn't loosen the evaluator to make the number look better."

## Security considerations

"Read-only, whitelisted, parameterized tools — there is no arbitrary SQL tool, so the model can't execute user-supplied queries. Session IDs are validated against a strict charset; path traversal gets a 422. Missing LLM credentials or a down memory store fail closed with explicit errors, never fake answers. Secrets are runtime env only — I verified they're absent from Docker image metadata and the frontend bundle. CORS is an explicit allowlist. The frontend container runs non-root, and container startup is fail-closed: wait for the DB, apply schema, import only if empty, ingest RAG. Prompt injection is a test case that must be refused. Honest caveat: it's single-user with no authn — a demo, not a hardened product."

## Biggest limitation

"The data: 254 transactions over 53 days in a single season. It cascades — the forecast model extrapolates past its training window and produces negative values at the month boundary, which I display as-is with a limitation note rather than clamping, and all the evaluation numbers describe this dataset, not general accuracy. I chose disclosure over patching because in a BI tool, quietly hiding a model's failure mode is worse than showing it."

## What would be improved for production

"Multi-season history first — it fixes forecasting at the root. Then stronger time-series methodology with validated extrapolation behavior and business constraints; real knowledge sources behind RAG with access control; authentication and multi-tenancy; a larger evaluation set — I'd add row-count outputs to the numeric universe so multi-step arithmetic can be checked safely; managed cloud Postgres and vector store; monitoring and a retraining pipeline with drift detection. The architecture maps onto all of it — that's the point of having built it in phases with tests at every layer."
