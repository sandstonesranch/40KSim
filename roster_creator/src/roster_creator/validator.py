from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from wh40kdc import Dataset
from .enhancements import detachment_enhancements, is_upgrade, max_copies, restrictions_met


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


def _battle_size_limits(points_limit: int) -> tuple[str, int, int]:
    if points_limit <= 1000:
        return "Incursion", 2, 2
    if points_limit <= 2000:
        return "Strike Force", 3, 4
    return "Onslaught", 3, 4


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
        if tier is None and unit.points:   # invalid size: price at the nearest tier so the readout isn't 0
            tier = min(unit.points, key=lambda t: abs(t["models"] - entry.size))
        if tier:
            total += tier["cost"]
        total += _enhancement_cost(roster, entry, ds)
    return total


def validate(roster: Roster, ds: Dataset) -> list[Violation]:
    violations: list[Violation] = []
    battle_size, copy_limit, enhancement_limit = _battle_size_limits(roster.points_limit)

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

    # Rule 6: battle-size datasheet limits
    datasheet_counts = {}
    for entry in roster.entries:
        datasheet_counts[entry.datasheet_id] = datasheet_counts.get(entry.datasheet_id, 0) + 1

    for datasheet_id, count in datasheet_counts.items():
        unit = ds.units.find(datasheet_id)
        if unit:
            keywords = {keyword.upper() for keyword in unit.keywords}
            unit_limit = copy_limit * (2 if "BATTLELINE" in keywords else 1)
            if count > unit_limit and "DEDICATED TRANSPORT" not in keywords:
                violations.append(Violation(
                    code="RULE_OF_THREE",
                    severity=Severity.ERROR,
                    message=(
                        f"{battle_size} allows at most {unit_limit} copies of "
                        f"{unit.name} (found {count})."
                    ),
                ))

    # Rule 7: Enhancements. Normal enhancements go on Characters; Upgrades go on
    # non-Characters and all copies of one Upgrade share a single enhancement slot.
    roster_detachment = next((d for d in ds.detachments if d.get("id") == roster.detachment_id), None)
    known_enhancements = {e["name"]: e for e in detachment_enhancements(ds, roster_detachment)}
    enhancement_slots: set[str] = set()

    for entry in roster.entries:
        if entry.enhancement:
            enhancement = known_enhancements.get(entry.enhancement)
            upgrade = enhancement is not None and is_upgrade(enhancement)
            enhancement_slots.add(entry.enhancement if upgrade else entry.instance_id)
            unit = ds.units.find(entry.datasheet_id)
            if unit:
                keywords = [k.upper() for k in unit.keywords]
                if upgrade and "CHARACTER" in keywords:
                    violations.append(Violation(
                        code="UPGRADE_ON_CHARACTER",
                        severity=Severity.ERROR,
                        message=f"{entry.enhancement} is an Upgrade and can only be taken by non-CHARACTER units.",
                        entry_id=entry.instance_id,
                    ))
                elif not upgrade and "CHARACTER" not in keywords:
                    violations.append(Violation(
                        code="ENHANCEMENT_ON_NON_CHARACTER",
                        severity=Severity.ERROR,
                        message=f"{unit.name} cannot take an enhancement because it lacks the CHARACTER keyword.",
                        entry_id=entry.instance_id,
                    ))
    enhancements_count = len(enhancement_slots)

    if enhancements_count > enhancement_limit:
        violations.append(Violation(
            code="ENHANCEMENT_CAP_EXCEEDED",
            severity=Severity.ERROR,
            message=(
                f"{battle_size} allows at most {enhancement_limit} enhancements; "
                f"roster has {enhancements_count}."
            ),
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

    # Rule 9: Duplicate Enhancements (an Upgrade may be repeated up to max_targets times)
    enhancement_copies: dict[str, int] = {}
    for entry in roster.entries:
        if entry.enhancement:
            enhancement = known_enhancements.get(entry.enhancement)
            copies = enhancement_copies.get(entry.enhancement, 0) + 1
            enhancement_copies[entry.enhancement] = copies
            if enhancement is not None and is_upgrade(enhancement):
                if copies > max_copies(enhancement):
                    violations.append(Violation(
                        code="UPGRADE_COPIES_EXCEEDED",
                        severity=Severity.ERROR,
                        message=(
                            f"'{entry.enhancement}' can be taken by at most "
                            f"{max_copies(enhancement)} units."
                        ),
                        entry_id=entry.instance_id,
                    ))
            elif copies > 1:
                violations.append(Violation(
                    code="DUPLICATE_ENHANCEMENT",
                    severity=Severity.ERROR,
                    message=f"Cannot take the enhancement '{entry.enhancement}' multiple times.",
                    entry_id=entry.instance_id,
                ))

    # Rule 10: unknown datasheets (stale save / typo) must not silently cost 0
    for entry in roster.entries:
        if ds.units.find(entry.datasheet_id) is None:
            violations.append(Violation("UNKNOWN_DATASHEET", Severity.ERROR,
                f"Unknown unit '{entry.datasheet_id}'.", entry.instance_id))

    # Rule 11: leader attachments must target a legal bodyguard and be acyclic.
    entries_by_id = {entry.instance_id: entry for entry in roster.entries}
    for entry in roster.entries:
        if not entry.attached_to:
            continue
        if entry.attached_to == entry.instance_id:
            violations.append(Violation(
                "LEADER_ATTACHMENT_SELF",
                Severity.ERROR,
                "A unit cannot attach to itself.",
                entry.instance_id,
            ))
            continue

        target = entries_by_id.get(entry.attached_to)
        if target is None:
            violations.append(Violation(
                "LEADER_ATTACHMENT_TARGET_NOT_FOUND",
                Severity.ERROR,
                f"Attached unit '{entry.attached_to}' is not in the roster.",
                entry.instance_id,
            ))
            continue

        leader = ds.units.find(entry.datasheet_id)
        target_unit = ds.units.find(target.datasheet_id)
        if leader is None or target_unit is None:
            continue

        legal_bodyguard_ids = {
            bodyguard.id for bodyguard in ds.bodyguards_attachable_from(leader.id)
        }
        if target_unit.id not in legal_bodyguard_ids:
            violations.append(Violation(
                "ILLEGAL_LEADER_ATTACHMENT",
                Severity.ERROR,
                f"{leader.name} cannot attach to {target_unit.name}.",
                entry.instance_id,
            ))

    completed_attachment_paths = set()
    for entry in roster.entries:
        path = []
        path_positions = {}
        current = entry
        while current is not None and current.instance_id not in completed_attachment_paths:
            if current.instance_id in path_positions:
                cycle = path[path_positions[current.instance_id]:]
                if len(cycle) > 1:
                    violations.append(Violation(
                        "LEADER_ATTACHMENT_CYCLE",
                        Severity.ERROR,
                        "Leader attachments cannot create a cycle.",
                        current.instance_id,
                    ))
                break
            path_positions[current.instance_id] = len(path)
            path.append(current)
            current = entries_by_id.get(current.attached_to) if current.attached_to else None
        completed_attachment_paths.update(item.instance_id for item in path)

    # Rule 12: detachment must exist and belong to the roster's faction
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
                if not restrictions_met(unit, enh):
                    violations.append(Violation("ENHANCEMENT_RESTRICTED", Severity.ERROR,
                        f"{unit.name} is not eligible for {enh['name']}.", entry.instance_id))

    # Rule 13: Epic Heroes cannot take enhancements
    for entry in roster.entries:
        unit = ds.units.find(entry.datasheet_id)
        if entry.enhancement and unit and "EPIC HERO" in [k.upper() for k in unit.keywords]:
            violations.append(Violation("ENHANCEMENT_ON_EPIC_HERO", Severity.ERROR,
                f"{unit.name} is an EPIC HERO and cannot take an enhancement.", entry.instance_id))

    return violations