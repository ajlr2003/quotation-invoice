# =============================================================================
# app/services/ai_copilot_service.py
# -----------------------------------------------------------------------------
# AI Copilot chat: a single-turn (per request) call to the Claude Messages API,
# grounded with a live snapshot of real business KPIs pulled from this app's
# own data (revenue, RFQ pipeline, inventory, expenses). No tool use / agentic
# loop — a straightforward chat completion, matching the Conversation tab's
# scope. History/Saved Prompts/Context tabs remain frontend-local by design.
# =============================================================================

from __future__ import annotations

from typing import List

import anthropic
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.sales_order import SalesOrder
from app.schemas.ai_copilot import ChatMessage
from app.services import expense_service, inventory_service, rfq_service


async def _business_context(db: AsyncSession) -> str:
    """Compact, real-data snapshot injected into the system prompt so answers
    are grounded in this business's actual numbers rather than guessed."""
    total_revenue = float(
        (await db.execute(select(func.coalesce(func.sum(SalesOrder.total), 0)))).scalar_one()
    )
    rfq_kpis = await rfq_service.get_rfq_kpis(db)
    inv_kpis = await inventory_service.get_kpis(db)
    exp_kpis = await expense_service.get_kpis(db)

    return (
        f"- Total sales revenue (all orders): SAR {total_revenue:,.0f}\n"
        f"- RFQs: {rfq_kpis.draft} draft, {rfq_kpis.sent} sent, "
        f"{rfq_kpis.awaiting_evaluation} awaiting evaluation, {rfq_kpis.awarded} awarded, "
        f"{rfq_kpis.late} overdue\n"
        f"- Inventory: {inv_kpis.total_items} items, {inv_kpis.zero_stock_count} out of stock, "
        f"{inv_kpis.low_stock_count} low stock, valuation SAR {inv_kpis.total_valuation:,.0f}\n"
        f"- Expenses: {exp_kpis.pending_count} pending approval "
        f"(SAR {exp_kpis.pending_amount:,.0f}), SAR {exp_kpis.reimbursed_amount:,.0f} reimbursed"
    )


async def get_chat_reply(db: AsyncSession, messages: List[ChatMessage]) -> str:
    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI Copilot is not configured — set ANTHROPIC_API_KEY in the backend .env to enable it.",
        )

    context = await _business_context(db)
    system_prompt = (
        "You are the AI Copilot inside Kytos Arabia's internal operations platform "
        "(procurement, sales, inventory, accounting). Answer using the live snapshot "
        "below when it's relevant to the question. If asked about something the "
        "snapshot doesn't cover, say plainly that you don't have that data rather "
        "than guessing or inventing numbers. Keep answers concise and business-focused.\n\n"
        f"Live snapshot:\n{context}"
    )

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    try:
        response = await client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=1500,
            system=system_prompt,
            thinking={"type": "adaptive"},
            output_config={"effort": "medium"},
            messages=[{"role": m.role, "content": m.content} for m in messages],
        )
    except anthropic.AuthenticationError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI Copilot authentication failed — check ANTHROPIC_API_KEY.",
        )
    except anthropic.RateLimitError:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="AI Copilot is rate-limited right now — try again shortly.",
        )
    except anthropic.APIConnectionError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI Copilot could not reach Anthropic's API.",
        )
    except anthropic.APIStatusError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI Copilot upstream error: {e.message}",
        )

    if response.stop_reason == "refusal":
        return "I'm not able to help with that request."

    text = "".join(block.text for block in response.content if block.type == "text")
    return text or "(No response generated.)"
