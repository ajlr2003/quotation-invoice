from __future__ import annotations

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import AuditMixin


class ConfigListItem(AuditMixin, Base):
    """A single value in a configurable named lookup list.

    Backs the various small "Configuration" screens scattered across the
    app that are all structurally the same thing — a short list of named
    values staff pick from (Product Categories, Units of Measure,
    Packagings, Payment Terms, Project Tags, etc.) — rather than giving
    each one its own bespoke table.
    """

    __tablename__ = "config_list_items"

    # e.g. "product_category" | "unit_of_measure" | "packaging" |
    #      "payment_terms" | "project_tag"
    list_type: Mapped[str] = mapped_column(String(50), index=True)
    value: Mapped[str] = mapped_column(String(150))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
