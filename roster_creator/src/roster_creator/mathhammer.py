"""Analytic (expected-value) Mathhammer.  Drop in as roster_creator/mathhammer.py.

Design rules
  * Pure functions, no I/O, no FastAPI, no wh40kdc imports in the core types.
    Only `profile_from_dataset()` knows the wh40kdc raw shape.
  * Everything edition-specific lives in `RuleSet`, so an edition bump is a data
    change plus a test update, not a rewrite.
  * Keywords are data: {keyword_id: parameters}. Each is handled in ONE place below.
    A keyword the calculator does not understand is reported in
    `Result.unhandled_keywords` instead of being silently ignored.

Known approximations (documented so tests don't over-claim):
  * Feel No Pain is applied as a flat multiplier on damage that gets through the
    per-wound damage cap; exact FNP-vs-overkill interaction needs Monte Carlo.
  * Rapid Fire / Melta / Blast depend on range and target size, so they are taken
    from `Context`, not guessed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from fractions import Fraction
from itertools import product
from typing import Callable, Mapping, Optional

# ───────────────────────── dice ─────────────────────────

_DICE_RE = re.compile(r"^(\d*)D(3|6)(?:\+(\d+))?$|^(\d+)$")


@dataclass(frozen=True)
class Dice:
    """'3', 'D6', 'D3+1', '2D6', '2D6+2' -> exact distribution."""
    count: int = 0      # number of dice
    sides: int = 0      # 3 or 6
    flat: int = 0

    @staticmethod
    def parse(value: int | str) -> "Dice":
        if isinstance(value, int):
            return Dice(flat=value)
        m = _DICE_RE.match(str(value).strip().upper().replace(" ", ""))
        if not m:
            raise ValueError(f"unparseable dice expression: {value!r}")
        if m.group(4) is not None:
            return Dice(flat=int(m.group(4)))
        return Dice(int(m.group(1) or 1), int(m.group(2)), int(m.group(3) or 0))

    def distribution(self) -> dict[int, Fraction]:
        dist: dict[int, Fraction] = {self.flat: Fraction(1)}
        for _ in range(self.count):
            nxt: dict[int, Fraction] = {}
            for total, p in dist.items():
                for face in range(1, self.sides + 1):
                    nxt[total + face] = nxt.get(total + face, Fraction(0)) + p / self.sides
            dist = nxt
        return dist

    def mean(self) -> float:
        return float(sum(v * p for v, p in self.distribution().items()))

    def mean_capped(self, cap: int) -> float:
        """E[min(X, cap)] -- damage never spills onto the next model."""
        return float(sum(min(v, cap) * p for v, p in self.distribution().items()))


# ───────────────────────── rules (edition-specific) ─────────────────────────

def _standard_wound_target(strength: int, toughness: int) -> int:
    # VERIFY against the current core rules before trusting (edition-sensitive).
    if strength >= 2 * toughness:
        return 2
    if strength > toughness:
        return 3
    if strength == toughness:
        return 4
    if strength * 2 <= toughness:
        return 6
    return 5


@dataclass(frozen=True)
class RuleSet:
    name: str = "standard"
    wound_target: Callable[[int, int], int] = _standard_wound_target
    crit_hit_on: int = 6          # unmodified roll that counts as a Critical Hit
    crit_wound_on: int = 6
    modifier_cap: int = 1         # hit / wound modifiers are clamped to +-cap
    save_always_fails_on: int = 1


STANDARD = RuleSet()

# ───────────────────────── inputs ─────────────────────────

@dataclass(frozen=True)
class WeaponProfile:
    name: str
    attacks: Dice
    skill: Optional[int]          # BS/WS; None == auto-hit (Torrent / BS "-")
    strength: int
    ap: int                       # negative number, e.g. -2
    damage: Dice
    is_melee: bool = False
    range_in: Optional[int] = None
    keywords: Mapping[str, Mapping] = field(default_factory=dict)


@dataclass(frozen=True)
class Target:
    toughness: int
    save: int                     # e.g. 3 for 3+
    wounds: int                   # per model
    invuln: Optional[int] = None
    fnp: Optional[int] = None
    keywords: frozenset[str] = frozenset()   # upper-cased unit keywords


@dataclass(frozen=True)
class Context:
    models_firing: int = 1        # weapon copies: attacks are multiplied by this
    in_half_range: bool = False   # Rapid Fire / Melta
    target_models: int = 1        # Blast
    hit_modifier: int = 0
    wound_modifier: int = 0
    reroll_hits: str = "none"     # none | ones | all
    reroll_wounds: str = "none"


@dataclass
class Result:
    attacks: float = 0.0
    hits: float = 0.0
    wounds: float = 0.0
    mortal_wounds: float = 0.0
    unsaved: float = 0.0
    damage: float = 0.0
    unhandled_keywords: list[str] = field(default_factory=list)


# ───────────────────────── probability helpers ─────────────────────────

def _p_roll_at_least(n: int) -> float:
    """P(d6 >= n) with no always-fail/always-succeed handling."""
    return max(0.0, min(1.0, (7 - n) / 6))


def _p_success(target: int, modifier: int, cap: int, crit_on: int) -> tuple[float, float]:
    """(P(success), P(critical)) for a hit/wound roll. Unmodified 1 always fails,
    unmodified 6 always succeeds; modifier is clamped to +-cap."""
    mod = max(-cap, min(cap, modifier))
    need = max(2, min(6, target - mod))        # 1 always fails, 6 always works
    p = _p_roll_at_least(need)
    crit = _p_roll_at_least(crit_on)
    return max(p, crit), crit


def _apply_reroll(p: float, crit: float, mode: str) -> tuple[float, float]:
    if mode == "all":
        return p + (1 - p) * p, crit + (1 - p) * crit
    if mode == "ones":
        return p + (1 / 6) * p, crit + (1 / 6) * crit
    return p, crit


# ───────────────────────── keyword handlers ─────────────────────────

HANDLED = {
    "torrent", "lethal-hits", "sustained-hits", "devastating-wounds", "anti",
    "twin-linked", "rapid-fire", "blast", "melta", "assault", "heavy", "pistol",
    "ignores-cover", "precision", "psychic", "hazardous", "one-shot",
    "close-quarters", "indirect-fire", "extra-attacks",
}   # ones in the 2nd row do not change expected damage in this calculator


def _excluded(kw: Mapping, target: Target) -> bool:
    banned = {k.upper() for k in (kw or {}).get("excluded_target_keywords", [])}
    return bool(banned & target.keywords)


def expected_damage(w: WeaponProfile, t: Target, ctx: Context = Context(),
                    rules: RuleSet = STANDARD) -> Result:
    kws = dict(w.keywords)
    res = Result(unhandled_keywords=sorted(k for k in kws if k not in HANDLED))

    # --- attacks
    attacks = w.attacks.mean() * ctx.models_firing
    if "rapid-fire" in kws and ctx.in_half_range:
        attacks += kws["rapid-fire"].get("value", 0) * ctx.models_firing
    if "blast" in kws:
        attacks += (ctx.target_models // 5) * ctx.models_firing
    res.attacks = attacks

    # --- hit roll
    if "torrent" in kws or w.skill is None:
        p_hit, p_crit = 1.0, 0.0
    else:
        p_hit, p_crit = _p_success(w.skill, ctx.hit_modifier, rules.modifier_cap, rules.crit_hit_on)
        p_hit, p_crit = _apply_reroll(p_hit, p_crit, ctx.reroll_hits)
    normal_hits = attacks * (p_hit - p_crit)
    crit_hits = attacks * p_crit

    lethal = "lethal-hits" in kws and not _excluded(kws["lethal-hits"], t)
    sustained = kws.get("sustained-hits", {}).get("value", 0) if "sustained-hits" in kws else 0

    extra_hits = crit_hits * sustained
    auto_wounds = crit_hits if lethal else 0.0
    to_wound = normal_hits + extra_hits + (0.0 if lethal else crit_hits)
    res.hits = normal_hits + crit_hits + extra_hits

    # --- wound roll
    anti = kws.get("anti")
    wound_mod = ctx.wound_modifier
    base_need = rules.wound_target(w.strength, t.toughness)
    p_w, p_cw = _p_success(base_need, wound_mod, rules.modifier_cap, rules.crit_wound_on)
    if anti and anti.get("target_keyword", "").upper() in t.keywords:
        p_cw = max(p_cw, _p_roll_at_least(anti.get("threshold", 6)))
        p_w = max(p_w, p_cw)
    reroll_w = "all" if "twin-linked" in kws else ctx.reroll_wounds
    p_w, p_cw = _apply_reroll(p_w, p_cw, reroll_w)

    crit_wounds = to_wound * p_cw
    normal_wounds = to_wound * (p_w - p_cw) + auto_wounds
    devastating = "devastating-wounds" in kws and not _excluded(kws["devastating-wounds"], t)

    mortal = crit_wounds if devastating else 0.0
    saveable = normal_wounds + (0.0 if devastating else crit_wounds)
    res.wounds = saveable + mortal
    res.mortal_wounds = mortal

    # --- save
    sv = t.save - w.ap                      # ap is negative: 3+ with AP-2 -> 5+
    if t.invuln is not None:
        sv = min(sv, t.invuln)
    p_save = 0.0 if sv > 6 else min(_p_roll_at_least(sv), 5 / 6)
    unsaved = saveable * (1 - p_save)
    res.unsaved = unsaved + mortal

    # --- damage (capped per wound, FNP approximated)
    d = w.damage
    if "melta" in kws and ctx.in_half_range:
        d = Dice(d.count, d.sides, d.flat + kws["melta"].get("value", 0))
    per_wound = d.mean_capped(t.wounds)
    fnp_mult = 1.0 if t.fnp is None else 1 - _p_roll_at_least(t.fnp)
    res.damage = (unsaved * per_wound + mortal * d.mean_capped(t.wounds)) * fnp_mult
    return res


# ───────────────────────── dataset adapter ─────────────────────────

def _num(v) -> Optional[int]:
    return v if isinstance(v, int) else None


def profile_from_dataset(raw_weapon: dict, raw_profile: dict) -> WeaponProfile:
    """Build a WeaponProfile from one wh40kdc weapon + one of its `profiles`.

    wh40kdc shape (verified against wh40kdc 1.4.5):
      profile = {name, range: int | 'Melee', keywords: [{keyword_id, parameters?}],
                 stats: {A: int|'D6'.., BS|WS: int|None, S: int, AP: int, D: int|'D6+1'..}}
    """
    stats = raw_profile["stats"]
    is_melee = raw_profile.get("range") == "Melee"
    skill = stats.get("WS") if is_melee else stats.get("BS")
    kws = {}
    for kw in raw_profile.get("keywords", []):
        if isinstance(kw, dict):
            kws[kw["keyword_id"]] = kw.get("parameters") or {}
        else:                                   # defensive: bare string
            kws[str(kw).lower().replace(" ", "-")] = {}
    return WeaponProfile(
        name=f"{raw_weapon['name']} - {raw_profile.get('name', '')}".strip(" -"),
        attacks=Dice.parse(stats["A"]), skill=_num(skill), strength=int(stats["S"]),
        ap=int(stats["AP"]), damage=Dice.parse(stats["D"]), is_melee=is_melee,
        range_in=None if is_melee else _num(raw_profile.get("range")), keywords=kws,
    )


def target_from_unit(unit, model_profile_index: int = 0) -> Target:
    p = unit.profile_at(model_profile_index)
    return Target(
        toughness=int(p["T"]), save=int(p["Sv"]), wounds=int(p["W"]),
        invuln=_num(p.get("invuln_sv")),
        keywords=frozenset(k.upper() for k in unit.keywords),
    )
