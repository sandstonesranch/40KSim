"""Boundary / edge-case tests for roster_creator.validator.

Run: cd roster_creator && python -m pytest tests/test_validator_boundaries.py -v
Tests marked BUG_* assert the CORRECT behaviour and currently fail against
validator.py; the rest pin down behaviour that already works.
"""
import pytest
from wh40kdc import Dataset
from roster_creator.validator import Roster, RosterEntry, validate, compute_points

# NOTE: all datasheet ids below are the dataset's slug ids (e.g. "captain"),
# not display names -- the existing tests pass names, which only works because
# ds.units.find() happens to accept both.


@pytest.fixture(scope="module")
def ds():
    return Dataset.embedded()


def roster(limit, *entries, faction="adeptus-astartes", detachment="gladius-task-force"):
    return Roster(faction_id=faction, detachment_id=detachment,
                  points_limit=limit, entries=list(entries))


def E(iid, ds_id, size=1, **kw):
    return RosterEntry(instance_id=iid, datasheet_id=ds_id, size=size, **kw)


def codes(r, ds):
    return [v.code for v in validate(r, ds)]


# ───────────── 1. points boundaries ─────────────

def test_points_exactly_at_limit_is_legal(ds):
    # Captain = 80 pts
    r = roster(80, E("a", "captain", is_warlord=True))
    assert compute_points(r, ds) == 80
    assert "POINTS_EXCEEDED" not in codes(r, ds)


def test_points_one_over_limit_is_illegal(ds):
    r = roster(79, E("a", "captain", is_warlord=True))
    v = [x for x in validate(r, ds) if x.code == "POINTS_EXCEEDED"]
    assert len(v) == 1 and "1 pts over" in v[0].message


@pytest.mark.parametrize("size,expected", [(5, 80), (6, 150), (10, 150)])
def test_intercessor_tier_boundaries(ds, size, expected):
    r = roster(2000, E("a", "intercessor-squad", size))
    assert compute_points(r, ds) == expected


@pytest.mark.parametrize("size", [0, 1, 4, 11, 20])
def test_intercessor_invalid_sizes(ds, size):
    r = roster(2000, E("c", "captain", is_warlord=True),
               E("a", "intercessor-squad", size))
    assert "INVALID_UNIT_SIZE" in codes(r, ds)


def test_assault_intercessor_tier_edges(ds):
    # tiers: 5-9 -> 75, 10 -> 150 (the "cheaper at 9, double at 10" cliff)
    for size, cost in [(5, 75), (9, 75), (10, 150)]:
        assert compute_points(roster(2000, E("a", "assault-intercessor-squad", size)), ds) == cost


def test_negative_size_is_invalid(ds):
    r = roster(2000, E("c", "captain", is_warlord=True), E("a", "intercessor-squad", -5))
    assert "INVALID_UNIT_SIZE" in codes(r, ds)


@pytest.mark.parametrize("squads", [11, 24, 37])   # roughly 1000 / 2000 / 3000 pts
def test_exact_fill_is_legal_and_one_point_less_is_not(ds, squads):
    entries = [E("c", "captain", is_warlord=True)] + [
        E(f"i{k}", "intercessor-squad", 5) for k in range(squads)]
    total = compute_points(roster(0, *entries), ds)
    assert total == 80 + 80 * squads
    assert "POINTS_EXCEEDED" not in codes(roster(total, *entries), ds)
    assert "POINTS_EXCEEDED" in codes(roster(total - 1, *entries), ds)


def test_BUG_invalid_size_does_not_silently_count_as_zero_points(ds):
    # compute_points() adds nothing for an out-of-tier size, so a roster full of
    # size-4 Intercessors "costs" 0 pts. INVALID_UNIT_SIZE fires, but the points
    # readout shown to the user is wrong while it does.
    r = roster(2000, E("a", "intercessor-squad", 4))
    assert compute_points(r, ds) != 0


def test_BUG_unit_count_tiers_are_ignored(ds):
    # Rhino: 65 pts each for 1-3 in the list, 75 pts each at 4+.
    # compute_points() only matches on `models`, so it always picks the first tier.
    four = roster(2000, *[E(f"r{k}", "rhino", 1) for k in range(4)])
    assert compute_points(four, ds) == 4 * 75
    three = roster(2000, *[E(f"r{k}", "rhino", 1) for k in range(3)])
    assert compute_points(three, ds) == 3 * 65


def test_BUG_enhancement_cost_is_not_counted(ds):
    # Artificer Armour = 20 pts. Captain 80 + 20 = 100 > 99.
    r = roster(99, E("a", "captain", is_warlord=True, enhancement="Artificer Armour"))
    assert compute_points(r, ds) == 100
    assert "POINTS_EXCEEDED" in codes(r, ds)


def test_BUG_unknown_datasheet_is_reported(ds):
    # Stale saved roster / typo: currently skipped everywhere -> "valid, 0 pts".
    r = roster(500, E("c", "captain", is_warlord=True), E("x", "no-such-unit", 5))
    assert "UNKNOWN_DATASHEET" in codes(r, ds)


# ───────────── 2. Warlord ─────────────

def test_empty_roster_reports_no_warlord_only(ds):
    assert codes(roster(2000), ds) == ["NO_WARLORD"]


def test_warlord_on_epic_hero_is_fine(ds):
    r = roster(500, E("a", "marneus-calgar-in-armour-of-antilochus", is_warlord=True))
    assert validate(r, ds) == []


def test_two_warlords_hides_character_check(ds):
    # Documents current behaviour: with >1 warlord the CHARACTER check is skipped,
    # so the user fixes one error and a *new* one appears. Consider reporting both.
    r = roster(2000, E("a", "captain", is_warlord=True),
               E("b", "intercessor-squad", 5, is_warlord=True))
    assert codes(r, ds) == ["MULTIPLE_WARLORDS"]


# ───────────── 3. Rule of Three ─────────────

def test_rule_of_three_exactly_three_is_legal(ds):
    r = roster(2000, E("c", "captain", is_warlord=True),
               *[E(f"t{k}", "terminator-squad", 5) for k in range(3)])
    assert "RULE_OF_THREE" not in codes(r, ds)


def test_rule_of_three_four_captains_fails(ds):
    r = roster(2000, E("c0", "captain", is_warlord=True),
               *[E(f"c{k}", "captain") for k in range(1, 4)])
    assert "RULE_OF_THREE" in codes(r, ds)


def test_rule_of_three_dedicated_transport_exempt(ds):
    r = roster(2000, E("c", "captain", is_warlord=True),
               *[E(f"r{k}", "rhino") for k in range(5)])
    assert "RULE_OF_THREE" not in codes(r, ds)


def test_rule_of_three_is_per_datasheet_not_per_role(ds):
    # 3 Terminator + 3 Hellblaster squads is fine; the cap is per datasheet.
    r = roster(3000, E("c", "captain", is_warlord=True),
               *[E(f"t{k}", "terminator-squad", 5) for k in range(3)],
               *[E(f"h{k}", "hellblaster-squad", 5) for k in range(3)])
    assert "RULE_OF_THREE" not in codes(r, ds)


def test_rule_of_three_violation_has_no_entry_id(ds):
    # UI cannot highlight the offending entries. Suggest attaching entry_id of the 4th.
    r = roster(2000, E("c0", "captain", is_warlord=True),
               *[E(f"c{k}", "captain") for k in range(1, 4)])
    v = next(x for x in validate(r, ds) if x.code == "RULE_OF_THREE")
    assert v.entry_id is None


# ───────────── 4. Epic Heroes ─────────────

def test_three_epic_heroes_report_two_duplicates(ds):
    mc = "marneus-calgar-in-armour-of-antilochus"
    r = roster(2000, E("a", mc, is_warlord=True), E("b", mc), E("c", mc))
    dup = [v for v in validate(r, ds) if v.code == "DUPLICATE_EPIC_HERO"]
    assert [v.entry_id for v in dup] == ["b", "c"]


def test_BUG_epic_hero_cannot_take_enhancement(ds):
    r = roster(500, E("a", "marneus-calgar-in-armour-of-antilochus",
                      is_warlord=True, enhancement="Artificer Armour"))
    assert "ENHANCEMENT_ON_EPIC_HERO" in codes(r, ds)


# ───────────── 5. Enhancements ─────────────

def test_exactly_three_enhancements_is_legal(ds):
    r = roster(2000,
               E("a", "captain", is_warlord=True, enhancement="Artificer Armour"),
               E("b", "captain", enhancement="The Honour Vehement"),
               E("c", "captain", enhancement="Fire Discipline"))
    assert "ENHANCEMENT_CAP_EXCEEDED" not in codes(r, ds)


def test_duplicate_enhancement_fails(ds):
    r = roster(2000,
               E("a", "captain", is_warlord=True, enhancement="Artificer Armour"),
               E("b", "captain", enhancement="Artificer Armour"))
    assert "DUPLICATE_ENHANCEMENT" in codes(r, ds)


def test_BUG_enhancement_must_belong_to_detachment(ds):
    # The existing cap test uses "Bolter Discipline", which is NOT a Gladius
    # enhancement -- it only passes because nothing checks the name.
    r = roster(500, E("a", "captain", is_warlord=True, enhancement="Bolter Discipline"))
    assert "UNKNOWN_ENHANCEMENT" in codes(r, ds)


def test_BUG_enhancement_keyword_restriction_enforced(ds):
    # "Adept of the Codex" lists keyword_restrictions=["Captain"]. NB the plain Captain
    # datasheet has no "Captain" keyword -- match against keywords + faction_keywords + name.
    r = roster(500, E("a", "marneus-calgar-in-armour-of-antilochus", is_warlord=True),
               E("b", "chaplain", enhancement="Adept of the Codex"))
    assert "ENHANCEMENT_RESTRICTED" in codes(r, ds)


# ───────────── 6. Detachment / faction ─────────────

def test_BUG_detachment_must_belong_to_faction(ds):
    r = roster(500, E("a", "captain", is_warlord=True), detachment="cryptek-conclave")
    assert "DETACHMENT_FACTION_MISMATCH" in codes(r, ds)


def test_BUG_nonexistent_detachment_rejected(ds):
    r = roster(500, E("a", "captain", is_warlord=True), detachment="totally-fake")
    assert "UNKNOWN_DETACHMENT" in codes(r, ds)


def test_faction_mismatch_names_each_offender(ds):
    r = roster(2000, E("c", "captain", is_warlord=True),
               E("n1", "necron-warriors", 10), E("n2", "necron-warriors", 10))
    mism = [v.entry_id for v in validate(r, ds) if v.code == "FACTION_MISMATCH"]
    assert mism == ["n1", "n2"]
