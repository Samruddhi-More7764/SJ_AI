"""StockJarvis FastAPI app: owned UI, catalog APIs, chat SSE."""

from __future__ import annotations

import json
import time
import traceback
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, Optional

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from vanna.core.user.request_context import RequestContext
from vanna.servers.base import ChatHandler, ChatRequest

from app.cache import peek_pending
from app.catalog import clamp_limit, fetch_companies, fetch_summary, fetch_tags
from app.fingerprint import fetch_derived_formulas
from app.provenance import build_provenance

WEB_DIR = Path(__file__).resolve().parent / "web"


def _request_context(chat_request: ChatRequest, http_request: Request) -> None:
    chat_request.request_context = RequestContext(
        cookies=dict(http_request.cookies),
        headers=dict(http_request.headers),
        remote_addr=http_request.client.host if http_request.client else None,
        query_params=dict(http_request.query_params),
        metadata=chat_request.metadata,
    )


def provenance_sse_payload(
    conversation_id: str,
    request_id: str,
    provenance: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "rich": {"type": "provenance", "data": provenance},
        "simple": None,
        "conversation_id": conversation_id or "",
        "request_id": request_id or "",
        "timestamp": time.time(),
    }


def _sse_response(
    handler: ChatHandler,
    chat_request: ChatRequest,
    database_url: Optional[str] = None,
) -> StreamingResponse:
    async def generate() -> AsyncGenerator[str, None]:
        conversation_id = chat_request.conversation_id or ""
        request_id = chat_request.request_id or ""
        pending_copy: Optional[Dict[str, Any]] = None
        try:
            async for chunk in handler.handle_stream(chat_request):
                conversation_id = chunk.conversation_id or conversation_id
                request_id = chunk.request_id or request_id
                yield f"data: {chunk.model_dump_json()}\n\n"
                peeked = peek_pending(conversation_id)
                if peeked and peeked.get("sql"):
                    pending_copy = dict(peeked)
            if pending_copy and pending_copy.get("sql"):
                formulas = {}
                if database_url:
                    try:
                        formulas = fetch_derived_formulas(database_url)
                    except Exception:
                        formulas = {}
                provenance = pending_copy.get("provenance")
                if formulas or not provenance:
                    provenance = build_provenance(
                        pending_copy.get("sql") or "",
                        pending_copy.get("columns") or [],
                        pending_copy.get("rows") or [],
                        derived_formulas=formulas,
                    )
                payload = provenance_sse_payload(
                    conversation_id, request_id, provenance
                )
                yield f"data: {json.dumps(payload)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as exc:
            traceback.print_exc()
            error_data = {
                "type": "error",
                "data": {"message": str(exc)},
                "conversation_id": chat_request.conversation_id or "",
                "request_id": chat_request.request_id or "",
            }
            yield f"data: {json.dumps(error_data)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def create_app(agent: Any, database_url: str) -> FastAPI:
    app = FastAPI(
        title="StockJarvis",
        description="Ask the filings.",
        version="0.1.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    handler = ChatHandler(agent)

    @app.post("/api/chat")
    @app.post("/api/vanna/v2/chat_sse")
    async def chat_sse(
        chat_request: ChatRequest, http_request: Request
    ) -> StreamingResponse:
        _request_context(chat_request, http_request)
        return _sse_response(handler, chat_request, database_url)

    @app.get("/api/catalog/summary")
    def catalog_summary() -> dict:
        return fetch_summary(database_url)

    @app.get("/api/catalog/companies")
    def catalog_companies(
        q: str = Query(default=""),
        limit: Optional[int] = Query(default=None),
    ) -> dict:
        return {
            "companies": fetch_companies(
                database_url, q=q, limit=clamp_limit(limit)
            )
        }

    @app.get("/api/catalog/tags")
    def catalog_tags(
        q: str = Query(default=""),
        limit: Optional[int] = Query(default=None),
    ) -> dict:
        return {"tags": fetch_tags(database_url, q=q, limit=clamp_limit(limit))}

    @app.get("/health")
    def health() -> dict:
        return {"status": "healthy", "service": "stockjarvis"}

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")
    return app


def run_app(app: FastAPI, host: str = "0.0.0.0", port: int = 8000) -> None:
    import uvicorn

    print("Your app is running at:")
    print(f"http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, timeout_keep_alive=120)
