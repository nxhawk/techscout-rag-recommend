# Contributing

## Development Setup

```bash
git clone https://github.com/nxhawk/rag-product-recommend.git
cd rag-product-recommend
uv sync --group dev --group docs
```

## Code Style

- **Language**: All code, comments, docstrings, and documentation must be in English.
- **User-facing text** (prompts, API responses): Vietnamese.
- **Type hints**: Required on all function signatures.
- **Python version**: Use 3.11+ features (`X | Y` unions, `match` statements).
- **Imports**: Always absolute from project root (`from src.retrieval.filter_engine import FilterEngine`).
- **Package management**: Use `uv` exclusively. Add deps with `uv add <package>`.

## Adding a New Module

1. Create the module file in the appropriate `src/` subdirectory.
2. Use absolute imports.
3. Add type hints to all public functions.
4. Write docstrings in English.
5. Add unit tests in `tests/unit/<domain>/test_<module>.py`, mirroring the module path under `src/` or `api/` (see [Testing](testing.md)).
6. Update `CLAUDE.md` if the module introduces new patterns.

## Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add cross-encoder reranking
fix: handle empty query in filter engine
docs: update API endpoint documentation
test: add integration tests for compare pipeline
```

## Running Docs Locally

```bash
uv run mkdocs serve
```

Docs will be available at `http://localhost:8000`.
