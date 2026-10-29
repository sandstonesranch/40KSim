from roster_creator.ai.gap_analysis import analyze_gaps
from roster_creator.validator import Roster, RosterEntry


def make_roster(datasheet_ids: list[str]) -> Roster:
    return Roster(
        faction_id="adeptus-astartes",
        detachment_id="gladius-task-force",
        points_limit=1000,
        entries=[
            RosterEntry(
                instance_id=f"entry-{index}",
                datasheet_id=datasheet_id,
                size=5,
                is_warlord=False,
            )
            for index, datasheet_id in enumerate(datasheet_ids)
        ],
    )


def test_gunline_missing_roles():
    roster = make_roster(["intercessor-squad"])

    gaps = analyze_gaps(roster, "gunline")

    assert "anti-tank" in gaps
    assert "screening" in gaps
    assert "objective-holder" not in gaps


def test_gunline_complete():
    roster = make_roster(
        [
            "intercessor-squad",
            "eliminator-squad",
            "incursor-squad",
        ]
    )

    gaps = analyze_gaps(roster, "gunline")

    assert gaps == []
