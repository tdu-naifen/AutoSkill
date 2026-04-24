# AutoSkill

![AutoSkill Demo](assets/demo.gif)

AI agent skills accumulate fast. Different teams write overlapping guides for the same cloud services, CLI tools, and best practices. **AutoSkill** finds that overlap automatically — extracting shared knowledge and output templates — so your agents stay lean and consistent.

## How it works

Drop in a folder of skills (each with a `SKILL.md`), and AutoSkill will:

- **Detect similar skills** using semantic embeddings — configurable model, default nomic-embed-text-v1.5 with 8192 token context
- **Extract shared knowledge** via LLM — only for skill pairs that actually overlap, not every combination
- **Detect output templates** — files that instruct agents to generate reports, plans, or other structured output
- **Produce a clean output** where skills reference shared knowledge and templates instead of duplicating content

For example, if `azure-cost` and `aws-cost` both explain tagging best practices, AutoSkill extracts that into `knowledge/cost-tagging-patterns` and links both skills to it. If `azure-cost` has a report template, it appears as a separate `templates/azure-cost-report-template`.

## Incremental by default

Adding new skills doesn't restart from scratch. AutoSkill caches embeddings and previous LLM extractions — only new skills and their new pairings get processed.

## Live dashboard

A built-in dashboard lets you watch the pipeline run and explore results:

- **Skill Graph** — skills (top), shared knowledge (middle), and templates (bottom) with hover cross-highlighting
- **Embedding Space** — interactive 3D scatter of all skills and knowledge, cross-highlighted with the graph
- **Pipeline Status** — live progress bar during ingestion

## Output

```
output/
  skills/
    azure-cost/SKILL.md                    # original skill with knowledge + template refs
    aws-serverless-eda/SKILL.md
  knowledge/
    cost-tagging-patterns/KNOWLEDGE.md     # shared knowledge extracted from similar skills
  templates/
    azure-cost-report-template/TEMPLATE.md # output template detected from skills
```

Skills keep their original content, sub-files, and metadata. `knowledge:` and `templates:` fields are added to their frontmatter pointing to the relevant shared resources.

## Quick start

```bash
uv sync
cp .env.example .env   # customize your LLM, embedding model, etc.
uv run skill-pipeline ingest ./my-skills --output output
uv run skill-pipeline dashboard
```

## Configuration

Copy `.env.example` to `.env` and customize:

```bash
# LLM — any OpenAI-compatible API (oMLX, Ollama, vLLM, OpenAI, etc.)
LLM_MODEL=gemma-4-26b-a4b-it-4bit
LLM_URL=http://127.0.0.1:1111/v1/chat/completions
LLM_API_KEY=test

# Embedding — any sentence-transformers compatible model
EMBED_MODEL=nomic-ai/nomic-embed-text-v1.5

# Similarity threshold — how similar two skills need to be for knowledge extraction (0.0-1.0)
SIMILARITY_THRESHOLD=0.75
```

All settings have sensible defaults. Without a `.env` file, AutoSkill uses a local oMLX server and nomic-embed-text-v1.5.

## Requirements

- Python 3.11+
- An OpenAI-compatible LLM API for knowledge extraction
- GPU recommended for the embedding model
