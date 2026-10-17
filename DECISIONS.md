# DECISIONS.md — every autonomous judgment call

This file records every place the build made a decision the spec left open, plus
every (documented) deviation. Rule 3 of the operating contract: *record what you
decided and why*.

## Platform / environment

1. **Sandbox preview runs as a single process on port 3000.** The build sandbox
   exposes exactly one port and has no Docker. `app/main.py` therefore optionally
   serves the built `frontend/dist` (SPA fallback) from the same FastAPI process.
   This changes NOTHING about the deliverable architecture: `docker-compose.yml`
   still runs the standard three services (frontend nginx + backend + postgres),
   and `npm run dev` + `uvicorn --reload` remain the documented dev workflow.
2. **SQLite fallback + Postgres/pgvector dual mode.** The sandbox has no Postgres.
   `DATABASE_URL` selects the engine: `postgresql+psycopg://…` uses pgvector's
   `Vector` column + native cosine distance (the docker-compose default);
   `sqlite:///…` stores embeddings as JSON and does brute-force cosine in Python
   (`app/rag/retriever.py`). Both return identical shapes; spec §10's "one
   database" goal is preserved in the compose deployment.
3. **Sandbox `DATABASE_URL` env sanitisation.** The sandbox exports a foreign
   `DATABASE_URL=file:…` (a Prisma convention) for other tooling; `config.py`
   validates the scheme and falls back to the SQLite default when it isn't a
   SQLAlchemy URL.

## LLM provider

4. **Added a third provider: `mock` (deterministic offline engine).** The spec
   mandates Model Studio + an OpenAI-compatible fallback and forbids hard-coding
   providers inside agent logic — both exist exactly as specified
   (`app/llm/model_studio_adapter.py`, `app/llm/openai_compatible_adapter.py`).
   To make the MVP runnable **with zero API keys** (sandbox, CI, judge laptop
   without a key, this workspace's live demo), a third adapter `mock` was added:
   a rule-based engine + feature-hashing embeddings, selected via
   `LLM_PROVIDER=mock`. Agent nodes tag prompts with `[TASK: …]` so the mock can
   produce the exact structured output each task needs; real LLMs read the marker
   as plain instruction text. The UI never hides this: the health endpoint and
   README state the active provider. This workspace's `.env` ships with `mock`
   for the live preview; `.env.example` defaults to `model_studio`.
5. **Embedding dimensionality is configurable** (`EMBEDDING_DIM`, default 1536)
   because Model Studio embedding models differ (text-embedding-v3 → 1024). The
   pgvector column is created with the configured dimension; SQLite is
   dimension-agnostic.

## Agent graph

6. **One compiled StateGraph, three routed paths.** The spec's three node
   sequences (fresh intake, filing continuation, government-message) are separate
   edge paths in one graph with a **conditional START edge** keyed on the
   persisted conversation phase. This keeps the exact node names and sequences
   from spec §7 while making a stateless graph library stateful across turns.
7. **Added one node beyond §7's list: `present_guidance`.** Spec §2 requires
   "Understand My Options" to give neutral, RAG-grounded guidance with citations;
   §7's node list has no node that produces it. The guidance branch forks after
   `retrieve_official_information` (conditional edge) and reuses existing event
   types plus one extra event (`GUIDANCE_PROVIDED`, `OPTIONS_PRESENTED`) for the
   workflow panel. Documented here rather than silently omitted.
8. **`AgentState` extensions** (all in `state.py`, marked as extensions):
   `phase`, `guidance_requested`, `guidance_mode`, `asked_fields`,
   `awaiting_fields`, `initial_request`, `complaint_id`. The spec allows
   "extend only if genuinely necessary" — these are necessary for turn-based
   orchestration (progressive collection, phase routing, description prefill).
   `errors`, `workflow_events` and `assistant_messages` use an append-only
   reducer; **`assistant_messages`/`workflow_events` are treated as per-turn
   volatile** and stripped before persisting `agent_state`.
9. **Nodes receive services via a factory/closure** (`Services`: llm, gov,
   retriever, db session). This keeps nodes pure-ish and unit-testable while
   letting `store_complaint`/`schedule_followup` touch the DB as real graph nodes.
10. **Validation failures never loop inside the graph.** On a failed validation
    the invalid values are cleared, the fields are re-asked, and the turn ENDS
    (human-in-the-loop). The graph resumes at `collect_information` next turn.
11. **"Report the Incident" uses the same filing path** with a distinct intent
    label. The mock backend has no separate "report" endpoint; differentiating
    would be cosmetic in this MVP (documented as a natural next step).
12. **Progressive collection asks 1–2 fields per turn** — required-missing first,
    then each never-asked optional field once (with a `[Skip]` chip in the UI).
    Optional fields asked once and ignored are not re-asked.
13. **Description prefill.** The citizen's first message usually IS the incident
    description; `collect_information` prefills it from `initial_request` instead
    of asking again (the review card still shows it for editing).

## Mock government client

14. **Status thresholds are env-configurable** (`MOCK_STATUS_*_SECONDS`, defaults
    30/90/180 s) so a live demo shows real progression in minutes, exactly as
    spec §9 asks. `force_advance` (spec's demo safety net) is exposed at
    `POST /api/demo/advance-status` and also makes the complaint's follow-up job
    immediately due + runs one scheduler pass so the change propagates instantly.
15. **The mock case store is a JSON file** (`MOCK_STORE_PATH` or next to the
    SQLite DB), surviving restarts — more believable than memory-only state for a
    live demo. `submit_complaint` is idempotent per `idempotency_key` (GUID kept
    in agent state across retries).

## Data model

16. **Schema extensions beyond §11** (all additive, flagged in `models/__init__.py`):
    - `conversations.agent_state` (JSONB) — persists the AgentState between turns.
    - `conversations.title` — conversation list display.
    - `notifications` table — spec §12/§13 require *in-app notifications*; §11 has
      no table for them.
    - `evidence.conversation_id` — uploads happen while the complaint is still a
      draft; rows are linked to the complaint at submission.
    - `gov_message_logs.user_id` — pasted messages may precede any complaint.
17. **Migrations:** Alembic was specified as "or equivalent". For the MVP the
    schema is created idempotently at startup (`Base.metadata.create_all`) — the
    seed script is likewise idempotent. Swapping to Alembic revisions later is
    mechanical and doesn't affect app code.

## Security / auth

18. **Password hashing uses PBKDF2-HMAC-SHA256 (stdlib)** instead of
    passlib/bcrypt to avoid native-wheel failures on judge machines. JWT via
    PyJWT (HS256, `JWT_SECRET`, `JWT_EXPIRE_MINUTES`).
19. **Evidence files are served through an authorised endpoint**
    (`/api/evidence/{id}/file`) that checks ownership, not public URLs.
20. **Sensitive-value masking** helper exists (`nodes/base.mask_sensitive`) and is
    applied where identifiers could be echoed into transcripts; the demo flow
    doesn't collect CNIC numbers (only phone), so masking is mostly future-proofing.

## Frontend

21. **shadcn/ui-style components are hand-rolled** (Button/Card/Badge/inputs in
    `index.css` + card components) rather than installing the full shadcn
    generator — the spec asks for a "lightweight component library
    (shadcn/ui-style)", and a hand-rolled set keeps the bundle small and the
    look consistent.
22. **Polling instead of WebSocket** for events/notifications (spec §8: "a simple
    polling endpoint is fine for the MVP"). `GET /api/conversations/{id}/events`
    powers the workflow panel; `GET /api/notifications?since=…` powers the bell +
    toasts (6 s interval).
23. **Workflow panel node layout** wraps the sequence into rows of 4 (React Flow)
    and switches to the government-message sequence when a pasted message turn
    occurs, per the two graph paths.
24. **One extra structured card type**: `validation_issues` (re-ask after failed
    validation) — spec §15's list didn't include a card for this state.

## Known deferrals (deliberate, per spec scope)

- `AlibabaOSSStorage` is a wired-but-stubbed adapter (clear error, selectable via
  env, not implemented — spec §4 "stubbed for production").
- Celery+Redis replacement for APScheduler, real email/SMS sending, OAuth login,
  Urdu/localisation, admin portal — all out of MVP scope per spec §A exclusions.
- Browser E2E tests skipped per spec §19; the API-level integration test covers
  the full journey instead.

## Post-review fixes (MVP patch 2)

25. **Google Gemini provider** (`app/llm/gemini_adapter.py`): REST over httpx (no
    new SDK dependency). Two modes via `.env` only — `LLM_PROVIDER=gemini`
    (chat + embeddings from one key) or `EMBEDDING_PROVIDER=gemini` (Gemini
    embeddings with any other chat provider; surfaces as e.g.
    `groq+gemini-embed` in the boot log and `/api/health`). Embeddings always
    request `outputDimensionality = EMBEDDING_DIM` (clamped to ≥768) so stored
    widths stay aligned with the pgvector column / brute-force cosine.
26. **`seed_demo_data.py` was empty** — `main.py` imports `seed_if_empty()` at
    boot, so the app crashed with ImportError on start. The module now seeds
    (idempotently): the demo citizen, the KB, 3 complaints across the mock
    lifecycle (registered in the mock gov case store so tracking works),
    complaint events, notifications, one pending follow-up job and 2 demo
    conversations. `SEED_ON_START` failures no longer block boot (logged and
    skipped instead).
27. **Embedding-dimension drift self-heal** (`reingest_if_dim_changed`): when
    the embedding provider/model/dimension changes, old KB chunks have the
    wrong width — SQLite silently returns empty RAG results, pgvector raises
    dimension-mismatch errors. Startup now detects the drift, wipes and
    re-embeds the KB automatically (PostgreSQL column is recreated).
