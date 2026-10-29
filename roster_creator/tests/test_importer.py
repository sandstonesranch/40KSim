import pytest
from wh40kdc import Dataset
from roster_creator.importer import import_simple_list
from roster_creator.validator import validate


@pytest.fixture(scope="module")
def ds():
    return Dataset.embedded()


def test_import_from_external_json(ds):
    # Simulate a JSON file a user might upload
    mock_json_data = {
        "faction": "adeptus-astartes",
        "detachment": "gladius-task-force",
        "points_limit": 1000,
        "units": [
            {"name": "Captain", "size": 1, "is_warlord": True},
            {"name": "Intercessor Squad", "size": 5},
            {"name": "Terminator Squad", "size": 5},
        ],
    }

    roster = import_simple_list(mock_json_data)

    assert len(roster.entries) == 3
    assert roster.entries[0].datasheet_id == "Captain"
    assert roster.entries[1].size == 5

    violations = validate(roster, ds)
    assert len(violations) == 0
