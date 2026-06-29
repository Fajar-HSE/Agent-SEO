# SEO Agent Platform

AI Agent Automation Platform untuk mengotomasi riset, pembuatan konten, optimasi SEO, review, dan publikasi ke WordPress.

---

## Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Setup environment
```bash
cp .env.example .env
# Edit .env dan isi API keys
```

### 3. Jalankan workflow
```bash
# Full SEO pipeline (9 steps)
python main.py run seo_article --keyword="tips SEO 2025"

# Simple 3-step pipeline
python main.py run simple_article --keyword="belajar Python"

# Dry run (cek workflow tanpa eksekusi)
python main.py run seo_article --keyword="test" --dry-run

# Lihat semua workflow
python main.py list
```

---

## Arsitektur

```
User Input (keyword)
    ↓
Workflow Engine (main.py)
    ↓
LLM Gateway (gateway/)
    ├── Router — provider selection + fallback
    ├── Cache — file-based response cache
    ├── RateLimiter — token bucket
    └── Retry — exponential backoff
    ↓
Agents (agents/)
    ├── Keyword Agent   → keyword research
    ├── Research Agent  → context gathering
    ├── Planner Agent   → outline creation
    ├── Writer Agent    → content writing
    ├── SEO Agent       → SEO optimization
    ├── Reviewer Agent  → quality review
    ├── Approval Agent  → human approval
    ├── Publisher Agent → WordPress publish
    └── Monitor Agent   → metrics & health
    ↓
Memory (memory/)
    ├── SessionMemory   → per-workflow state
    ├── ProjectMemory   → brand voice, SOP, rules
    └── LongTermMemory  → cross-workflow history
```

---

## Provider Support

| Provider       | API Key Env         | Free Tier | Notes                      |
|---------------|---------------------|-----------|----------------------------|
| HuggingFace   | `HF_API_TOKEN`      | ✅ Yes    | Default provider           |
| OpenRouter    | `OPENROUTER_API_KEY`| ✅ Yes    | Multi-model, has free models|
| Ollama        | —                   | ✅ Yes    | Local, unlimited            |

Fallback order: `huggingface → openrouter → ollama`

---

## Human Approval

Workflow `seo_article` pauses sebelum publish untuk human review.

```bash
# Skip approval (CI/automation mode)
NO_HUMAN_APPROVAL=1 python main.py run seo_article --keyword="test"
```

---

## WordPress Publishing

Set env vars di `.env`:
```
WP_URL=https://your-site.com
WP_USERNAME=your_username
WP_APP_PASSWORD=xxxx xxxx xxxx xxxx
```

Default publish sebagai `draft`. Ubah ke `publish` untuk langsung live.

---

## Project Structure

```
agents/          Agent implementations
  approval/      Human approval checkpoint
  keyword/       Keyword research
  monitor/       Metrics & health tracking
  planner/       Outline generation
  publisher/     WordPress publisher
  research/      Context research
  reviewer/      Quality review
  seo/           SEO optimization
  writer/        Content writing
config/
  agents/        Per-agent YAML configs
  providers.yaml LLM provider settings
  settings.yaml  Global settings
gateway/         LLM abstraction layer
knowledge/       Knowledge base loader
logs/            Execution logs + monitor reports
memory/          Session, project, long-term memory
prompts/         System prompts (separate from code)
schemas/         Pydantic data contracts
security/        Input/output guards
workflows/       YAML workflow definitions
```

---

## Security Features

- **Input Guard**: Prompt injection detection, input length limit
- **Output Guard**: PII detection, hallucination signal detection
- **Rate Limiting**: Token bucket per provider
- **API Key Protection**: Keys read from env vars only, never logged
- **Human Approval**: Mandatory review before publish
