# =============================================================================
# app/schemas/ai_copilot.py
# -----------------------------------------------------------------------------
# Request/response models for the AI Copilot chat endpoint.
# =============================================================================

from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    messages: List[ChatMessage] = Field(min_length=1)


class ChatResponse(BaseModel):
    reply: str
