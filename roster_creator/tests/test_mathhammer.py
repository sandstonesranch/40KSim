"""Hand-calculated oracle tests for mathhammer.py.

Every expected number below is derived by hand in the comment next to it, so a
failure means the code is wrong, not that two implementations agree with each other.
"""
import pytest
from wh40kdc import Dataset
from roster_creator.mathhammer import (
    Context, Dice, Target, WeaponProfile, expected_damage,
    profile_from_dataset, target_from_unit, _standard_wound_target,
)

D = Dice.parse


def W(a=1, skill=3, s=4, ap=0, d=1, **kw):
    return WeaponProfile("test", D(a), skill, s, ap, D(d), keywords=kw)


T4_3UP = Target(toughness=4, save=3, wounds=2)


def approx(x):
    return pytest.approx(x, abs=1e-9)


# ── dice ──
def test_dice_means():
    assert D("D6").mean() == approx(3.5)
    assert D("D3").mean() == approx(2.0)
    assert D("2D6+2").mean() == approx(9.0)
    assert D(3).mean() == approx(3.0)


def test_damage_is_capped_per_model_wounds():
    # D6 into 2-wound models: E[min(D6,2)] = (1 + 5*2)/6 = 11/6
    assert D("D6").mean_capped(2) == approx(11 / 6)
    assert D("D6").mean_capped(1) == approx(1.0)
    assert D("D6").mean_capped(6) == approx(3.5)


@pytest.mark.parametrize("bad", ["D4", "banana", "D6-1"])
def test_unparseable_dice_raises(bad):
    with pytest.raises(ValueError):
        D(bad)


# ── wound table ──
@pytest.mark.parametrize("s,t,need", [
    (8, 4, 2), (9, 4, 2), (5, 4, 3), (4, 4, 4), (3, 4, 5), (2, 4, 6), (1, 4, 6), (4, 8, 6),
])
def test_wound_table(s, t, need):
    assert _standard_wound_target(s, t) == need


# ── the worked example: 10 Intercessors (20 shots) into T4 / 3+ ──
def test_basic_pipeline_matches_hand_calc():
    # 20 x 2/3 hit x 1/2 wound x 1/2 fail (3+ with AP-1 -> 4+)  = 3.3333
    r = expected_damage(W(a=20, ap=-1), T4_3UP)
    assert r.hits == approx(20 * 2 / 3)
    assert r.wounds == approx(20 * 2 / 3 * 1 / 2)
    assert r.damage == approx(20 * 2 / 3 * 1 / 2 * 1 / 2 * 1.0)   # D1 so cap irrelevant


def test_ap_zero_vs_3up_and_invuln_never_worse():
    r0 = expected_damage(W(a=6, s=4), Target(4, 3, 1))                # fail 1/3
    assert r0.damage == approx(6 * 2 / 3 * 1 / 2 * 1 / 3)
    r_inv = expected_damage(W(a=6, s=4, ap=-4), Target(4, 3, 1, invuln=4))   # 7+ vs 4++ -> 4+
    assert r_inv.damage == approx(6 * 2 / 3 * 1 / 2 * 1 / 2)
    r_bad_inv = expected_damage(W(a=6, s=4, ap=0), Target(4, 3, 1, invuln=5))  # armour 3+ beats 5++
    assert r_bad_inv.damage == approx(r0.damage)


def test_save_cannot_beat_5_6_even_with_good_armour():
    r = expected_damage(W(a=6, s=8), Target(4, 2, 1))   # 2+ save: still fails on a 1
    assert r.damage == approx(6 * 2 / 3 * 5 / 6 * (1 / 6))


def test_save_impossible_when_ap_pushes_past_6():
    r = expected_damage(W(a=6, s=8, ap=-5), Target(4, 3, 1))  # 3+ with AP-5 -> 8+
    assert r.damage == approx(6 * 2 / 3 * 5 / 6)


# ── keywords ──
def test_torrent_and_no_bs_auto_hit():
    assert expected_damage(W(a=6, skill=3, torrent={}), T4_3UP).hits == approx(6)
    assert expected_damage(W(a=6, skill=None), T4_3UP).hits == approx(6)


def test_lethal_vs_sustained_are_not_interchangeable():
    # A=6, BS3+, S8 vs T4 (wound 2+ => 5/6), 4+ save, AP0 => fail 1/2
    t = Target(4, 4, 1)
    lethal = expected_damage(W(a=6, s=8, **{"lethal-hits": {}}), t)
    # crit 1, normal hits 3 -> wounds = 1 auto + 3*5/6 = 3.5 -> *1/2
    assert lethal.wounds == approx(3.5) and lethal.damage == approx(1.75)
    sust = expected_damage(W(a=6, s=8, **{"sustained-hits": {"value": 1}}), t)
    # hits = 3 normal + 1 crit + 1 extra = 5 -> 5*5/6 = 4.1667 wounds
    assert sust.hits == approx(5) and sust.wounds == approx(5 * 5 / 6)
    assert sust.damage == approx(5 * 5 / 6 * 1 / 2)


def test_devastating_wounds_bypass_saves():
    # A=6 -> 4 hits; S4=T4 wound 4+ (1/2), crit wound 1/6.
    # crit wounds = 4/6 = 0.667 (mortal, no save). normal = 4*(1/2-1/6)=1.333 -> *1/2
    r = expected_damage(W(a=6, **{"devastating-wounds": {}}), Target(4, 4, 1))
    assert r.mortal_wounds == approx(4 / 6)
    assert r.damage == approx(4 / 6 + 4 * (1 / 2 - 1 / 6) * 1 / 2)


def test_devastating_wounds_respects_excluded_target_keywords():
    kw = {"devastating-wounds": {"excluded_target_keywords": ["Vehicle"]}}
    veh = Target(4, 4, 1, keywords=frozenset({"VEHICLE"}))
    assert expected_damage(W(a=6, **kw), veh).mortal_wounds == 0
    assert expected_damage(W(a=6, **kw), Target(4, 4, 1)).mortal_wounds > 0


def test_anti_makes_crit_wounds_on_threshold():
    # Anti-Infantry 4+: against INFANTRY wounds on 4+ regardless of S/T.
    kw = {"anti": {"target_keyword": "Infantry", "threshold": 4}}
    t = Target(8, 4, 1, keywords=frozenset({"INFANTRY"}))      # S4 vs T8 = 6+ normally
    r = expected_damage(W(a=6, s=4, **kw), t)
    assert r.wounds == approx(4 * 1 / 2)                       # 4 hits * (4+ = 1/2)
    r2 = expected_damage(W(a=6, s=4, **kw), Target(8, 4, 1))   # not infantry: unchanged
    assert r2.wounds == approx(4 * 1 / 6)


def test_twin_linked_rerolls_wounds():
    # wound 4+ = 1/2 -> 1/2 + 1/2*1/2 = 3/4
    r = expected_damage(W(a=6, **{"twin-linked": {}}), Target(4, 4, 1))
    assert r.wounds == approx(4 * 3 / 4)


def test_reroll_ones_and_all_hits():
    base = expected_damage(W(a=6), Target(4, 4, 1)).hits
    assert base == approx(4)
    assert expected_damage(W(a=6), Target(4, 4, 1), Context(reroll_hits="ones")).hits == approx(6 * (2 / 3 + 1 / 6 * 2 / 3))
    assert expected_damage(W(a=6), Target(4, 4, 1), Context(reroll_hits="all")).hits == approx(6 * (2 / 3 + 1 / 3 * 2 / 3))


def test_modifier_is_capped_at_plus_one():
    plus1 = expected_damage(W(a=6, skill=4), Target(4, 4, 1), Context(hit_modifier=1)).hits
    plus3 = expected_damage(W(a=6, skill=4), Target(4, 4, 1), Context(hit_modifier=3)).hits
    assert plus1 == plus3 == approx(6 * 2 / 3)


def test_unmodified_one_always_misses_even_with_big_bonus():
    # BS2+ with +1 would be 1+ -> still 5/6
    assert expected_damage(W(a=6, skill=2), Target(4, 4, 1), Context(hit_modifier=1)).hits == approx(5)


def test_rapid_fire_and_melta_depend_on_range():
    rf = {"rapid-fire": {"value": 1}}
    assert expected_damage(W(a=2, **rf), T4_3UP, Context(in_half_range=False)).attacks == approx(2)
    assert expected_damage(W(a=2, **rf), T4_3UP, Context(in_half_range=True)).attacks == approx(3)
    melta = {"melta": {"value": 2}}
    far = expected_damage(W(a=1, d="D6", **melta), Target(4, 7, 12), Context()).damage
    near = expected_damage(W(a=1, d="D6", **melta), Target(4, 7, 12), Context(in_half_range=True)).damage
    assert near - far == approx(2 * (2 / 3) * (1 / 2) * 1.0)   # +2 damage on every unsaved wound


def test_fnp_scales_damage():
    base = expected_damage(W(a=6, s=8, ap=-4), Target(4, 3, 1)).damage
    assert expected_damage(W(a=6, s=8, ap=-4), Target(4, 3, 1, fnp=5)).damage == approx(base * (1 - 2 / 6))


def test_unknown_keywords_are_reported_not_swallowed():
    r = expected_damage(W(a=1, **{"made-up-rule": {}, "cleave": {"value": 1}}), T4_3UP)
    assert r.unhandled_keywords == ["cleave", "made-up-rule"]


# ── real dataset integration ──
@pytest.fixture(scope="module")
def ds():
    return Dataset.embedded()


def test_every_dataset_weapon_profile_parses(ds):
    """If this fails, the data has a shape the adapter doesn't know. This is the
    test that tells you whether you need more than a basic calculator."""
    bad = []
    n = 0
    for u in ds.units:
        for w in u.weapons:
            for p in w.raw.get("profiles", []):
                n += 1
                try:
                    profile_from_dataset(w.raw, p)
                except Exception as e:                       # noqa: BLE001
                    bad.append((u.id, w.name, repr(e)))
    assert n > 5000
    assert not bad, bad[:5]


def test_real_unit_end_to_end(ds):
    intercessor = ds.units.find("intercessor-squad")
    target = target_from_unit(intercessor)
    bolt = next(w for w in ds.units.find("intercessor-squad").weapons if w.raw["profiles"][0]["range"] != "Melee")
    prof = profile_from_dataset(bolt.raw, bolt.raw["profiles"][0])
    r = expected_damage(prof, target, Context(models_firing=10))
    assert 0 < r.damage < r.attacks
