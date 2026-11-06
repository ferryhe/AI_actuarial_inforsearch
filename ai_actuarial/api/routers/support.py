from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/support/capabilities")
def api_support_capabilities(request: Request):
    return {
        "feedback_enabled": bool(getattr(request.app.state, "feedback_enabled", False)),
        "assistant_enabled": bool(getattr(request.app.state, "assistant_enabled", False)),
    }
