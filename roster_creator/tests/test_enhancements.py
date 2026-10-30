"""Enhancement data flow: wh40kdc is authoritative, the MCP server only adds text.

Regression for: Codex "No entries are available" and an empty Enhancements picker
for detachments such as Flyblown Host (an 11th-edition detachment, both of whose
enhancements are Upgrades for non-Character units).
"""
import json

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from wh40kdc import Dataset

from roster_creator import api
from roster_creator.enhancements import (
    base_name,
    eligible_for_unit,
    max_copies,
    restrictions_met,
)
from roster_creator.validator import Roster, RosterEntry, validate


@pytest.fixture(scope="module")
def ds():
    return Dataset.embedded()


@pytest.fixture()
def client():
    return TestClient(api.app)


@pytest.fixture()
def mcp_dir(tmp_path, monkeypatch):
    """Point the API at an empty fake MCP server folder; tests add data to it."""
    monkeypatch.setattr(api, "MCP_SERVER_DIR", tmp_path)

    async def fake_tools():
        return ["fake_tool"]

    async def stratagems_ok(tool, args):
        return "No stratagems found"

    monkeypatch.setattr(api, "list_mcp_tools", fake_tools)
    monkeypatch.setattr(api, "call_40k_tool", stratagems_ok)
    api.load_mcp_faction_file.cache_clear()
    yield tmp_path
    api.load_mcp_faction_file.cache_clear()


def write_mcp(root, faction, entries):
    folder = root / "data" / faction
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "enhancements.json").write_text(json.dumps(entries), encoding="utf-8")


# ───────────── helpers ─────────────

def test_base_name_strips_upgrade_suffix_and_curly_quotes():
    assert base_name("Plagueveil (Upgrade)") == "plagueveil"
    assert base_name("  Plagueveil ") == "plagueveil"
    assert base_name("Emperor’s Wrath") == "emperor's wrath"


def test_keyword_restrictions_are_and_not_or(ds):
    # ['Adeptus Astartes', 'Infantry']: a Chaplain on Bike has the first but not the second.
    enhancement = next(e for e in ds.enhancements if e["name"] == "The Blade Driven Deep")
    assert enhancement["keyword_restrictions"] == ["Adeptus Astartes", "Infantry"]
    assert restrictions_met(ds.units.find("captain"), enhancement)
    assert not restrictions_met(ds.units.find("chaplain-on-bike"), enhancement)


def test_normal_enhancement_needs_non_epic_character(ds):
    artificer = ds.enhancements.find("artificer-armour-gladius-task-force")
    assert eligible_for_unit(ds.units.find("captain"), artificer)
    assert not eligible_for_unit(ds.units.find("intercessor-squad"), artificer)
    assert not eligible_for_unit(
        ds.units.find("marneus-calgar-in-armour-of-antilochus"), artificer
    )


def test_upgrade_needs_non_character_with_matching_keywords(ds):
    plagueveil = ds.enhancements.find("plagueveil-upgrade-flyblown-host")
    assert max_copies(plagueveil) == 3
    assert eligible_for_unit(ds.units.find("plague-marines"), plagueveil)
    assert not eligible_for_unit(ds.units.find("poxwalkers"), plagueveil)       # wrong unit
    assert not eligible_for_unit(ds.units.find("lord-of-poxes"), plagueveil)    # a Character


# ───────────── /api/detachments/{id} ─────────────

def flyblown(client):
    response = client.get("/api/detachments/flyblown-host")
    assert response.status_code == 200, response.text
    return response.json()


def test_flyblown_host_lists_enhancements_when_mcp_folder_is_missing(client, mcp_dir):
    data = flyblown(client)
    names = [e["name"] for e in data["enhancements"]]
    assert names == ["Insectile Murmuration (Upgrade)", "Plagueveil (Upgrade)"]
    first = data["enhancements"][0]
    assert first["cost"] == 15 and first["upgrade"] is True and first["max_targets"] == 3
    assert first["keyword_restrictions"] == ["Death Guard", "Plague Marines"]
    assert first["description_available"] is False
    assert any("enhancements.json" in w for w in data["warnings"])


def test_flyblown_host_when_mcp_data_predates_the_detachment(client, mcp_dir):
    # MCP server loaded (776 enhancements in the log) but only has older detachments.
    write_mcp(mcp_dir, "death-guard", [
        {"name": "Plague Lord", "detachment": "Virulent Vectorium", "pointsCost": 20, "effect": "x"},
    ])
    data = flyblown(client)
    assert [e["name"] for e in data["enhancements"]] == [
        "Insectile Murmuration (Upgrade)", "Plagueveil (Upgrade)",
    ]
    assert all(e["source"] == "wh40kdc" for e in data["enhancements"])


def test_mcp_text_is_attached_when_names_differ_only_by_upgrade_suffix(client, mcp_dir):
    write_mcp(mcp_dir, "death-guard", [
        {"name": "Plagueveil", "detachment": "Flyblown Host", "pointsCost": 15,
         "effect": "Subtract 3 from detection range."},
    ])
    by_name = {e["name"]: e for e in flyblown(client)["enhancements"]}
    veil = by_name["Plagueveil (Upgrade)"]
    assert veil["description"] == "Subtract 3 from detection range."
    assert veil["description_available"] is True and veil["source"] == "wh40kdc+mcp"
    assert by_name["Insectile Murmuration (Upgrade)"]["description_available"] is False


def test_mcp_failure_for_stratagems_does_not_hide_enhancements(client, mcp_dir, monkeypatch):
    async def broken(tool, args):
        raise HTTPException(status_code=502, detail="40k MCP connection failed")

    monkeypatch.setattr(api, "call_40k_tool", broken)
    data = flyblown(client)
    assert len(data["enhancements"]) == 2
    assert data["stratagems"] == []
    assert any("Stratagems unavailable" in w for w in data["warnings"])


def test_falls_back_to_mcp_when_dataset_has_no_enhancements(client, mcp_dir, monkeypatch):
    monkeypatch.setattr(api, "detachment_enhancements", lambda ds, detachment: [])
    write_mcp(mcp_dir, "death-guard", [
        {"name": "Fury Unbound", "detachment": "Flyblown Host", "pointsCost": 25, "effect": "Rage."},
    ])
    data = client.get("/api/detachments/flyblown-host").json()
    assert [(e["name"], e["cost"], e["source"], e["description"]) for e in data["enhancements"]] == [
        ("Fury Unbound", 25, "mcp", "Rage.")
    ]


# ───────────── /api/units/{id} eligibility ─────────────

def available(client, unit_id, detachment_id):
    response = client.get(f"/api/units/{unit_id}", params={"detachment_id": detachment_id})
    assert response.status_code == 200
    return {e["name"]: e for e in response.json()["available_enhancements"]}


def test_plague_marines_can_take_flyblown_host_upgrades(client):
    options = available(client, "plague-marines", "flyblown-host")
    assert all(e["eligible"] for e in options.values()) and len(options) == 2


def test_characters_and_wrong_units_are_not_eligible_for_upgrades(client):
    assert not any(e["eligible"] for e in available(client, "lord-of-poxes", "flyblown-host").values())
    assert not any(e["eligible"] for e in available(client, "poxwalkers", "flyblown-host").values())


def test_captain_still_gets_normal_enhancements(client):
    options = available(client, "captain", "gladius-task-force")
    assert options["Artificer Armour"]["eligible"] is True
    assert available(client, "intercessor-squad", "gladius-task-force")["Artificer Armour"]["eligible"] is False


def test_enhancement_cost_is_always_numeric(client):
    for enhancement in available(client, "plague-marines", "flyblown-host").values():
        assert isinstance(enhancement["cost"], int)


# ───────────── enhancement rules text ─────────────

def rule(client, **params):
    response = client.get("/api/codex/rule", params={"type": "enhancement", **params})
    assert response.status_code == 200, response.text
    return response.json()["text"]


def test_rule_text_resolves_detachment_id_and_upgrade_suffix(client, mcp_dir):
    # Roster Builder sends the detachment *id*; MCP stores the *name*. Both must work.
    write_mcp(mcp_dir, "death-guard", [
        {"name": "Plagueveil", "detachment": "Flyblown Host", "pointsCost": 15,
         "effect": "Subtract 3 from detection range."},
    ])
    text = rule(client, name="Plagueveil (Upgrade)", faction="death-guard", detachment="flyblown-host")
    assert "Subtract 3 from detection range." in text
    assert not text.lstrip().startswith("[")        # no raw JSON dump


def test_rule_text_falls_back_to_dataset_facts(client, mcp_dir):
    text = rule(client, name="Plagueveil (Upgrade)", faction="death-guard", detachment="flyblown-host")
    assert "15 pts" in text and "Upgrade" in text and "Plague Marines" in text
    assert "not available" in text


# ───────────── diagnostics ─────────────

def test_debug_endpoint_reports_where_enhancements_come_from(client, mcp_dir):
    write_mcp(mcp_dir, "death-guard", [
        {"name": "Plague Lord", "detachment": "Virulent Vectorium", "pointsCost": 20, "effect": "x"},
    ])
    report = client.get("/api/debug/enhancements/flyblown-host").json()
    assert report["mcp_file_entries"] == 1
    assert report["mcp_matches_for_detachment"] == []
    assert report["mcp_detachment_names"] == ["Virulent Vectorium"]
    assert len(report["local_enhancements"]) == 2
    assert report["mcp_tools"] == ["fake_tool"]


# ───────────── validator: Upgrades ─────────────

def death_guard(*entries, limit=1000):
    return Roster("death-guard", "flyblown-host", limit, list(entries))


def plague_marines(iid, upgrade="Plagueveil (Upgrade)"):
    return RosterEntry(iid, "plague-marines", 5, enhancement=upgrade)


def codes(roster, ds):
    return [v.code for v in validate(roster, ds)]


def test_upgrade_on_non_character_is_legal(ds):
    found = codes(death_guard(plague_marines("a")), ds)
    assert "ENHANCEMENT_ON_NON_CHARACTER" not in found
    assert "ENHANCEMENT_RESTRICTED" not in found
    assert "UNKNOWN_ENHANCEMENT" not in found


def test_three_copies_of_an_upgrade_use_one_slot_and_are_allowed(ds):
    # Incursion allows 2 enhancement slots; three copies of one Upgrade must not exceed it.
    found = codes(death_guard(*[plague_marines(f"p{i}") for i in range(3)]), ds)
    assert "ENHANCEMENT_CAP_EXCEEDED" not in found
    assert "DUPLICATE_ENHANCEMENT" not in found
    assert "UPGRADE_COPIES_EXCEEDED" not in found


def test_fourth_copy_of_an_upgrade_is_rejected(ds):
    violations = validate(death_guard(*[plague_marines(f"p{i}") for i in range(4)]), ds)
    exceeded = [v for v in violations if v.code == "UPGRADE_COPIES_EXCEEDED"]
    assert [v.entry_id for v in exceeded] == ["p3"]


def test_upgrade_on_a_character_is_rejected(ds):
    roster = death_guard(RosterEntry("c", "lord-of-poxes", 1, enhancement="Plagueveil (Upgrade)"))
    assert "UPGRADE_ON_CHARACTER" in codes(roster, ds)


def test_upgrade_restricted_to_plague_marines(ds):
    roster = death_guard(RosterEntry("x", "poxwalkers", 10, enhancement="Plagueveil (Upgrade)"))
    assert "ENHANCEMENT_RESTRICTED" in codes(roster, ds)


def test_normal_enhancement_on_non_character_is_still_rejected(ds):
    roster = Roster("adeptus-astartes", "gladius-task-force", 2000, [
        RosterEntry("c", "captain", 1, is_warlord=True),
        RosterEntry("i", "intercessor-squad", 5, enhancement="Artificer Armour"),
    ])
    assert "ENHANCEMENT_ON_NON_CHARACTER" in codes(roster, ds)


def test_and_restriction_is_enforced_by_the_validator(ds):
    # "The Blade Driven Deep" needs Adeptus Astartes AND Infantry.
    roster = Roster("adeptus-astartes", "vanguard-spearhead", 2000, [
        RosterEntry("c", "chaplain-on-bike", 1, is_warlord=True, enhancement="The Blade Driven Deep"),
    ])
    assert "ENHANCEMENT_RESTRICTED" in codes(roster, ds)


def test_unit_without_points_data_does_not_crash_validation(ds):
    # 6 units in wh40kdc have no points entry; validation must still return.
    roster = Roster("adeptus-astartes", "gladius-task-force", 2000, [
        RosterEntry("c", "captain-on-bike", 1, is_warlord=True),
    ])
    assert isinstance(validate(roster, ds), list)
