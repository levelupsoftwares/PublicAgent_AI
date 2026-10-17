# PublicAgent AI

**Agentic GovTech complaint assistant** — Alibaba Cloud AI Hackathon Pakistan 2026.

PublicAgent AI is a guided, agentic *front door* between a citizen and the maze of
departments, forms and procedures they would otherwise have to figure out alone.
The citizen describes a problem in plain language; a real multi-step LangGraph
agent classifies the issue, retrieves (demo) official guidance via RAG, presents
neutral options, progressively collects only the missing information, shows a full
review, submits **only after explicit confirmation**, then keeps watching the
complaint on a schedule and translates government replies (even pasted SMS text)
into plain language.

> **All government data in this app is demo / mock data.** No real complaint is
> filed anywhere and no real institution is affiliated with this prototype.
> The UI labels every piece of information as *user-reported*, *AI-extracted
> (unverified)* or *(mock) official data*.

---

## Quick start (Docker — recommended)

```bash
cp .env.example .env         # fill in GROQ_API_KEY + OPENROUTER_API_KEY for a real
                             # Groq (chat) + OpenRouter (embeddings) stack;
                             # the app also runs fully offline with LLM_PROVIDER=mock
docker compose up --build
```

- Frontend: http://localhost:5173
- Backend API: http://localhost:8000 (docs at `/docs`)
- Postgres 16 with **pgvector** (one container — relational + vector in one DB)

Then open the app and click **Continue as Demo Citizen**.

### Default provider: Groq + OpenRouter

Out of the box the `.env` is wired for `LLM_PROVIDER=groq`:

| Layer       | Provider   | Model                                | Where to get a key           |
|-------------|------------|--------------------------------------|------------------------------|
| Chat (LLM)  | Groq       | `qwen/qwen3-32b`                     | https://console.groq.com/keys |
| Embeddings  | OpenRouter | `nvidia/nemotron-3-embed-1b:free`    | https://openrouter.ai/keys    |

> **Note on the model name:** Groq does not host a `qwen3-27b` variant. The
> closest available Qwen3 model on Groq is `qwen/qwen3-32b` (the default). To
> use a different Groq-hosted Qwen, override `GROQ_MODEL_NAME` in `.env`.

> **Embedding dimension:** `EMBEDDING_DIM=1024` matches the default
> `nvidia/nemotron-3-embed-1b:free` model. If you swap to a different
> embedding model, change `EMBEDDING_DIM` to match AND wipe the postgres
> volume (`docker compose down -v`) so the `kb_chunks.embedding` column is
> recreated at the new width on first boot.

### Google Gemini (chat + embeddings)

Gemini is supported in two modes — both configured purely via `.env`:

1. **Gemini for everything** — dynamic chat replies AND embeddings from one
   key ([get a key](https://aistudio.google.com/apikey)):
   ```env
   LLM_PROVIDER=gemini
   GEMINI_API_KEY=AIza...
   GEMINI_CHAT_MODEL=gemini-2.0-flash
   GEMINI_EMBEDDING_MODEL=gemini-embedding-001
   EMBEDDING_DIM=1536
   ```
2. **Gemini embeddings only** (e.g. keep Groq chat, use `gemini-embedding-001`
   for the RAG knowledge base):
   ```env
   LLM_PROVIDER=groq
   GROQ_API_KEY=gsk_...
   EMBEDDING_PROVIDER=gemini
   GEMINI_API_KEY=AIza...
   EMBEDDING_DIM=1536
   ```

The boot log and `/api/health` report the active engine (`gemini` or
`groq+gemini-embed`). `gemini-embedding-001` supports Matryoshka truncation,
so any `EMBEDDING_DIM` between 768 and 3072 works; if you change the
dimension after data was ingested, the backend detects the drift on boot,
wipes and re-embeds the knowledge base automatically.

### Other providers

Set `LLM_PROVIDER` in `.env` to switch:

- `mock` — deterministic offline engine (no API keys needed; default fallback
  when keys are missing).
- `model_studio` — Alibaba Cloud Model Studio / Qwen via DashScope (set
  `DASHSCOPE_API_KEY`).
- `openai_compatible` — any OpenAI-compatible endpoint (set `OPENAI_API_KEY`
  and `OPENAI_BASE_URL`).

## Quick start (manual, no Docker)

```bash
# backend  (Python 3.12)
cd backend && pip install -r requirements.txt
export DATABASE_URL=sqlite:///./data/publicagent.db   # or a Postgres URL with pgvector
uvicorn app.main:app --reload --port 8000

# frontend (Node 20+)
cd frontend && npm install && npm run dev   # http://localhost:5173, proxies /api → :8000

# seed (idempotent — also happens automatically on backend boot)
python -m app.scripts.seed_demo_data
```

The **default `.env` in this workspace uses `LLM_PROVIDER=mock`** — a deterministic,
rule-based LLM engine so the whole demo runs with zero API keys (CI, judge laptops,
offline demos). Switch to `model_studio` with a `DASHSCOPE_API_KEY` to use Qwen; no
other code changes are needed (the agent only ever calls the `LLMClient` interface).

## The demo script 

1. Log in with **Continue as Demo Citizen**.
2. Type: *"A police officer misbehaved with me."*
   → the agent classifies the issue and shows **neutral options** — it never files immediately.
3. Click **Understand My Options** → RAG-grounded guidance with **source citations**.
4. Click **File a Formal Complaint** → it asks **only what's missing**, 1–2 fields at a
   time, every optional field carrying a **[Skip]** button.
5. Review card lists everything, with a clearly-marked **"reported by you — not
   independently verified"** section. Press **Confirm & Submit**.
6. Get reference `CMP-YYYY-NNNNNN`; a follow-up job is scheduled automatically.
7. Watch the status advance on its own (mock thresholds: ~30 s → Received, ~90 s →
   Under Review) with an **in-app notification**, or force it from the dashboard's
   **Demo: advance status** button (live-demo safety net).
8. Paste a mock government SMS, e.g.
   `Police Complaints Authority: Complaint CMP-2026-001928 requires additional documents...`
   → the agent extracts the reference, explains it in plain language, updates the
   timeline and labels it **"from a message you pasted — not independently verified"**.

The **Agent workflow panel** (right side, React Flow) visualises the graph live:
✓ completed · ● current · ○ upcoming — driven only by safe workflow events
(raw chain-of-thought never leaves the backend).

## Architecture

```
Citizen (browser)
      │
      ▼
React 18 + TypeScript + Vite  ─────►  Workflow panel (React Flow)
      │  REST / JSON
      ▼
FastAPI backend
      ├── LangGraph agent  ──uses──►  LLMClient (Model Studio / OpenAI-compatible / mock)
      │        ├──► RAG retriever ──► pgvector (in Postgres) or in-process cosine (SQLite)
      │        └──► GovernmentServiceClient ──► MockGovernmentClient (swappable)
      ├── APScheduler follow-up job ──► GovernmentServiceClient.get_complaint_status()
      └── PostgreSQL (users, conversations, messages, complaints, complaint_events,
                      evidence, followup_jobs, gov_message_logs, kb_documents, kb_chunks,
                      notifications)
```

### Agent graph (LangGraph — exact node names)

```
understand_request → classify_issue → identify_authority → retrieve_official_information
   → analyze_available_data → present_options → END
collect_information → validate_information → prepare_complaint → request_confirmation
   → submit_complaint → store_complaint → schedule_followup → END
analyze_user_message → detect_government_message → extract_reference → retrieve_complaint
   → analyze_status → update_complaint → explain_to_user → END
```

All three paths are compiled into one `StateGraph` with a conditional START edge
that routes on the persisted conversation phase — stateful across chat turns while
preserving the exact node sequences. See `DECISIONS.md` for every judgment call.

### Safety & accuracy rules (enforced in code)

- Submission is **hard-gated** on `user_confirmation=True` and idempotent per draft.
- Allegations are never stated as facts; every surface labels its data source.
- Pasted messages are persisted in `gov_message_logs` and treated as unverified
  unless the (mock) status API corroborates them.
- Emergency phrasing surfaces the **helpline 15** prompt *in addition to* the normal flow.
- Uploads: JPG/PNG/PDF only, 10 MB cap, everything else rejected with a clear message.
- Secrets only via env vars; `.env` is git-ignored; `.env.example` documents them.

## Testing

```bash
cd backend && python -m pytest tests/ -q
```

18 tests cover: each agent node's core logic (mock LLM), the `MockGovernmentClient`
(including time-based status progression + force-advance), the government message
parser (regex + heuristics), and a full API integration test of the journey:
describe → options → file → collect → review → confirm → submit → idempotent
re-confirm → force-advance → notification → paste-message → timeline.

## Project layout

```
/backend      FastAPI + LangGraph agent + RAG + scheduler + tests
/frontend     React + TS + Vite + Tailwind + React Flow
docker-compose.yml    frontend + backend + postgres(pgvector)
.env.example  every environment variable, documented
DECISIONS.md  every autonomous judgment call made during the build
```
