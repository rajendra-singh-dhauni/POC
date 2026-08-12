# CGR Lite - FastAPI + React

This repository contains the Phase-1 scaffolding for the Code-Graph-RAG Lite prototype (Dart-focused). It provides a backend FastAPI service to clone a GitHub repo and run a Tree-sitter based Dart parser, a React frontend to submit repos and review results, and a Gemini (Google) wrapper for LLM-powered generation.

Environment variables
- GEMINI_API_KEY — your Gemini API key (set on the host)
- GEMINI_MODEL — e.g., gemini-flash-lite-latest
- GIT_CLONE_TOKEN (optional, for private repo cloning)

Run backend (development)

1. Create and activate Python venv

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Start FastAPI

```bash
uvicorn server.main:app --reload --port 8000
```

Run frontend (development)

```bash
cd client
npm install
npm start
```

Notes
- On first parse run the Tree-sitter Dart grammar will be cloned and built locally (requires cmake and a C compiler).
- Provide GEMINI_API_KEY and GEMINI_MODEL environment variables for Gemini usage.
