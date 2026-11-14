# EchoRole

Local-first practice for realistic communication scenarios. Roleplay and
evaluation use the provider selected by `LLM_PROVIDER`: local Ollama or an
OpenAI-compatible API. Speech recognition uses a local faster-whisper model,
and browser speech synthesis speaks interviewer replies.

For current capabilities, validation results, and known gaps, see the
[project status and handoff](docs/PROJECT_STATUS.md).

## Requirements

- Python 3.11 or newer (validated on this machine with Python 3.14.0)
- Node.js 20 or newer and npm (validated with Node.js 26.13.1 and npm 11.20.0)
- Ollama and a locally installed model only when `LLM_PROVIDER=ollama`

## Quickstart

### 1. One-click Local Runner (Recommended)

After cloning the repository, launch both the backend and frontend with a single command:

- **Windows (PowerShell):**
  ```powershell
  .\run_local.ps1
  ```
- **macOS / Linux / WSL:**
  ```bash
  chmod +x run_local.sh
  ./run_local.sh
  ```

The script automatically initializes `.env` from `.env.example` (if missing), creates the SQLite data directory, runs database migrations (`alembic upgrade head`), and starts both servers:
- **Backend API:** `http://127.0.0.1:8000`
- **Frontend UI:** `http://localhost:5173`

Press `Ctrl+C` to gracefully shut down both services.

### 2. Manual Step-by-Step Setup

From the repository root, copy the recommended local configuration:

```powershell
Copy-Item .env.example .env
```

The checked-in template selects an OpenAI-compatible Groq endpoint, leaves the
API key blank, and includes a sample model ID. Confirm that the selected model
is available to your account. To use Ollama, set `LLM_PROVIDER=ollama` and
`OLLAMA_MODEL` to an installed model. [The benchmark report](docs/architecture/LLM_BENCHMARK.md)
records local benchmark coverage and remaining acceptance gaps. Change
`OLLAMA_MODEL` or `WHISPER_MODEL` in `.env` when using different local models.
The 180-second LLM timeout and 1200-token
Coach budget allow evaluation output to finish on the CPU-only benchmark
machine; evaluations run asynchronously and the frontend polls for their result.

### OpenAI-compatible cloud providers

To use a cloud provider, set `LLM_PROVIDER=openai_compatible` in `.env`, then
configure `OPENAI_BASE_URL`, `OPENAI_MODEL`, and `OPENAI_API_KEY`. The key is
blank in the template; provide your own key locally and never commit it. An
empty key omits bearer authentication, which is useful for compatible local
services. The backend sends standard `/chat/completions` requests and uses
`/models` for provider health checks.

For example, Groq uses a base URL such as
`https://api.groq.com/openai/v1`; Gemini's OpenAI-compatible API uses
`https://generativelanguage.googleapis.com/v1beta/openai/`. Use a model name
supported by the selected provider. Replace the base URL, model, and key in
your local `.env`; do not put credentials in this file in version control.

Backend, in terminal 1:

```powershell
cd backend
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Frontend, in terminal 2:

```powershell
cd frontend
npm ci
npm run dev
```

Mocks are disabled by default, so the browser calls
`http://localhost:8000/api/v1`. To opt into MSW for frontend-only work, set the
flag before starting Vite:

```powershell
$env:VITE_USE_MOCKS = "true"
npm run dev
```

Set it to `"false"` (or remove it) and restart Vite to use the real backend.
`VITE_API_BASE_URL` can override the default backend address; for example:

```powershell
$env:VITE_API_BASE_URL = "http://localhost:8000/api/v1"
```

## Validation

From `backend/`:

```powershell
python -m ruff check .
python -m mypy app
python -m pytest
```

The default pytest run excludes tests marked `llm` or `stt`; those require
separately configured local services/models. Run an opt-in group explicitly
with `python -m pytest -m stt` or `python -m pytest -m llm`.

From `frontend/`:

```powershell
npm run typecheck
npm run lint
npm test -- --run
npm run build
```

## Deployment

### Backend on Render (Free Tier - 512MB RAM)

EchoRole is optimized to run smoothly on Render Free (512MB RAM) without `faster-whisper`. When `faster-whisper` is absent from the environment, the app boots cleanly and returns `STT_UNAVAILABLE` so the frontend automatically switches to text input or browser Web Speech API.

- **Blueprint (`render.yaml`):** The repository includes `render.yaml` at the root with `rootDir: backend`.
- **Manual Render Web Service Settings:**
  - **Root Directory:** `backend` (or `echorole/backend`)
  - **Environment:** `Python 3`
  - **Build Command:** `pip install -e .`
  - **Start Command:** `mkdir -p data && alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT`
  - **Environment Variables:**
    - `LLM_PROVIDER`: `openai_compatible`
    - `OPENAI_BASE_URL`: (e.g. `https://api.groq.com/openai/v1` or `https://generativelanguage.googleapis.com/v1beta/openai/`)
    - `OPENAI_API_KEY`: your API key
    - `OPENAI_MODEL`: (e.g. `llama-3.3-70b-versatile`)
    - `CORS_ORIGINS`: `["https://your-frontend.vercel.app"]`

### Frontend on Vercel

- **Root Directory:** `frontend`
- **Framework Preset:** `Vite`
- **SPA Rewrites:** Pre-configured in `frontend/vercel.json` (`rewrites: [{"source": "/(.*)", "destination": "/index.html"}]`) so refreshing sub-pages does not trigger 404 errors.
- **Environment Variables:**
  - `VITE_API_BASE_URL`: `https://your-backend.onrender.com/api/v1`

## Branch protection

Protect `main` in GitHub repository settings: require pull requests, at least
one approval, and successful backend/frontend CI checks before merge. These
remote settings cannot be enabled by a local repository change.

Contract changes must use the `contract-change` label and update the contract,
backend schemas, canonical examples, and MSW mocks together.
