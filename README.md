# Personal Expense Management Agent

A university Agent Based Modeling assignment demonstrating an LLM agent, a real MCP
server/client, long-term SQLite memory, thread-scoped LangGraph state, and locally
embedded RAG over the supplied finance documents. The transaction CSV and eight
knowledge documents are synthetic assignment inputs and are copied unchanged.

## Requirements and setup

- Python 3.11 or newer
- A Groq API key for live chat (the reproducible demo and tests need no key)

From this directory:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Set `GROQ_API_KEY` in `.env`. The default provider is Groq when that key is present;
`LLM_PROVIDER=groq` can be set explicitly. Never commit `.env`.

The code was checked against current package releases and official LangChain/MCP
examples on 2026-11-05. It uses LangChain `create_agent`, the `MultiServerMCPClient`
stdio configuration, and the MCP SDK v1 `FastMCP` API. Although MCP SDK 2.x is
published, this project intentionally bounds `mcp` to `<2` because the assignment
requires the v1 FastMCP server interface used by the adapter examples.

## Run

Build the persistent Chroma index (downloads the local embedding model on first run):

```powershell
python -m src.ingest
```

Start a live chat:

```powershell
python -m src.cli --user alice --session s1
python -m src.cli --user alice --session s1 --verbose
```

The MCP server is launched as a child Python process over stdio. Its tools read
`data/transactions.csv`; they do not call an LLM. Verbose mode prints tool
arguments/results and the retrieved evidence chunks.

## Web UI

Start the Streamlit chat from the project directory:

```powershell
python -m streamlit run app.py
```

If you are using the virtual environment at `D:\e` without activating it:

```powershell
D:\e\Scripts\python.exe -m streamlit run app.py
```

The sidebar lets you choose a user, start a new conversation, show/hide tool and
RAG evidence, and review stored budgets and goals. Proposed memory changes display
explicit **Yes, save** and **No, cancel** buttons. The UI shares the same agent,
SQLite memory, MCP tools, RAG index, and `.env` settings as the CLI.

Run the API-key-free demo and tests:

```powershell
python demo/run_demo.py
python -m pytest
```

The deterministic demo exercises scenarios A-G, writes `demo/demo_output.md`, and
records JSON-lines tool events in `demo/sample_session_logs/demo_tool_calls.jsonl`.
It uses the same deterministic transaction functions, SQLite memory, and RAG
retriever, with scripted responses to keep the run reproducible and free-tier
friendly. For live-model conversations, use the CLI.

## Configuration and persistence

| Environment variable | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER` | `groq` when a Groq key exists | Selects the configured chat provider |
| `GROQ_API_KEY` | unset | Required for live LLM chat |
| `GROQ_MODEL` | `openai/gpt-oss-120b` | Groq model |
| `TRANSACTIONS_CSV` | `data/transactions.csv` | Transaction source |
| `RAG_DOCS_DIR` | `rag_docs` | Markdown knowledge sources |
| `CHROMA_PATH` | `chroma_db` | Persistent Chroma database |
| `MEMORY_DB_PATH` | `memory.db` | User profiles, budgets, goals, and notes |
| `AGENT_LOG_PATH` | `logs/agent.log` | Structured tool-call JSONL |

LangGraph's in-memory checkpointer retains short-term state by `thread_id` for the
life of the running CLI. Long-term user memory is SQLite-backed and survives
restarts. Memory writes are staged and require an explicit confirmation turn.

## Project layout

```text
data/transactions.csv        Synthetic transactions
rag_docs/                    Eight supplied finance references
src/config.py                Environment, paths, and Groq model factory
src/prompts.py               Role, routing, evidence, privacy, and oversight policies
src/memory_store.py          SQLite durable memory and confirmation staging
src/rag.py                   Local embedding, Chroma ingestion, and retrieval
src/transactions.py          Deterministic analysis underlying MCP tools
src/mcp_server.py            Official FastMCP stdio server
src/agent.py                 LangChain agent, MCP client, tools, checkpointer
src/cli.py                   Interactive CLI
src/ingest.py                RAG indexing command
app.py                       Streamlit chat UI
tests/                       API-key-free unit and agent-flow tests
demo/                        Scripted scenarios and generated transcript
report/                      Architecture diagram and design notes
```

See the [architecture diagram](report/architecture.png), its
[Mermaid source](report/architecture.mmd), and the
[design and evaluation notes](report/report_notes.md).

## Troubleshooting

- **Missing Groq key:** Add `GROQ_API_KEY` to `.env`; the demo/tests do not need it.
- **RAG answers use keyword fallback:** Run `python -m src.ingest`; first-time local
  model download requires network access and enough disk space.
- **MCP tools unavailable:** Run from the project directory and reinstall the pinned
  `requirements.txt`; the child server must start with `python -m src.mcp_server`.
- **MCP stdio JSON/protocol errors:** Do not add normal `print()` output to the server
  module; stdout is reserved for MCP. Tool telemetry goes to a JSONL file.
- **No transaction file:** Check `TRANSACTIONS_CSV` or restore the supplied CSV.
- **Model/API errors:** The agent retries once and then reports the error. Verify
  provider key, model name, and network availability.
- **Data boundaries:** Personal data is local in SQLite/Chroma/logs. Do not store
  credentials, card numbers, CVVs, or OTPs.

## Assignment scope and limitations

The application is educational and operates on synthetic transactions. It is not
professional financial advice, has no payment/bank integration, and does not
recommend specific investments, tax actions, or legal actions. Category rules are
transparent keyword heuristics; ambiguous/high-value classifications request review.
The RAG index is local, but live chat sends user prompts and selected tool results to
the configured Groq API.
