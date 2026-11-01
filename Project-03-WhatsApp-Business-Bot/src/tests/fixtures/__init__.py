"""JSON payload fixtures modelled on the Evolution API v2 webhook contract.

All data in these fixtures is fictional. See the ``_comment`` field in the
JSON file for details.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

FIXTURE_FILE = Path(__file__).with_name("evolution_messages_upsert.json")


@lru_cache
def load_fixtures() -> dict[str, Any]:
    """Return every fixture, keyed by name."""
    return json.loads(FIXTURE_FILE.read_text(encoding="utf-8"))


def load(name: str) -> Any:
    """Return a single fixture by name."""
    return load_fixtures()[name]


def names() -> list[str]:
    """Return the fixture names, excluding the documentation entry."""
    return [key for key in load_fixtures() if not key.startswith("_")]
