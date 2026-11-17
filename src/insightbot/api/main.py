"""FastAPI application entry point for InsightBot."""

from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from insightbot.api.admin_audit import router as admin_audit_router
from insightbot.api.admin_jobs import router as admin_jobs_router
from insightbot.api.admin_sources import router as admin_sources_router
from insightbot.api.admin_users import router as admin_users_router
from insightbot.api.analytics import router as analytics_router
from insightbot.api.articles import router as articles_router
from insightbot.api.assistant import router as assistant_router
from insightbot.api.auth import router as auth_router
from insightbot.api.generation import router as generation_router
from insightbot.api.middleware import RequestIDMiddleware, setup_exception_handlers
from insightbot.api.notifications import router as notifications_router
from insightbot.api.search import router as search_router
from insightbot.api.sources import router as sources_router
from insightbot.api.stories import router as stories_router
from insightbot.api.workspace import router as workspace_router
from insightbot.config import get_settings

settings = get_settings()

app = FastAPI(
    title="InsightBot API",
    description="Multilingual news intelligence and analysis API",
    version="0.1.0",
)

# Exception handlers for structured error envelopes
setup_exception_handlers(app)

# Middlewares
app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router)
app.include_router(admin_users_router)
app.include_router(admin_sources_router)
app.include_router(admin_jobs_router)
app.include_router(admin_audit_router)
app.include_router(articles_router)
app.include_router(search_router)
app.include_router(stories_router)
app.include_router(sources_router)
app.include_router(workspace_router)
app.include_router(analytics_router)
app.include_router(generation_router)
app.include_router(notifications_router)
app.include_router(assistant_router)


@app.get("/api/health")
def health_check() -> dict[str, str]:
    """Basic health check endpoint."""
    return {
        "status": "ok",
        "env": settings.env,
        "version": "0.1.0",
    }


@app.get("/api/capabilities")
def get_capabilities() -> dict[str, Any]:
    """Inspect system capabilities, operational limits, and enabled features."""
    return {
        "version": "0.1.0",
        "languages": ["ar", "en", "ru"],
        "rtl_languages": ["ar"],
        "search_engine": "hybrid_rrf",
        "nlp_enabled": True,
        "assistant_enabled": True,
        "max_page_limit": 100,
    }


# Optional SPA Static Files Serving (Section 20: Same-Origin Production Packaging)
if settings.static_dir and settings.static_dir.is_dir():
    index_file = settings.static_dir / "index.html"
    assets_dir = settings.static_dir / "assets"
    if assets_dir.is_dir():
        from starlette.staticfiles import StaticFiles

        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    if index_file.is_file():
        from fastapi import HTTPException
        from starlette.responses import FileResponse

        @app.get("/{full_path:path}", include_in_schema=False)
        def serve_spa(full_path: str) -> FileResponse:
            """Serve single-page application with fallback for client-side routing."""
            if (
                full_path.startswith("api")
                or full_path.startswith("docs")
                or full_path.startswith("redoc")
                or full_path == "openapi.json"
            ):
                raise HTTPException(status_code=404, detail="Not Found")

            if settings.static_dir:
                target_file = settings.static_dir / full_path
                if target_file.is_file() and not full_path.endswith(".html"):
                    return FileResponse(str(target_file))
            return FileResponse(str(index_file))
