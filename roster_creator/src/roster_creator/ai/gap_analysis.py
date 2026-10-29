import json
from pathlib import Path

from ..validator import Roster


def load_tags() -> tuple[dict, dict]:
    project_root = Path(__file__).resolve().parents[4]
    tags_dir = project_root / "data-schema" / "tags"

    with (tags_dir / "archetypes.json").open(encoding="utf-8") as file:
        archetypes = json.load(file)["archetypes"]
    with (tags_dir / "unit_roles.json").open(encoding="utf-8") as file:
        unit_roles = json.load(file)["units"]

    return archetypes, unit_roles


def analyze_gaps(roster: Roster, archetype_key: str) -> list[str]:
    """Return the archetype roles not covered by units in the roster."""
    archetypes, unit_roles = load_tags()

    archetype = archetypes.get(archetype_key)
    if archetype is None:
        return []

    expected_roles = set(archetype["expected_roles"])
    present_roles = {
        role
        for entry in roster.entries
        for role in unit_roles.get(entry.datasheet_id, {}).get("roles", [])
    }

    return sorted(expected_roles - present_roles)
