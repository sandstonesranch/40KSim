import json
from dataclasses import asdict
from .validator import Roster, RosterEntry


def save_roster(roster: Roster, filepath: str) -> None:
    """Saves a Roster object to a JSON file."""
    with open(filepath, "w") as f:
        json.dump(asdict(roster), f, indent=2)


def load_roster(filepath: str) -> Roster:
    """Loads a Roster object from a JSON file."""
    with open(filepath, "r") as f:
        data = json.load(f)

    # Reconstruct the RosterEntry dataclasses
    entries = [RosterEntry(**entry_data) for entry_data in data.get("entries", [])]

    # Reconstruct the main Roster dataclass
    return Roster(
        faction_id=data["faction_id"],
        detachment_id=data["detachment_id"],
        points_limit=data["points_limit"],
        entries=entries,
    )
