from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from ..deps import AuthContext, require_permissions
from ..services.rag_admin import RagAdminError
from ..services.ready_data_automation import set_ready_data_automation


router = APIRouter()


def _db_path(request: Request) -> str:
    db_path = str(getattr(request.app.state, "db_path", "") or "")
    if not db_path:
        raise RagAdminError("Database path is unavailable", status_code=500)
    return db_path


@router.put("/rag/knowledge-bases/{kb_id}/agentic-ready-automation")
def api_set_ready_data_automation(
    kb_id: str,
    payload: dict[str, object],
    request: Request,
    auth: AuthContext = Depends(require_permissions("config.write")),
):
    try:
        return set_ready_data_automation(
            db_path=_db_path(request),
            kb_id=kb_id,
            payload=payload,
            headers=dict(request.headers),
            auth=auth,
        )
    except RagAdminError as exc:
        return JSONResponse(status_code=exc.status_code, content={"error": exc.message})
