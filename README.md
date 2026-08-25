# SJ_AI

Chat over NSE filings in Postgres. The UI is the StockJarvis page (`app/web/`) with no login. If filings cannot answer: `This information is not with us.`

```bash
source .venv/bin/activate
PYTHONPATH=. python -m app.main
```

Open http://127.0.0.1:8000 (or http://0.0.0.0:8000). Secrets stay in `.env` (see `.env.example`).

How the chatbot works (for teammates): [docs/codebase-guide.md](docs/codebase-guide.md).


