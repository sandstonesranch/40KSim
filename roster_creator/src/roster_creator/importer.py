from .validator import Roster, RosterEntry


def import_simple_list(data: dict) -> Roster:
    """
    Converts a simple dictionary (simulating a NewRecruit file)
    into our internal Roster object.
    """
    entries = []
    for i, unit_data in enumerate(data.get("units", [])):
        entry = RosterEntry(
            instance_id=f"imported-{i}",
            datasheet_id=unit_data["name"],
            size=unit_data.get("size", 1),
            is_warlord=unit_data.get("is_warlord", False),
            enhancement=unit_data.get("enhancement", None),
        )
        entries.append(entry)

    return Roster(
        faction_id=data.get("faction", "adeptus-astartes"),
        detachment_id=data.get("detachment", "gladius-task-force"),
        points_limit=data.get("points_limit", 2000),
        entries=entries,
    )
