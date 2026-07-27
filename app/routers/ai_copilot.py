# =============================================================================
# app/routers/ai_copilot.py
# -----------------------------------------------------------------------------
# POST /api/v1/ai/chat — send a conversation to Claude, grounded with a live
# snapshot of this app's own KPIs. Returns 503 if ANTHROPIC_API_KEY isn't set.
# =============================================================================

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.schemas.ai_copilot import ChatRequest, ChatResponse
from app.services import ai_copilot_service

router = APIRouter()


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Chat with the AI Copilot",
)
async def chat(
    payload: ChatRequest,
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    reply = await ai_copilot_service.get_chat_reply(db, payload.messages)
    return ChatResponse(reply=reply)
