# =============================================================================
# app/integrations/odoo_client.py
# -----------------------------------------------------------------------------
# Async-safe Odoo XML-RPC client. Odoo's standard xmlrpc.client library is
# synchronous, so every call is dispatched to a thread pool via
# asyncio.to_thread() to avoid blocking the FastAPI event loop.
#
# Usage:
#   client = OdooClient()
#   records = await client.execute("account.move", "search_read", [[...]], {...})
#
# Authentication uses an API key (Settings → My Profile → Account Security →
# API Keys) instead of the account password for improved security.
# =============================================================================

from __future__ import annotations

import asyncio
import logging
import xmlrpc.client
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


class OdooClient:
    """Thin async wrapper around Odoo's XML-RPC API.

    Authenticates once (lazy, on first call) and caches the user ID for
    the lifetime of the instance. All RPC calls run in a thread pool so
    they do not block the asyncio event loop.

    Raises:
        RuntimeError: If Odoo credentials are not configured in .env.
        xmlrpc.client.Fault: On Odoo-side errors (access denied, bad model, etc.).
    """

    def __init__(self) -> None:
        self._url     = settings.ODOO_URL.rstrip("/")
        self._db      = settings.ODOO_DB
        self._login   = settings.ODOO_LOGIN
        self._api_key = settings.ODOO_API_KEY
        self._uid: int | None = None

    # ── Authentication ────────────────────────────────────────────────────────

    async def uid(self) -> int:
        """Return the authenticated Odoo user ID, authenticating on first call.

        Returns:
            Integer UID of the authenticated Odoo user.

        Raises:
            RuntimeError: If credentials are missing or authentication fails.
        """
        if self._uid is not None:
            return self._uid

        if not self._url or not self._db or not self._login or not self._api_key:
            raise RuntimeError(
                "Odoo credentials not configured. "
                "Set ODOO_URL, ODOO_DB, ODOO_LOGIN, ODOO_API_KEY in .env"
            )

        common = xmlrpc.client.ServerProxy(f"{self._url}/xmlrpc/2/common")
        uid = await asyncio.to_thread(
            common.authenticate, self._db, self._login, self._api_key, {}
        )
        if not uid:
            raise RuntimeError("Odoo authentication failed — check credentials and API key")

        self._uid = uid
        logger.info("Odoo authenticated as UID %s", uid)
        return uid

    # ── Core execute method ───────────────────────────────────────────────────

    async def execute(
        self,
        model: str,
        method: str,
        args: list,
        kwargs: dict | None = None,
    ) -> Any:
        """Call an Odoo model method via XML-RPC.

        Args:
            model:  Odoo model name, e.g. ``"account.move"``.
            method: Method to call, e.g. ``"search_read"``, ``"create"``.
            args:   Positional arguments list, e.g. ``[[["state", "=", "posted"]]]``.
            kwargs: Keyword arguments dict, e.g. ``{"fields": ["name"], "limit": 10}``.

        Returns:
            The raw result returned by Odoo (list, dict, int, or bool).
        """
        uid = await self.uid()
        models_proxy = xmlrpc.client.ServerProxy(f"{self._url}/xmlrpc/2/object")
        return await asyncio.to_thread(
            models_proxy.execute_kw,
            self._db, uid, self._api_key,
            model, method, args, kwargs or {},
        )

    # ── Convenience helpers ───────────────────────────────────────────────────

    async def search_read(
        self,
        model: str,
        domain: list,
        fields: list[str],
        limit: int = 100,
        order: str = "id desc",
    ) -> list[dict]:
        """Search Odoo records and return specified fields.

        Args:
            model:  Odoo model name.
            domain: Odoo domain filter, e.g. ``[["move_type", "=", "out_invoice"]]``.
            fields: List of field names to return.
            limit:  Maximum number of records (default 100).
            order:  Sort expression (default newest first).

        Returns:
            List of record dicts with only the requested fields.
        """
        return await self.execute(
            model, "search_read", [domain],
            {"fields": fields, "limit": limit, "order": order},
        )

    async def create(self, model: str, values: dict) -> int:
        """Create a single Odoo record and return its ID.

        Args:
            model:  Odoo model name.
            values: Field values for the new record.

        Returns:
            Integer ID of the newly created record.
        """
        return await self.execute(model, "create", [values])

    async def write(self, model: str, ids: list[int], values: dict) -> bool:
        """Update Odoo records by ID.

        Args:
            model:  Odoo model name.
            ids:    List of record IDs to update.
            values: Fields and new values to set.

        Returns:
            True on success.
        """
        return await self.execute(model, "write", [ids, values])

    async def action(self, model: str, method: str, ids: list[int]) -> Any:
        """Call a button/action method on a set of Odoo records.

        Used for workflow transitions like ``action_post`` (draft → posted) or
        ``action_register_payment``.

        Args:
            model:  Odoo model name.
            method: Action method name, e.g. ``"action_post"``.
            ids:    List of record IDs to act on.

        Returns:
            The Odoo action result (dict, bool, or None).
        """
        return await self.execute(model, method, [ids])


# Module-level singleton reused across requests
odoo = OdooClient()
