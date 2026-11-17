"""API endpoints for Analytics Metrics, Coverage Reports, and Data Exports."""


from fastapi import APIRouter, Depends, Query, Response

from insightbot.api.deps import (
    get_analytics_service,
    get_export_service,
    require_viewer,
)
from insightbot.models.analytics import AnalyticsOverviewReport
from insightbot.models.export import ExportFormat
from insightbot.models.user import User
from insightbot.modules.analytics.export import ExportService
from insightbot.modules.analytics.service import AnalyticsService

router = APIRouter(tags=["analytics"])


@router.get("/api/analytics/overview", response_model=AnalyticsOverviewReport)
def get_analytics_overview(
    current_user: User = Depends(require_viewer),
    analytics_service: AnalyticsService = Depends(get_analytics_service),
) -> AnalyticsOverviewReport:
    """
    Retrieve comprehensive analytics overview, source coverage percentages,
    language breakdown, 30-day timeline trends, and Defect A13/A14 metrics.
    """
    return analytics_service.get_overview_report()


@router.get("/api/export/articles")
def export_articles(
    format: ExportFormat = Query(ExportFormat.CSV, description="Export format (csv, jsonl, markdown)"),
    q: str | None = Query(None, description="Optional search query filter"),
    source_id: str | None = Query(None, description="Optional source filter"),
    language: str | None = Query(None, description="Optional language filter"),
    limit: int = Query(500, ge=1, le=1000, description="Max articles to export (bounded <= 1000)"),
    current_user: User = Depends(require_viewer),
    export_service: ExportService = Depends(get_export_service),
) -> Response:
    """
    Export articles with CSV formula protection, bounded pagination,
    and source display policy enforcement.
    """
    content, media_type, manifest = export_service.export_articles(
        export_format=format,
        query=q,
        source_id=source_id,
        language=language,
        limit=limit,
    )

    filename = f"insightbot_articles_{manifest.export_id[:8]}.{format.value}"
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "X-Export-ID": manifest.export_id,
        "X-Export-Count": str(manifest.total_exported),
    }

    return Response(content=content, media_type=media_type, headers=headers)


@router.get("/api/export/stories")
def export_stories(
    format: ExportFormat = Query(ExportFormat.CSV, description="Export format (csv, jsonl, markdown)"),
    status: str | None = Query(None, description="Optional story status filter"),
    limit: int = Query(100, ge=1, le=500, description="Max stories to export"),
    current_user: User = Depends(require_viewer),
    export_service: ExportService = Depends(get_export_service),
) -> Response:
    """Export story clusters with multi-source metadata."""
    content, media_type, manifest = export_service.export_stories(
        export_format=format,
        status=status,
        limit=limit,
    )

    filename = f"insightbot_stories_{manifest.export_id[:8]}.{format.value}"
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "X-Export-ID": manifest.export_id,
        "X-Export-Count": str(manifest.total_exported),
    }

    return Response(content=content, media_type=media_type, headers=headers)
