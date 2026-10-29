import pytest
from wh40kdc import Dataset

from roster_creator.ai.advisor import get_suggestions
from roster_creator.validator import Roster, RosterEntry


@pytest.fixture(scope="module")
def ds():
    return Dataset.embedded()


def make_roster(points_limit: int = 1000) -> Roster:
    return Roster(
        faction_id="adeptus-astartes",
        detachment_id="gladius-task-force",
        points_limit=points_limit,
        entries=[
            RosterEntry(
                instance_id="entry-intercessors",
                datasheet_id="intercessor-squad",
                size=5,
            )
        ],
    )


def test_suggests_units_for_missing_roles(ds):
    suggestions = get_suggestions(make_roster(), "gunline", ds)

    assert [suggestion.missing_role for suggestion in suggestions] == [
        "anti-tank",
        "screening",
    ]
    assert [suggestion.suggested_unit_id for suggestion in suggestions] == [
        "eliminator-squad",
        "incursor-squad",
    ]
    assert [suggestion.points for suggestion in suggestions] == [75, 85]


def test_suggestions_obey_limit_and_exclude_units_already_in_roster(ds):
    roster = make_roster()
    roster.entries.append(
        RosterEntry(
            instance_id="entry-eliminators",
            datasheet_id="eliminator-squad",
            size=3,
        )
    )

    suggestions = get_suggestions(roster, "gunline", ds, max_suggestions=1)

    assert len(suggestions) == 1
    assert suggestions[0].missing_role == "screening"
    assert suggestions[0].suggested_unit_id == "incursor-squad"


def test_does_not_suggest_units_that_exceed_roster_points_limit(ds):
    suggestions = get_suggestions(make_roster(points_limit=80), "gunline", ds)

    assert suggestions == []


def test_unknown_archetype_and_nonpositive_limit_return_no_suggestions(ds):
    roster = make_roster()

    assert get_suggestions(roster, "unknown", ds) == []
    assert get_suggestions(roster, "gunline", ds, max_suggestions=0) == []


def test_advisor_uses_database_points_and_does_not_modify_roster(ds):
    roster = make_roster()

    suggestions = get_suggestions(roster, "gunline", ds)

    eliminator_suggestion = next(
        suggestion
        for suggestion in suggestions
        if suggestion.suggested_unit_id == "eliminator-squad"
    )
    db_unit = ds.units.find("eliminator-squad")

    assert db_unit is not None
    assert eliminator_suggestion.points == db_unit.points[0]["cost"]
    assert len(roster.entries) == 1
