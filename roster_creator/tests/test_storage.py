from roster_creator.storage import load_roster, save_roster
from roster_creator.validator import Roster, RosterEntry


def test_save_and_load_roster_round_trip(tmp_path):
    roster = Roster(
        faction_id="adeptus-astartes",
        detachment_id="gladius-task-force",
        points_limit=1000,
        entries=[
            RosterEntry(
                instance_id="a1",
                datasheet_id="Captain",
                size=1,
                enhancement="Artificer Armour",
                is_warlord=True,
            ),
        ],
    )
    filepath = tmp_path / "roster.json"

    save_roster(roster, str(filepath))

    assert load_roster(str(filepath)) == roster
