from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from wh40kdc import Dataset


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"


@dataclass
class Violation:
    code: str
    severity: Severity
    message: str
    entry_id: Optional[str] = None


@dataclass
class RosterEntry:
    instance_id: str
    datasheet_id: str
    size: int
    wargear: list[str] = field(default_factory=list)
    enhancement: Optional[str] = None
    attached_to: Optional[str] = None
    is_warlord: bool = False


@dataclass
class Roster:
    faction_id: str
    detachment_id: str
    points_limit: int
    entries: list[RosterEntry] = field(default_factory=list)


def _enhancement_cost(roster: Roster, entry: RosterEntry, ds: Dataset) -> int:
    if not entry.enhancement:
        return 0
    det = next((d for d in ds.detachments if d.get("id") == roster.detachment_id), None)
    for eid in (det or {}).get("enhancement_ids", []):
        enh = ds.enhancements.find(eid)
        if enh and enh.get("name") == entry.enhancement:
            return enh.get("cost", 0)
    return 0


def _tier_for(unit, size: int, copies: int):
    """First tier matching model count AND the roster-wide copy count."""
    for tier in unit.points:
        lo, hi = tier["models"], tier.get("models_max", tier["models"])
        cmin = tier.get("unit_count_min") or 1
        cmax = tier.get("unit_count_max")
        if lo <= size <= hi and copies >= cmin and (cmax is None or copies <= cmax):
            return tier
    return None


def compute_points(roster: Roster, ds: Dataset) -> int:
    copies: dict[str, int] = {}
    for e in roster.entries:
        copies[e.datasheet_id] = copies.get(e.datasheet_id, 0) + 1
    total = 0
    for entry in roster.entries:
        unit = ds.units.find(entry.datasheet_id)
        if unit is None:
            continue
        tier = _tier_for(unit, entry.size, copies[entry.datasheet_id])
        if tier is None:   # invalid size: price at the nearest tier so the readout isn't 0
            tier = min(unit.points, key=lambda t: abs(t["models"] - entry.size))
        if tier:
            total += tier["cost"]
        total += _enhancement_cost(roster, entry, ds)
    return total


def validate(roster: Roster, ds: Dataset) -> list[Violation]:
    violations: list[Violation] = []

    # Rule 1: points limit
    total = compute_points(roster, ds)
    if total > roster.points_limit:
        violations.append(Violation(
            code="POINTS_EXCEEDED",
            severity=Severity.ERROR,
            message=f"Roster is {total} pts, limit is {roster.points_limit} "
                    f"({total - roster.points_limit} pts over)",
        ))

    # Rule 2 & 3: exactly one Warlord (and must be a Character)
    warlords = [e for e in roster.entries if e.is_warlord]
    if len(warlords) == 0:
        violations.append(Violation(
            code="NO_WARLORD",
            severity=Severity.ERROR,
            message="Roster must nominate exactly one Warlord, but none was nominated",
        ))
    elif len(warlords) > 1:
        violations.append(Violation(
            code="MULTIPLE_WARLORDS",
            severity=Severity.ERROR,
            message=f"Roster must have exactly one Warlord, but {len(warlords)} were nominated",
            entry_id=warlords[1].instance_id,
        ))
    elif len(warlords) == 1:
        warlord_entry = warlords[0]
        unit = ds.units.find(warlord_entry.datasheet_id)
        if unit:
            keywords = [k.upper() for k in unit.keywords]
            if "CHARACTER" not in keywords:
                violations.append(Violation(
                    code="WARLORD_NOT_CHARACTER",
                    severity=Severity.ERROR,
                    message=f"{unit.name} cannot be the Warlord because it lacks the CHARACTER keyword.",
                    entry_id=warlord_entry.instance_id,
                ))

    # Rule 4: Duplicate EPIC HEROES
    epic_heroes_seen = set()
    for entry in roster.entries:
        unit = ds.units.find(entry.datasheet_id)
        if unit:
            keywords = [k.upper() for k in unit.keywords]
            if "EPIC HERO" in keywords:
                if entry.datasheet_id in epic_heroes_seen:
                    violations.append(Violation(
                        code="DUPLICATE_EPIC_HERO",
                        severity=Severity.ERROR,
                        message=f"{unit.name} is an EPIC HERO and can only be taken once.",
                        entry_id=entry.instance_id,
                    ))
                else:
                    epic_heroes_seen.add(entry.datasheet_id)

    # Rule 5: Invalid Unit Size
    for entry in roster.entries:
        unit = ds.units.find(entry.datasheet_id)
        if unit:
            valid_size = any(
                tier["models"] <= entry.size <= tier.get("models_max", tier["models"])
                for tier in unit.points
            )
            if not valid_size:
                violations.append(Violation(
                    code="INVALID_UNIT_SIZE",
                    severity=Severity.ERROR,
                    message=f"{unit.name} cannot be taken in a squad of {entry.size} models.",
                    entry_id=entry.instance_id,
                ))

    # Rule 6: Rule of Three
    datasheet_counts = {}
    for entry in roster.entries:
        datasheet_counts[entry.datasheet_id] = datasheet_counts.get(entry.datasheet_id, 0) + 1

    for datasheet_id, count in datasheet_counts.items():
        if count > 3:
            unit = ds.units.find(datasheet_id)
            if unit:
                keywords = [k.upper() for k in unit.keywords]
                if "BATTLELINE" not in keywords and "DEDICATED TRANSPORT" not in keywords:
                    violations.append(Violation(
                        code="RULE_OF_THREE",
                        severity=Severity.ERROR,
                        message=f"You cannot take more than 3 of {unit.name} (found {count}).",
                    ))

    # Rule 7: Enhancements
    enhancements_count = 0

    for entry in roster.entries:
        if entry.enhancement:
            enhancements_count += 1
            unit = ds.units.find(entry.datasheet_id)
            if unit:
                keywords = [k.upper() for k in unit.keywords]
                if "CHARACTER" not in keywords:
                    violations.append(Violation(
                        code="ENHANCEMENT_ON_NON_CHARACTER",
                        severity=Severity.ERROR,
                        message=f"{unit.name} cannot take an enhancement because it lacks the CHARACTER keyword.",
                        entry_id=entry.instance_id,
                    ))

    if enhancements_count > 3:
        violations.append(Violation(
            code="ENHANCEMENT_CAP_EXCEEDED",
            severity=Severity.ERROR,
            message=f"Roster has {enhancements_count} enhancements. The maximum allowed is 3.",
        ))

    # Rule 8: Faction Mismatch
    for entry in roster.entries:
        unit = ds.units.find(entry.datasheet_id)
        if unit:
            if unit.faction_id != roster.faction_id:
                violations.append(Violation(
                    code="FACTION_MISMATCH",
                    severity=Severity.ERROR,
                    message=f"{unit.name} belongs to {unit.faction_id}, not {roster.faction_id}.",
                    entry_id=entry.instance_id,
                ))

    # Rule 9: Duplicate Enhancements
    seen_enhancements = set()
    for entry in roster.entries:
        if entry.enhancement:
            if entry.enhancement in seen_enhancements:
                violations.append(Violation(
                    code="DUPLICATE_ENHANCEMENT",
                    severity=Severity.ERROR,
                    message=f"Cannot take the enhancement '{entry.enhancement}' multiple times.",
                    entry_id=entry.instance_id,
                ))
            else:
                seen_enhancements.add(entry.enhancement)

    # Rule 10: unknown datasheets (stale save / typo) must not silently cost 0
    for entry in roster.entries:
        if ds.units.find(entry.datasheet_id) is None:
            violations.append(Violation("UNKNOWN_DATASHEET", Severity.ERROR,
                f"Unknown unit '{entry.datasheet_id}'.", entry.instance_id))

    # Rule 11: detachment must exist and belong to the roster's faction
    det = next((d for d in ds.detachments if d.get("id") == roster.detachment_id), None)
    if det is None:
        violations.append(Violation("UNKNOWN_DETACHMENT", Severity.ERROR,
            f"Unknown detachment '{roster.detachment_id}'."))
    elif det.get("faction_id") != roster.faction_id:
        violations.append(Violation("DETACHMENT_FACTION_MISMATCH", Severity.ERROR,
            f"{det.get('name')} is not a {roster.faction_id} detachment."))
    else:
        # Rule 12: enhancement must be one of that detachment's, and eligible
        by_name = {}
        for eid in det.get("enhancement_ids", []):
            enh = ds.enhancements.find(eid)
            if enh:
                by_name[enh["name"]] = enh
        for entry in roster.entries:
            if not entry.enhancement:
                continue
            unit = ds.units.find(entry.datasheet_id)
            enh = by_name.get(entry.enhancement)
            if enh is None:
                violations.append(Violation("UNKNOWN_ENHANCEMENT", Severity.ERROR,
                    f"'{entry.enhancement}' is not an enhancement of {det['name']}.", entry.instance_id))
            elif unit is not None:
                have = {k.upper() for k in unit.keywords} | {k.upper() for k in unit.faction_keywords} | {unit.name.upper()}
                need = {k.upper() for k in enh.get("keyword_restrictions", [])}
                if need and not (need & have):
                    violations.append(Violation("ENHANCEMENT_RESTRICTED", Severity.ERROR,
                        f"{unit.name} is not eligible for {enh['name']}.", entry.instance_id))

    # Rule 13: Epic Heroes cannot take enhancements
    for entry in roster.entries:
        unit = ds.units.find(entry.datasheet_id)
        if entry.enhancement and unit and "EPIC HERO" in [k.upper() for k in unit.keywords]:
            violations.append(Violation("ENHANCEMENT_ON_EPIC_HERO", Severity.ERROR,
                f"{unit.name} is an EPIC HERO and cannot take an enhancement.", entry.instance_id))

    return violations