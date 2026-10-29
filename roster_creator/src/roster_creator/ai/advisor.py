from collections import Counter
from dataclasses import dataclass

from wh40kdc import Dataset

from ..validator import Roster, RosterEntry, validate
from .gap_analysis import analyze_gaps, load_tags


@dataclass
class Suggestion:
    missing_role: str
    suggested_unit_id: str
    suggested_unit_name: str
    size: int
    points: int
    reason: str


def get_suggestions(
    roster: Roster,
    archetype: str,
    ds: Dataset,
    max_suggestions: int = 3,
) -> list[Suggestion]:
    """Suggest tagged units that fill roster gaps without adding rule violations."""
    if max_suggestions <= 0:
        return []

    missing_roles = analyze_gaps(roster, archetype)
    if not missing_roles:
        return []

    _, unit_roles = load_tags()
    units_in_roster = {entry.datasheet_id for entry in roster.entries}
    existing_errors = Counter(
        violation.code
        for violation in validate(roster, ds)
        if violation.severity.value == "error"
    )
    suggestions = []

    for role in missing_roles:
        for unit_id, data in unit_roles.items():
            if role not in data["roles"] or unit_id in units_in_roster:
                continue

            unit = ds.units.find(unit_id)
            if unit is None or not unit.points:
                continue

            points_tier = unit.points[0]
            candidate = RosterEntry(
                instance_id=f"advisor-{unit_id}",
                datasheet_id=unit_id,
                size=points_tier["models"],
            )
            candidate_roster = Roster(
                faction_id=roster.faction_id,
                detachment_id=roster.detachment_id,
                points_limit=roster.points_limit,
                entries=[*roster.entries, candidate],
            )
            candidate_errors = Counter(
                violation.code
                for violation in validate(candidate_roster, ds)
                if violation.severity.value == "error"
            )
            if candidate_errors - existing_errors:
                continue

            suggestions.append(
                Suggestion(
                    missing_role=role,
                    suggested_unit_id=unit_id,
                    suggested_unit_name=unit.name,
                    size=points_tier["models"],
                    points=points_tier["cost"],
                    reason=(
                        f"Your {archetype} list is missing a '{role}' unit. "
                        "This datasheet fills that role."
                    ),
                )
            )
            break

        if len(suggestions) >= max_suggestions:
            break

    return suggestions
