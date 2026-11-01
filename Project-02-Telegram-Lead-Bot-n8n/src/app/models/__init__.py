"""Доменные модели."""

from app.models.lead import Lead, LeadStatus, normalize_phone

__all__ = ["Lead", "LeadStatus", "normalize_phone"]
