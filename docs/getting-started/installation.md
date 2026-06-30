# Installation

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- API keys for Anthropic and/or OpenAI

## Install uv

=== "Windows"

    ```powershell
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    ```

=== "macOS / Linux"

    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

## Clone and Install

```bash
git clone https://github.com/nxhawk/rag-product-recommend.git
cd rag-product-recommend
uv sync
```

This installs all dependencies from `pyproject.toml` and creates a virtual environment automatically (like `npm install`).

## Environment Variables

Copy the example env file and fill in your API keys:

```bash
cp .env.example .env
```

Required variables:

| Variable             | Description                |
| -------------------- | -------------------------- |
| `ANTHROPIC_API_KEY`  | Anthropic API key          |
| `OPENAI_API_KEY`     | OpenAI API key (embedding) |

## Install Dev Dependencies

```bash
uv sync --group dev
```

## Install Docs Dependencies

```bash
uv sync --group docs
```
