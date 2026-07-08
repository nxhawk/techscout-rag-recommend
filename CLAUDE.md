# CLAUDE.md

## Language Rules

- **Code comments**: English only.
- **Docstrings**: English only.
- **Variable/function/class names**: English only.
- **Documentation files**: `README.md` and `CLAUDE.md`: English only. `docs/**/*.md` (MkDocs site): bilingual via `mkdocs-static-i18n` — English is the default/source language (no suffix, e.g. `index.md`); Vietnamese translations use the `.vi.md` suffix (e.g. `index.vi.md`). Every English page should eventually get a matching `.vi.md` counterpart; pages without one fall back to English automatically (`fallback_to_default: true` in `mkdocs.yml`).
- **Git commit messages**: English only.
- **User-facing text** (LLM prompts, API responses shown to end users): Vietnamese.

## Code Style

- Use Python 3.11+ features (type unions with `|`, `match` statements, etc.).
- Use type hints on all function signatures.
- Use `uv` for package management (not pip). Add deps via `uv add <package>`.
- Documentation site: MkDocs Material (`docs/` folder, config in `mkdocs.yml`), i18n via `mkdocs-static-i18n` (EN default, VI suffix `.vi.md`).

## Project Overview

RAG-based product recommendation & comparison system. Users ask natural language queries in Vietnamese, the system retrieves product data from a vector DB, then an LLM generates contextual answers.

Two main pipelines:
- **Recommend**: Query → Intent Parser → Filter → Retrieve → Rerank → Score → LLM → Response
- **Compare**: Query → Extract Products → Retrieve Specs → Align → Compare → LLM → Response

## Project Structure

```
rag-product-recommend/
├── pyproject.toml              # Dependencies & project metadata
├── uv.lock                     # Lockfile
│
├── src/                        # Core business logic
│   ├── crawler/                # Web crawling (raw data collection)
│   │   ├── config.py           #   CrawlerConfig / SourceConfig (crawler.yaml)
│   │   ├── http_client.py      #   httpx client: retry + rate limit + robots
│   │   ├── rate_limiter.py     #   Polite delay between requests
│   │   ├── robots.py           #   robots.txt checker
│   │   ├── parser.py           #   BeautifulSoup helpers (price/rating/text)
│   │   ├── models.py           #   CrawledProduct / CrawlResult dataclasses
│   │   ├── storage.py          #   Save raw results to data/raw/crawled
│   │   ├── pipeline.py         #   CrawlPipeline: spider → product → store
│   │   └── spiders/            #   One spider per source
│   │       ├── base_spider.py  #     BaseSpider (list + detail hooks)
│   │       ├── tgdd_spider.py  #     thegioididong.com
│   │       └── cellphones_spider.py # cellphones.com.vn
│   │
│   ├── ingestion/              # Data loading & normalization
│   │   ├── product_loader.py   #   Load from JSON/CSV
│   │   ├── review_loader.py    #   Load user reviews
│   │   ├── data_cleaner.py     #   Clean & normalize data
│   │   ├── spec_parser.py      #   Parse product specs
│   │   ├── chunker.py          #   Field-based chunking
│   │   └── price_tracker.py    #   Price history tracking
│   │
│   ├── embedding/              # Embedding & Vector DB
│   │   ├── product_embedder.py #   Text → vector (OpenAI)
│   │   ├── multi_field_embedder.py
│   │   └── vector_store.py     #   Postgres + pgvector operations
│   │
│   ├── retrieval/              # Product retrieval
│   │   ├── product_retriever.py #  Combine filter + search
│   │   ├── hybrid_search.py    #   Semantic + keyword search
│   │   ├── filter_engine.py    #   Extract filters from NL query
│   │   ├── similarity_scorer.py #  Composite scoring
│   │   └── reranker.py         #   Cross-encoder reranking
│   │
│   ├── generation/             # LLM generation
│   │   ├── llm_client.py       #   Multi-provider (Anthropic, OpenAI)
│   │   ├── response_parser.py  #   Parse JSON from LLM output
│   │   ├── guardrails.py       #   Legacy input/output helper (superseded by src/guardrails/)
│   │   └── prompt_templates/
│   │       ├── recommend_prompt.py
│   │       ├── compare_prompt.py
│   │       └── review_summary_prompt.py
│   │
│   ├── guardrails/              # Non-LLM guardrails (input/context/output) - see GUARDRAIL_PLAN.md
│   │   ├── types.py             #   GuardrailAction, GuardrailResult (allow/sanitize/block contract)
│   │   ├── base.py              #   BaseGuardrail (ABC), GuardrailChain
│   │   ├── config.py            #   GuardrailConfig - all thresholds in one place
│   │   ├── exceptions.py        #   InputGuardrailBlocked
│   │   ├── logging_utils.py     #   Structured guardrail=... log helper
│   │   ├── fallback.py          #   Deterministic no-LLM fallback responses
│   │   ├── input/                #   normalize / injection / heuristics -> build_input_chain()
│   │   ├── context/              #   sanitize_text_field() for retrieved product text
│   │   └── output/               #   RecommendLLMOutput/CompareLLMOutput schemas, validator, grounding
│   │
│   ├── pipeline/               # Orchestration layer
│   │   ├── rag_router.py       #   Classify query → pipeline
│   │   ├── config.py           #   PipelineConfig dataclass
│   │   ├── recommend_pipeline.py
│   │   ├── compare_pipeline.py
│   │   ├── recommend/          #   Recommendation domain logic
│   │   │   ├── engine.py       #     Main recommend engine
│   │   │   ├── user_intent_parser.py
│   │   │   ├── scoring.py      #     Multi-criteria scoring
│   │   │   └── personalization.py
│   │   └── compare/            #   Comparison domain logic
│   │       ├── comparator.py
│   │       ├── spec_aligner.py
│   │       ├── formatter.py
│   │       └── pros_cons_extractor.py
│   │
│   └── utils/
│       ├── logger.py
│       ├── cache.py
│       └── helpers.py
│
├── api/                        # FastAPI layer
│   ├── app.py                  #   Entry point
│   ├── schemas.py              #   Pydantic request/response models
│   ├── deps.py                 #   Dependency injection
│   ├── routes/
│   │   ├── recommend.py        #   POST /api/recommend
│   │   ├── compare.py          #   POST /api/compare
│   │   └── search.py           #   POST /api/search
│   └── middleware/
│       ├── rate_limit.py
│       └── error_handler.py
│
├── tests/
│   ├── conftest.py             # Shared fixtures
│   ├── unit/
│   └── integration/
│
├── evaluation/                 # RAG quality evaluation
│   ├── eval_recommend.py
│   ├── eval_compare.py
│   └── test_case/
│       ├── test_cases_recommend.json
│       └── test_cases_compare.json
│
├── scripts/                    # CLI scripts
│   ├── crawl.py                #   Crawl raw data into data/raw/crawled
│   ├── ingest.py               #   Ingest data into vector store
│   └── seed.py                 #   Seed sample data
│
├── configs/
│   ├── settings.yaml
│   ├── crawler.yaml            #   Crawler sources & politeness settings
│   ├── product_categories.yaml
│   └── scoring_weights.yaml
│
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
│
└── data/
    ├── raw/products/
    ├── raw/crawled/            #   Raw crawler output (gitignored)
    └── processed/
```

## Key Patterns

- **Imports**: Always use absolute imports from project root, e.g. `from src.retrieval.filter_engine import FilterEngine`.
- **Config**: `PipelineConfig` dataclass loaded from `configs/settings.yaml`. Access via `api/deps.py` factory functions.
- **LLM calls**: Go through `src/generation/llm_client.py` (supports Anthropic + OpenAI). Never call LLM APIs directly.
- **Vector DB**: Go through `src/embedding/vector_store.py`. Postgres + pgvector (HNSW, cosine similarity); connection via `DATABASE_URL` env var or `vector_db_url` in settings.
- **Prompt templates**: Stored as module-level constants (`SYSTEM_PROMPT`, `USER_PROMPT_TEMPLATE`) in `src/generation/prompt_templates/`.
- **API dependencies**: Use factory functions in `api/deps.py` (e.g. `get_retriever()`, `get_llm_client()`).
- **User-facing text**: Vietnamese. Code/comments/docstrings: English.
- **Guardrails**: Non-LLM input/context/output validation lives in `src/guardrails/` (see
  `GUARDRAIL_PLAN.md`). Both `RecommendPipeline` and `ComparePipeline` run the input chain first
  (raises `InputGuardrailBlocked`, mapped to HTTP 422 in the routes), sanitize retrieved product
  text before prompting, then validate + ground the LLM's JSON output before returning it - on
  any output failure they fall back to a deterministic response instead of calling the LLM again.

## CI / Workflow Compliance (MANDATORY)

Any code you generate or edit MUST pass the GitHub Actions workflows in `.github/workflows/`
**before it is considered done**. Do not hand back code that would turn the CI red. When you
finish a change, mentally (or actually) run the local equivalents below and fix anything they
would flag.

- **Lint — `ci.yml` (ruff).** No unused imports (`F401`) or unused variables (`F841`); no
  undefined names. Verify with `uvx ruff check .`. Run `uvx ruff format .` so formatting is
  clean too.
- **Type check — `ci.yml` (mypy).** Keep full type hints on signatures; avoid new type errors
  even though the step is currently advisory (`uv run --with mypy mypy src api`).
- **Tests — `ci.yml` (pytest).** Existing tests must still pass and new logic needs tests.
  Verify with `uv run pytest tests/`. Tests must not require real secrets or a live network.
- **Security — `bandit.yml`.** No MEDIUM+ findings. Specifically: use `hashlib.md5(..., usedforsecurity=False)`
  for non-security hashing; build SQL with parameterized `%s` placeholders (never interpolate
  user input); only trusted, internal identifiers may be interpolated. Verify with
  `uvx bandit -r src api scripts -ll -ii -s B608`.
- **Secrets — `gitleaks.yml`.** Never commit API keys, tokens, passwords, or `.env`. Read secrets
  from environment variables; keep `.env` gitignored and use `.env.example` for placeholders.
- **Dependencies — `pip-audit.yml` + Dependabot.** Add/remove deps only via `uv add` / `uv remove`,
  then keep `uv.lock` in sync with `uv lock`. Do not introduce vulnerable or unused packages;
  after changing dependencies run `uvx pip-audit`.
- **SAST / containers — `codeql.yml`, `trivy.yml`.** Avoid injection-prone patterns (unsafe
  `subprocess`, `eval`, unsanitized SQL/paths) and follow Dockerfile best practices.
- **Docs — `docs.yml`.** Docs must build with `uv run mkdocs build --strict` (fails on broken
  links/nav). Keep `nav` in `mkdocs.yml` in sync with files under `docs/`, and add a matching
  `.vi.md` for every new English page.

Rule of thumb: if `uvx ruff check .`, `uvx bandit -r src api scripts -ll -ii -s B608`,
`uv run pytest tests/`, and `uv run mkdocs build --strict` would all pass, the change is ready.
