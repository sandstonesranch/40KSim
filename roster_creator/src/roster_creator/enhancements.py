"""Enhancement lookup shared by the API and the validator.

The embedded wh40kdc dataset is the source of truth for *which* enhancements a
detachment has, what they cost, and who may take them. The 40k MCP server only
supplies human-readable rule text, and only for the editions it covers, so it is
treated as an optional overlay. If it is missing or out of date, enhancements
still appear (name, points, eligibility) and only the prose is absent.

Rules encoded here (from the dataset's own fields):
  * `keyword_restrictions` is an AND list: the unit must carry every keyword.
    (242 non-Upgrade enhancements list several, e.g. ['Adeptus Astartes', 'Infantry'].)
    A "keyword" is matched against the unit's keywords, faction keywords and name.
  * A normal enhancement goes on a non-Epic-Hero CHARACTER.
  * An Upgrade (`upgrade_tag`) goes on non-CHARACTER units, up to `max_targets`
    copies, and uses a single enhancement slot however many copies are taken.
"""
from __future__ import annotations

import difflib
import re
from typing import Any, Iterable, Optional

_UPGRADE_SUFFIX = re.compile(r"\s*\(upgrade\)\s*$", re.IGNORECASE)
DEFAULT_UPGRADE_COPIES = 3


def base_name(name: str) -> str:
    """Normalised name for matching across sources.

    The dataset says 'Plagueveil (Upgrade)'; MCP text says 'Plagueveil'.
    """
    cleaned = (name or "").replace("’", "'").strip()
    return _UPGRADE_SUFFIX.sub("", cleaned).casefold()


def is_upgrade(enhancement: Any) -> bool:
    return bool(enhancement.get("upgrade_tag"))


def max_copies(enhancement: Any) -> int:
    """How many units may carry this enhancement."""
    if not is_upgrade(enhancement):
        return 1
    return enhancement.get("max_targets") or DEFAULT_UPGRADE_COPIES


def unit_keyword_set(unit: Any) -> set[str]:
    return (
        {k.upper() for k in unit.keywords}
        | {k.upper() for k in unit.faction_keywords}
        | {unit.name.upper()}
    )


def restrictions_met(unit: Any, enhancement: Any) -> bool:
    need = {k.upper() for k in (enhancement.get("keyword_restrictions") or [])}
    return need <= unit_keyword_set(unit)


def eligible_for_unit(unit: Any, enhancement: Any) -> bool:
    keywords = {k.upper() for k in unit.keywords}
    is_character = "CHARACTER" in keywords
    if is_upgrade(enhancement):
        if is_character:
            return False
    elif not is_character or "EPIC HERO" in keywords:
        return False
    return restrictions_met(unit, enhancement)


def detachment_enhancements(ds: Any, detachment: Optional[dict]) -> list[Any]:
    """Enhancement records for a detachment, in dataset order. Never raises."""
    found = []
    for enhancement_id in (detachment or {}).get("enhancement_ids", []):
        enhancement = ds.enhancements.find(enhancement_id)
        if enhancement is not None:
            found.append(enhancement)
    return found


def enhancement_view(
    enhancement: Any,
    unit: Any = None,
    description: str = "",
    source: str = "wh40kdc",
) -> dict:
    view = {
        "id": enhancement.get("id"),
        "name": enhancement.get("name"),
        "cost": enhancement.get("cost") or 0,
        "upgrade": is_upgrade(enhancement),
        "max_targets": max_copies(enhancement),
        "keyword_restrictions": list(enhancement.get("keyword_restrictions") or []),
        "points_provisional": bool(enhancement.get("points_provisional")),
        "description": description,
        "description_available": bool(description.strip()),
        "source": source,
    }
    if unit is not None:
        view["eligible"] = eligible_for_unit(unit, enhancement)
    return view


def mcp_entries_for(entries: Iterable[dict], detachment_name: str) -> list[dict]:
    wanted = (detachment_name or "").replace("’", "'").casefold().strip()
    return [
        item for item in entries
        if (item.get("detachment") or "").replace("’", "'").casefold().strip() == wanted
    ]


def mcp_text_index(entries: Iterable[dict]) -> dict[str, dict]:
    return {base_name(item.get("name", "")): item for item in entries}


def format_mcp_enhancement(item: dict) -> str:
    cost = item.get("pointsCost")
    heading = f"{item.get('name', 'Enhancement')}" + (f" ({cost} pts)" if cost is not None else "")
    return f"{heading}\n{(item.get('effect') or '').strip()}".strip()


def describe_local(enhancement: Any) -> str:
    """Honest fallback text built only from dataset facts (no rules prose)."""
    parts = [f"{enhancement.get('name')} ({enhancement.get('cost') or 0} pts)."]
    if is_upgrade(enhancement):
        parts.append(
            f"Upgrade: can be taken by up to {max_copies(enhancement)} non-Character units "
            "and uses one enhancement slot."
        )
    restrictions = enhancement.get("keyword_restrictions") or []
    if restrictions:
        parts.append("Eligible units have: " + " + ".join(restrictions) + ".")
    parts.append("Rules text is not available from the 40k MCP data for this enhancement.")
    return " ".join(parts)


def near_misses(wanted: str, candidates: Iterable[str], limit: int = 5) -> list[str]:
    pool = sorted({c for c in candidates if c})
    return difflib.get_close_matches(wanted, pool, n=limit, cutoff=0.5)
