import pytest
from wh40kdc import Dataset
from roster_creator.validator import (
    Roster, RosterEntry, validate, compute_points
)


@pytest.fixture(scope="module")
def ds():
    return Dataset.embedded()


def make_roster(points_limit, entries):
    return Roster(
        faction_id="adeptus-astartes",
        detachment_id="gladius-task-force",
        points_limit=points_limit,
        entries=entries,
    )


# ---------- points rule ----------

def test_compute_points_single_unit(ds):
    roster = make_roster(500, [RosterEntry(instance_id="a1", datasheet_id="Intercessor Squad", size=5)])
    assert compute_points(roster, ds) == 80


def test_points_within_limit_no_violations(ds):
    roster = make_roster(500, [
        RosterEntry(instance_id="a1", datasheet_id="Captain", size=1, is_warlord=True),
    ])
    assert validate(roster, ds) == []


def test_points_exceeded_returns_violation(ds):
    roster = make_roster(50, [
        RosterEntry(instance_id="a1", datasheet_id="Captain", size=1, is_warlord=True),
    ])
    violations = validate(roster, ds)
    assert len(violations) == 1
    assert violations[0].code == "POINTS_EXCEEDED"


# ---------- warlord rules ----------

def test_no_warlord_returns_violation(ds):
    roster = make_roster(500, [
        RosterEntry(instance_id="a1", datasheet_id="Captain", size=1),
    ])
    violations = validate(roster, ds)
    assert len(violations) == 1
    assert violations[0].code == "NO_WARLORD"


def test_multiple_warlords_returns_violation(ds):
    roster = make_roster(500, [
        RosterEntry(instance_id="a1", datasheet_id="Captain", size=1, is_warlord=True),
        RosterEntry(instance_id="a2", datasheet_id="Captain", size=1, is_warlord=True),
    ])
    codes = {v.code for v in validate(roster, ds)}
    assert "MULTIPLE_WARLORDS" in codes


def test_warlord_must_be_character(ds):
    # Intercessors are not Characters, so they can't be the Warlord
    roster = make_roster(500, [
        RosterEntry(instance_id="a1", datasheet_id="Intercessor Squad", size=5, is_warlord=True),
    ])
    violations = validate(roster, ds)
    assert len(violations) == 1
    assert violations[0].code == "WARLORD_NOT_CHARACTER"
    assert violations[0].entry_id == "a1"


def test_valid_character_warlord_passes(ds):
    # Captains are Characters, so they are valid
    roster = make_roster(500, [
        RosterEntry(instance_id="a1", datasheet_id="Captain", size=1, is_warlord=True),
        RosterEntry(instance_id="a2", datasheet_id="Intercessor Squad", size=5),
    ])
    assert validate(roster, ds) == []


# ---------- Epic Hero rules ----------

def test_duplicate_epic_hero_fails(ds):
    # Marneus Calgar is an Epic Hero, taking two should fail
    roster = make_roster(1000, [
        RosterEntry(instance_id="a1", datasheet_id="Marneus Calgar in Armour of Antilochus", size=1, is_warlord=True),
        RosterEntry(instance_id="a2", datasheet_id="Marneus Calgar in Armour of Antilochus", size=1),
    ])
    violations = validate(roster, ds)
    codes = {v.code for v in violations}
    assert "DUPLICATE_EPIC_HERO" in codes


def test_unique_epic_hero_passes(ds):
    # One Epic Hero and one regular Captain is fine
    roster = make_roster(1000, [
        RosterEntry(instance_id="a1", datasheet_id="Marneus Calgar in Armour of Antilochus", size=1, is_warlord=True),
        RosterEntry(instance_id="a2", datasheet_id="Captain", size=1),
    ])
    violations = validate(roster, ds)
    codes = {v.code for v in violations}
    assert "DUPLICATE_EPIC_HERO" not in codes


# ---------- Unit Size rules ----------

def test_invalid_unit_size_fails(ds):
    # A Captain is a single model, so size=5 is invalid
    roster = make_roster(500, [
        RosterEntry(instance_id="a1", datasheet_id="Captain", size=5, is_warlord=True),
    ])
    violations = validate(roster, ds)
    codes = {v.code for v in violations}
    assert "INVALID_UNIT_SIZE" in codes


def test_valid_unit_size_passes(ds):
    # Intercessors can be taken in squads of 5
    roster = make_roster(500, [
        RosterEntry(instance_id="a1", datasheet_id="Captain", size=1, is_warlord=True),
        RosterEntry(instance_id="a2", datasheet_id="Intercessor Squad", size=5),
    ])
    violations = validate(roster, ds)
    codes = {v.code for v in violations}
    assert "INVALID_UNIT_SIZE" not in codes


def test_range_priced_unit_size_is_valid_and_costed(ds):
    roster = Roster(
        faction_id="adepta-sororitas",
        detachment_id="penitent-host",
        points_limit=500,
        entries=[RosterEntry(instance_id="a1", datasheet_id="arco-flagellants", size=7)],
    )

    assert compute_points(roster, ds) == 140
    codes = {violation.code for violation in validate(roster, ds)}
    assert "INVALID_UNIT_SIZE" not in codes


# ---------- Rule of Three ----------

def test_rule_of_three_fails(ds):
    # Terminators are not Battleline, so taking 4 should fail
    roster = make_roster(2000, [
        RosterEntry(instance_id="a1", datasheet_id="Captain", size=1, is_warlord=True),
        RosterEntry(instance_id="a2", datasheet_id="Terminator Squad", size=5),
        RosterEntry(instance_id="a3", datasheet_id="Terminator Squad", size=5),
        RosterEntry(instance_id="a4", datasheet_id="Terminator Squad", size=5),
        RosterEntry(instance_id="a5", datasheet_id="Terminator Squad", size=5),
    ])
    violations = validate(roster, ds)
    codes = {v.code for v in violations}
    assert "RULE_OF_THREE" in codes


def test_rule_of_three_battleline_passes(ds):
    # Intercessors have the BATTLELINE keyword, so taking 4 is allowed
    roster = make_roster(2000, [
        RosterEntry(instance_id="a1", datasheet_id="Captain", size=1, is_warlord=True),
        RosterEntry(instance_id="a2", datasheet_id="Intercessor Squad", size=5),
        RosterEntry(instance_id="a3", datasheet_id="Intercessor Squad", size=5),
        RosterEntry(instance_id="a4", datasheet_id="Intercessor Squad", size=5),
        RosterEntry(instance_id="a5", datasheet_id="Intercessor Squad", size=5),
    ])
    violations = validate(roster, ds)
    codes = {v.code for v in violations}
    assert "RULE_OF_THREE" not in codes


# ---------- Enhancement rules ----------

def test_enhancement_on_non_character_fails(ds):
    # Intercessors are not Characters, so they can't take an enhancement
    roster = make_roster(500, [
        RosterEntry(instance_id="a1", datasheet_id="Captain", size=1, is_warlord=True),
        RosterEntry(instance_id="a2", datasheet_id="Intercessor Squad", size=5, enhancement="Artificer Armour"),
    ])
    violations = validate(roster, ds)
    codes = {v.code for v in violations}
    assert "ENHANCEMENT_ON_NON_CHARACTER" in codes


def test_enhancement_cap_exceeded_fails(ds):
    # Strike Force allows 4 enhancements; taking 5 should fail.
    roster = make_roster(2000, [
        RosterEntry(instance_id="a1", datasheet_id="Captain", size=1, is_warlord=True, enhancement="Artificer Armour"),
        RosterEntry(instance_id="a2", datasheet_id="Captain", size=1, enhancement="Bolter Discipline"),
        RosterEntry(instance_id="a3", datasheet_id="Captain", size=1, enhancement="Adept of the Codex"),
        RosterEntry(instance_id="a4", datasheet_id="Captain", size=1, enhancement="Fire Discipline"),
        RosterEntry(instance_id="a5", datasheet_id="Captain", size=1, enhancement="Enhancement Five"),
    ])
    violations = validate(roster, ds)
    codes = {v.code for v in violations}
    assert "ENHANCEMENT_CAP_EXCEEDED" in codes


def test_valid_enhancements_pass(ds):
    # 2 enhancements on valid characters is perfectly legal
    roster = make_roster(1000, [
        RosterEntry(instance_id="a1", datasheet_id="Captain", size=1, is_warlord=True, enhancement="Artificer Armour"),
        RosterEntry(instance_id="a2", datasheet_id="Captain", size=1, enhancement="Bolter Discipline"),
    ])
    violations = validate(roster, ds)
    codes = {v.code for v in violations}
    assert "ENHANCEMENT_ON_NON_CHARACTER" not in codes
    assert "ENHANCEMENT_CAP_EXCEEDED" not in codes


# ---------- Faction rules ----------

def test_faction_mismatch_fails(ds):
    # Roster is Space Marines, but this entry is a Necron unit
    roster = make_roster(1000, [
        RosterEntry(instance_id="a1", datasheet_id="Captain", size=1, is_warlord=True),
        RosterEntry(instance_id="a2", datasheet_id="Necron Warriors", size=10),
    ])
    violations = validate(roster, ds)
    codes = {v.code for v in violations}
    assert "FACTION_MISMATCH" in codes


def test_same_faction_passes(ds):
    # Both units are Space Marines
    roster = make_roster(1000, [
        RosterEntry(instance_id="a1", datasheet_id="Captain", size=1, is_warlord=True),
        RosterEntry(instance_id="a2", datasheet_id="Intercessor Squad", size=5),
    ])
    violations = validate(roster, ds)
    codes = {v.code for v in violations}
    assert "FACTION_MISMATCH" not in codes