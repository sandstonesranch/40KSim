import json
import re
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Literal, Optional
from wh40kdc import Dataset
from .mathhammer import Context, Target, expected_damage, profile_from_dataset
from .validator import Roster, RosterEntry, validate
from .ai.advisor import get_suggestions
from .mcp_client import MCP_SERVER_DIR, call_mcp_tool, list_mcp_tools
from .enhancements import (
    base_name,
    describe_local,
    detachment_enhancements,
    enhancement_view,
    format_mcp_enhancement,
    mcp_entries_for,
    mcp_text_index,
    near_misses,
)


GENERIC_ASTARTES_DETACHMENTS = [
    "Gladius Task Force", "Anvil Siege Force", "Ironstorm Spearhead",
    "Vanguard Spearhead", "Firestorm Assault Force", "Stormlance Task Force",
    "Orbital Assault Force", "1st Company Task Force",
]

SUBFACTION_DETACHMENTS = {
    "Imperial Fists": ["Emperor’s Shield"],
    "Dark Angels": ["Unforgiven Task Force", "Inner Circle Task Force", "Company of Hunters", "Lion's Blade Task Force", "Dark Age Arsenal", "Darkflight Pursuit", "Interrogation Conclave", "Wrath of the Rock"],
    "Blood Angels": ["Sons of Sanguinius", "Liberator Assault Group", "Angelic Host", "Rage-cursed Onslaught"],
    "Space Wolves": ["Champions of Russ", "Saga of the Beastslayer", "Saga of the Great Wolf"],
    "Black Templars": ["Righteous Crusaders", "Wrathful Procession", "Godhammer Assault Force"],
}

SUBFACTION_FACTION_IDS = {
    "Imperial Fists": "imperial-fists",
    "Dark Angels": "dark-angels",
    "Blood Angels": "blood-angels",
    "Space Wolves": "space-wolves",
    "Black Templars": "black-templars",
}

ASTARTES_CHAPTER_FACTION_IDS = {
    "black-templars",
    "blood-angels",
    "crimson-fists",
    "dark-angels",
    "deathwatch",
    "imperial-fists",
    "iron-hands",
    "raven-guard",
    "salamanders",
    "space-wolves",
    "ultramarines",
    "white-scars",
}

ASTARTES_CHAPTER_KEYWORDS = {
    "black templars",
    "blood angels",
    "crimson fists",
    "dark angels",
    "deathwatch",
    "imperial fists",
    "iron hands",
    "raven guard",
    "salamanders",
    "space wolves",
    "ultramarines",
    "white scars",
}

MCP_FACTION_ALIASES = {
    "adeptus-astartes": "space-marines",
    "agents-of-the-imperium": "imperial-agents",
    "black-templars": "space-marines",
    "blood-angels": "space-marines",
    "crimson-fists": "space-marines",
    "dark-angels": "space-marines",
    "deathwatch": "space-marines",
    "imperial-fists": "space-marines",
    "iron-hands": "space-marines",
    "raven-guard": "space-marines",
    "salamanders": "space-marines",
    "space-wolves": "space-marines",
    "ultramarines": "space-marines",
    "white-scars": "space-marines",
}

WEAPON_ABILITIES = {
    "Assault": "This weapon can be shot even if the bearer's unit Advanced this turn.",
    "Rapid Fire": "Add the listed value to the weapon's Attacks when targeting a unit within half range.",
    "Ignores Cover": "The target cannot use the Benefit of Cover against this weapon.",
    "Twin-linked": "Re-roll the Wound roll for attacks made with this weapon.",
    "Pistol": "Can be fired even while within Engagement Range (only at an enemy in that combat).",
    "Torrent": "Attacks hit automatically — no Hit roll is made.",
    "Lethal Hits": "A Critical Hit (unmodified 6 to hit) automatically wounds the target.",
    "Lance": "Add 1 to the Wound roll for attacks made with this weapon if the bearer made a Charge move this turn.",
    "Indirect Fire": "Can target units not visible to the attacker, with penalties (-1 to Hit and target gains Benefit of Cover).",
    "Precision": "If the target unit has an attached Character, the attacker may allocate the wound to that Character.",
    "Blast": "Add 1 to the Attacks for every 5 models in the target unit; cannot target units within Engagement Range.",
    "Melta": "Improve the weapon's Damage by the listed value when targeting a unit within half range.",
    "Heavy": "Add 1 to the Hit roll if the bearer's unit Remained Stationary this turn.",
    "Hazardous": "After firing, roll one D6 per Hazardous weapon used; on a 1 or 2, a model in the unit is destroyed (Characters/Monsters/Vehicles instead take 3 mortal wounds).",
    "Devastating Wounds": "A Critical Wound (unmodified 6 to wound) inflicts its damage as mortal wounds — no saves of any kind are allowed.",
    "Sustained Hits": "Each Critical Hit (unmodified 6 to hit) scores the listed number of additional hits.",
    "Extra Attacks": "These attacks are made in addition to the model's other melee weapon attacks.",
    "Anti": "An unmodified Wound roll of the listed value or better against the listed keyword counts as a Critical Wound.",
    "One Shot": "The weapon can be shot only once per battle.",
    "Psychic": "A Psychic weapon/ability; interacts with rules affecting Psychic attacks.",
    "Close Quarters": "A weapon type used in Boarding Actions and close-range engagements.",
}


app = FastAPI(title="40Ksim Validator API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ds = Dataset.embedded()


def mcp_faction_id(faction_id: str) -> str:
    faction_name = faction_id.split("|", 1)[0].strip()
    normalized_id = faction_name.casefold().replace(" ", "-")
    if normalized_id in MCP_FACTION_ALIASES:
        return MCP_FACTION_ALIASES[normalized_id]

    faction = next(
        (
            faction
            for faction in ds.factions
            if faction.id.casefold() == normalized_id
            or faction.name.casefold() == faction_name.casefold()
        ),
        None,
    )
    if faction:
        normalized_name = faction.name.casefold().replace(" ", "-")
        return MCP_FACTION_ALIASES.get(normalized_name, normalized_name)
    return normalized_id


@lru_cache(maxsize=64)
def load_mcp_faction_file(faction_id: str, filename: str) -> list[dict]:
    if filename not in {"detachments.json", "enhancements.json"}:
        raise ValueError(f"Unsupported 40k MCP data file: {filename}")

    if not faction_id:
        data_dir = MCP_SERVER_DIR / "data"
        try:
            faction_dirs = [
                path for path in data_dir.iterdir()
                if path.is_dir() and path.name != "index"
            ]
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=503,
                detail=f"40k MCP data directory is unavailable: {data_dir}",
            ) from error
        return [
            item
            for faction_dir in faction_dirs
            for item in load_mcp_faction_file(faction_dir.name, filename)
        ]

    if not re.fullmatch(r"[a-z0-9-]+", faction_id):
        raise HTTPException(status_code=400, detail="Invalid faction identifier")

    path = MCP_SERVER_DIR / "data" / faction_id / filename
    try:
        with path.open(encoding="utf-8") as data_file:
            data = json.load(data_file)
    except FileNotFoundError as error:
        raise HTTPException(
            status_code=503,
            detail=f"40k MCP data file is unavailable: {path}",
        ) from error
    except json.JSONDecodeError as error:
        raise HTTPException(
            status_code=502,
            detail=f"40k MCP data file contains invalid JSON: {path}",
        ) from error
    if not isinstance(data, list):
        raise HTTPException(
            status_code=502,
            detail=f"40k MCP data file has an unexpected format: {path}",
        )
    return data


async def call_40k_tool(tool_name: str, arguments: dict) -> str:
    result = await call_mcp_tool(tool_name, arguments)
    if result.startswith("Error"):
        raise HTTPException(status_code=502, detail=result)
    return result


def normalize_rule_name(name: str) -> str:
    return name.casefold().replace("’", "'").strip()


def safe_load_mcp_faction_file(faction_id: str, filename: str, warnings: list[str]) -> list[dict]:
    """Like load_mcp_faction_file, but a missing/broken MCP file becomes a warning."""
    try:
        return load_mcp_faction_file(faction_id, filename)
    except HTTPException as error:
        warnings.append(f"40k MCP {filename} for '{faction_id}': {error.detail}")
        return []


def find_detachment(value: str) -> Optional[dict]:
    """Detachment by dataset id or (case-insensitive) name."""
    if not value:
        return None
    by_id = next((d for d in ds.detachments if d.get("id") == value), None)
    if by_id:
        return by_id
    wanted = normalize_rule_name(value)
    return next((d for d in ds.detachments if normalize_rule_name(d.get("name", "")) == wanted), None)


def build_detachment_enhancements(detachment: dict, faction_id: str, warnings: list[str]) -> list[dict]:
    """Enhancements for a detachment: wh40kdc is authoritative, MCP only adds text."""
    detachment_name = detachment.get("name", "")
    mcp_all = safe_load_mcp_faction_file(faction_id, "enhancements.json", warnings)
    mcp_matches = mcp_entries_for(mcp_all, detachment_name)
    text_index = mcp_text_index(mcp_matches)
    local = detachment_enhancements(ds, detachment)

    views = []
    for enhancement in local:
        match = text_index.get(base_name(enhancement.get("name", "")))
        views.append(enhancement_view(
            enhancement,
            description=((match or {}).get("effect") or "").strip(),
            source="wh40kdc+mcp" if match else "wh40kdc",
        ))

    if not local:
        # Dataset has none for this detachment: fall back to whatever MCP lists.
        for item in mcp_matches:
            cost = item.get("pointsCost")
            views.append({
                "id": base_name(item.get("name", "")).replace(" ", "-"),
                "name": item.get("name", "Enhancement"),
                "cost": cost if isinstance(cost, int) else 0,
                "upgrade": False,
                "max_targets": 1,
                "keyword_restrictions": [],
                "points_provisional": False,
                "description": (item.get("effect") or "").strip(),
                "description_available": bool((item.get("effect") or "").strip()),
                "source": "mcp",
            })

    # Diagnostics: remove once the MCP data is known to be in step with the dataset.
    print(
        f"[enhancements] {detachment.get('id')} faction={faction_id} "
        f"local={len(local)} mcp_file_entries={len(mcp_all)} "
        f"mcp_for_detachment={len(mcp_matches)} "
        f"with_text={sum(1 for v in views if v['description_available'])}",
        flush=True,
    )
    if mcp_matches:
        print(f"[enhancements]   mcp_results={json.dumps(mcp_matches, ensure_ascii=False)[:600]}", flush=True)
    elif mcp_all:
        names = {item.get("detachment", "") for item in mcp_all}
        print(
            f"[enhancements]   MCP has no enhancements for detachment {detachment_name!r}; "
            f"nearest MCP detachment names: {near_misses(detachment_name, names)}",
            flush=True,
        )
    return views


def enhancement_rule_text(name: str, faction: str = "", detachment: str = "") -> str:
    """Readable rules text for one enhancement, never raw JSON and never empty."""
    warnings: list[str] = []
    faction_id = mcp_faction_id(faction)
    detachment_record = find_detachment(detachment)
    detachment_name = detachment_record.get("name", "") if detachment_record else detachment
    wanted = base_name(name)

    entries = safe_load_mcp_faction_file(faction_id, "enhancements.json", warnings)
    if detachment_name:
        entries = mcp_entries_for(entries, detachment_name) or entries
    exact = [item for item in entries if base_name(item.get("name", "")) == wanted]
    loose = [item for item in entries if wanted and wanted in base_name(item.get("name", ""))]
    matches = exact or loose
    if matches:
        return "\n\n".join(format_mcp_enhancement(item) for item in matches)

    pool = detachment_enhancements(ds, detachment_record) if detachment_record else list(ds.enhancements)
    local = next((e for e in pool if base_name(e.get("name", "")) == wanted), None)
    if local is not None:
        return describe_local(local)
    suffix = f" ({'; '.join(warnings)})" if warnings else ""
    return f"No rules text found for {name}.{suffix}"


def parse_abilities_text(abilities_text: str) -> list[dict[str, str]]:
    abilities = []
    current_ability = None

    for line in abilities_text.strip().splitlines():
        match = re.match(r"\s*(?:-\s*)?\*\*(.+?):\*\*\s*(.*)", line)
        if match:
            current_ability = {"name": match.group(1), "text": match.group(2)}
            abilities.append(current_ability)
        elif current_ability and line.strip():
            current_ability["text"] += f"\n{line.strip()}"

    if not abilities and abilities_text.strip():
        return [{"name": "Abilities", "text": abilities_text.strip()}]
    return abilities


def parse_mcp_stratagems(text: str) -> list[dict]:
    if text.startswith("No stratagems found"):
        return []

    _, separator, body = text.partition("\n\n")
    if not separator:
        raise HTTPException(
            status_code=502,
            detail="40k MCP returned stratagem data in an unexpected format",
        )

    stratagems = []
    for block in body.split("\n\n---\n\n"):
        lines = block.splitlines()
        if not lines:
            continue
        heading = re.match(r"\*\*(.+?)\*\* \((.+?)CP\) — (.+)", lines[0])
        if not heading:
            raise HTTPException(
                status_code=502,
                detail="40k MCP returned stratagem data in an unexpected format",
            )

        sections = {}
        for line in lines[1:]:
            section = re.match(
                r"\*\*(WHEN|TARGET|EFFECT|RESTRICTIONS):\*\*\s*(.*)",
                line,
            )
            if section:
                sections[section.group(1)] = section.group(2)
        description = "\n".join(
            f"{label}: {sections[label]}"
            for label in ("WHEN", "TARGET", "EFFECT", "RESTRICTIONS")
            if sections.get(label)
        )
        stratagems.append({
            "name": heading.group(1),
            "cp_cost": heading.group(2),
            "description": description,
        })
    return stratagems


def find_unit_by_name(unit_name: str, faction_id: str = ""):
    requested_faction = faction_id.split("|", 1)[0].strip().casefold()
    subfaction = faction_id.split("|", 1)[1].strip().casefold() if "|" in faction_id else ""
    matching_units = [
        unit for unit in ds.units
        if unit.name.casefold() == unit_name.strip().casefold()
    ]
    if requested_faction:
        matching_units = [
            unit for unit in matching_units
            if unit.faction_id.casefold() == requested_faction
            or (
                subfaction
                and any(keyword.casefold() == subfaction for keyword in unit.faction_keywords)
            )
        ]
    return matching_units[0] if matching_units else None
FACTION_METADATA_PATH = (
    Path(__file__).resolve().parents[3]
    / "data-schema"
    / "factions"
    / "faction_metadata.json"
)


def get_weapon_name(weapon_id: str) -> str:
    """Helper to turn a weapon ID into a readable name."""
    weapon = ds.weapons.find(weapon_id)
    if weapon:
        return getattr(weapon, 'name', weapon_id)
    return weapon_id


class EntryData(BaseModel):
    instance_id: str
    datasheet_id: str
    size: int
    is_warlord: bool = False
    enhancement: Optional[str] = None
    attached_to: Optional[str] = None

class RosterData(BaseModel):
    faction_id: str
    detachment_id: str
    points_limit: int
    entries: List[EntryData]


class MathhammerContext(BaseModel):
    models_firing: int = Field(default=1, ge=1)
    in_half_range: bool = False
    target_models: int = Field(default=1, ge=1)
    hit_modifier: int = Field(default=0, ge=-10, le=10)
    wound_modifier: int = Field(default=0, ge=-10, le=10)
    reroll_hits: Literal["none", "ones", "all"] = "none"
    reroll_wounds: Literal["none", "ones", "all"] = "none"


class MathhammerRequest(BaseModel):
    attacker_id: str
    weapon_id: str
    profile_index: int = Field(default=0, ge=0)
    defender_toughness: int = Field(gt=0)
    defender_save: int = Field(ge=2, le=7)
    defender_wounds: int = Field(gt=0)
    defender_invuln: Optional[int] = Field(default=None, ge=2, le=7)
    defender_fnp: Optional[int] = Field(default=None, ge=2, le=6)
    defender_keywords: list[str] = Field(default_factory=list)
    context: MathhammerContext = Field(default_factory=MathhammerContext)


@app.get("/")
def read_root():
    return {"status": "ok"}

@app.get("/api/factions")
def get_factions():
    faction_list = []
    chapter_names = {
        faction.id: faction.name
        for faction in ds.factions
        if faction.id in ASTARTES_CHAPTER_FACTION_IDS
    }

    for faction in ds.factions:
        if faction.id in ASTARTES_CHAPTER_FACTION_IDS:
            continue

        subfactions = set()
        faction_units = [unit for unit in ds.units if unit.faction_id == faction.id]

        for unit in faction_units:
            for keyword in unit.faction_keywords:
                if keyword.upper() != faction.name.upper() and len(keyword) > 2:
                    if keyword.upper() not in ["IMPERIUM", "CHAOS", "XENOS", "AELDARI"]:
                        subfactions.add(keyword)

        if faction.id == "adeptus-astartes":
            subfactions.update(chapter_names.values())

        faction_list.append({
            "id": faction.id,
            "name": faction.name,
            "subfactions": sorted(list(subfactions))
        })

    return faction_list


@app.get("/api/faction-metadata/{faction_id}")
def get_faction_metadata(faction_id: str):
    try:
        with FACTION_METADATA_PATH.open(encoding="utf-8") as metadata_file:
            metadata = json.load(metadata_file)
    except FileNotFoundError as error:
        raise HTTPException(status_code=500, detail="Faction metadata file was not found") from error
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=500, detail="Faction metadata file contains invalid JSON") from error

    return metadata.get(
        faction_id,
        {"lore": "", "playstyle": "", "subfactions": {}},
    )

@app.get("/api/detachments")
def get_detachments(faction_id: str = "", subfaction: str = ""):
    results = ds.detachments
    if faction_id == "adeptus-astartes":
        allowed_names = GENERIC_ASTARTES_DETACHMENTS + (
            SUBFACTION_DETACHMENTS.get(subfaction, []) if subfaction else []
        )
        allowed_faction_ids = {"adeptus-astartes"}
        if subfaction in SUBFACTION_FACTION_IDS:
            allowed_faction_ids.add(SUBFACTION_FACTION_IDS[subfaction])

        filtered_results = []
        seen_ids = set()
        for detachment in results:
            detachment_id = detachment.get("id")
            if (
                detachment.get("faction_id") in allowed_faction_ids
                and detachment.get("name") in allowed_names
                and detachment_id not in seen_ids
            ):
                filtered_results.append({
                    "id": detachment_id,
                    "name": detachment.get("name"),
                })
                seen_ids.add(detachment_id)
        return filtered_results
    if faction_id:
        results = [d for d in results if d.get('faction_id') == faction_id]

    return [{"id": d.get('id'), "name": d.get('name')} for d in results]

@app.get("/api/detachments/{detachment_id}")
async def get_detachment_details(detachment_id: str):
    detachment = next((d for d in ds.detachments if d.get('id') == detachment_id), None)
    if not detachment:
        raise HTTPException(status_code=404, detail="Detachment not found")

    warnings: list[str] = []
    faction_id = mcp_faction_id(detachment.get("faction_id", ""))
    detachment_name = detachment.get("name", "")
    mcp_detachment = next(
        (
            item
            for item in safe_load_mcp_faction_file(faction_id, "detachments.json", warnings)
            if normalize_rule_name(item.get("name", ""))
            == normalize_rule_name(detachment_name)
        ),
        {},
    )
    rule_text = mcp_detachment.get("ruleText", "").strip()
    if not rule_text:
        rule_text = (
            "Full rules text currently unavailable from 40k MCP data. "
            "Please check the official supplement."
        )

    try:
        stratagem_text = await call_40k_tool(
            "list_stratagems",
            {
                "faction": faction_id,
                "detachment": detachment_name.replace("’", "'"),
            },
        )
        stratagems = parse_mcp_stratagems(stratagem_text)
    except HTTPException as error:
        warnings.append(f"Stratagems unavailable: {error.detail}")
        stratagems = []

    return {
        "id": detachment.get("id"),
        "name": mcp_detachment.get("name", detachment_name),
        "rules": [{
            "name": mcp_detachment.get("ruleName", "Detachment Ability"),
            "description": rule_text,
        }],
        "stratagems": stratagems,
        "enhancements": build_detachment_enhancements(detachment, faction_id, warnings),
        "detachment_points": detachment.get("detachment_points"),
        "warnings": warnings,
    }


@app.get("/api/debug/enhancements/{detachment_id}")
async def debug_enhancements(detachment_id: str):
    """Where do a detachment's enhancements come from? Local-dev diagnostic."""
    detachment = find_detachment(detachment_id)
    if not detachment:
        raise HTTPException(status_code=404, detail="Detachment not found")
    faction_id = mcp_faction_id(detachment.get("faction_id", ""))
    warnings: list[str] = []
    mcp_all = safe_load_mcp_faction_file(faction_id, "enhancements.json", warnings)
    matches = mcp_entries_for(mcp_all, detachment.get("name", ""))
    mcp_names = {item.get("detachment", "") for item in mcp_all}
    return {
        "detachment": {k: detachment.get(k) for k in ("id", "name", "faction_id", "detachment_points")},
        "mcp_server_dir": str(MCP_SERVER_DIR),
        "mcp_server_dir_exists": MCP_SERVER_DIR.exists(),
        "mcp_faction_id": faction_id,
        "mcp_enhancements_file": str(MCP_SERVER_DIR / "data" / faction_id / "enhancements.json"),
        "mcp_file_entries": len(mcp_all),
        "mcp_detachment_names": sorted(n for n in mcp_names if n),
        "mcp_matches_for_detachment": matches,
        "nearest_mcp_detachment_names": near_misses(detachment.get("name", ""), mcp_names),
        "local_enhancements": [
            {k: e.get(k) for k in ("id", "name", "cost", "upgrade_tag", "max_targets", "keyword_restrictions")}
            for e in detachment_enhancements(ds, detachment)
        ],
        "mcp_tools": await list_mcp_tools(),
        "warnings": warnings,
    }

@app.get("/api/search")
def search_units(q: str = "", faction_id: str = "", limit: int = Query(500, ge=1, le=1000)):
    results = ds.units
    if faction_id:
        if "|" in faction_id:
            main_id, sub_name = faction_id.split("|", 1)
            if main_id == "adeptus-astartes":
                selected_chapter = sub_name.casefold()
                results = [
                    unit
                    for unit in results
                    if unit.faction_id == main_id
                    and (
                        selected_chapter in {
                            keyword.casefold() for keyword in unit.faction_keywords
                        }
                        or not (
                            {
                                keyword.casefold() for keyword in unit.faction_keywords
                            } & ASTARTES_CHAPTER_KEYWORDS
                        )
                    )
                ]
            else:
                results = [
                    unit for unit in results
                    if unit.faction_id == main_id
                    and any(sub_name.casefold() == keyword.casefold() for keyword in unit.faction_keywords)
                ]
        else:
            results = [u for u in results if u.faction_id == faction_id]
    if q:
        results = [u for u in results if q.lower() in u.name.lower()]
    results = results[:limit]

    grouped = {
        "Epic Heroes": [],
        "Characters": [],
        "Battleline": [],
        "Dedicated Transports": [],
        "Allied Units": [],
        "Vehicles": [],
        "Monsters": [],
        "Infantry": [],
        "Mounted": [],
        "Aircraft": [],
        "Fortifications": [],
    }

    for u in results:
        unit_data = {"id": u.id, "name": u.name, "points": u.points[0]["cost"] if u.points else 0}
        role = getattr(u, 'role', None)
        keywords = {keyword.upper() for keyword in u.keywords}

        if role == "epic-hero":
            group = "Epic Heroes"
        elif role == "character":
            group = "Characters"
        elif role == "battleline":
            group = "Battleline"
        elif role == "dedicated-transport":
            group = "Dedicated Transports"
        elif role == "allied":
            group = "Allied Units"
        elif "VEHICLE" in keywords:
            group = "Vehicles"
        elif "MONSTER" in keywords:
            group = "Monsters"
        elif "MOUNTED" in keywords:
            group = "Mounted"
        elif "AIRCRAFT" in keywords:
            group = "Aircraft"
        elif "INFANTRY" in keywords:
            group = "Infantry"
        else:
            group = "Fortifications"

        grouped[group].append(unit_data)

    return grouped

@app.get("/api/units/{unit_id}")
def get_unit_details(unit_id: str, detachment_id: str = ""):
    unit = ds.units.find(unit_id)
    if not unit:
        raise HTTPException(status_code=404, detail="Unit not found")

    profile = unit.profile_at(0) if unit.profile_count > 0 else {}

    abilities_data = []
    if hasattr(unit, 'abilities'):
        for a in unit.abilities:
            a_name = getattr(a, 'name', a.get('name') if isinstance(a, dict) else 'Unknown')
            a_text = getattr(a, 'text', a.get('text') if isinstance(a, dict) else '')
            abilities_data.append({"name": a_name, "text": a_text})

    # Ultra-defensive weapon stat extraction (handles multiple profiles)
    weapons_data = []
    for w in unit.weapons:
        raw_stats = getattr(w, 'raw', {})
        profiles = raw_stats.get('profiles', [raw_stats]) if isinstance(raw_stats, dict) else [raw_stats]

        for profile_index, p in enumerate(profiles):
            if not isinstance(p, dict) or not p:
                continue

            def get_stat(keys):
                for key in keys:
                    if key in p and p[key] is not None:
                        return p[key]
                nested_stats = p.get("stats", {})
                if isinstance(nested_stats, dict):
                    for key in keys:
                        if key in nested_stats and nested_stats[key] is not None:
                            return nested_stats[key]
                return "-"

            range_val = get_stat(["range", "Range"])
            profile_name = str(p.get("name", "")).lower()
            is_melee = "melee" in profile_name or str(range_val).lower() == "melee"

            stats = {
                "Range": range_val,
                "A": get_stat(["a", "A", "attacks", "Attacks"]),
                "BS": get_stat(["bs", "BS", "ws", "WS", "skill", "Skill", "ballistic_skill", "weapon_skill"]),
                "WS": get_stat(["ws", "WS"]),
                "S": get_stat(["s", "S", "strength", "Strength"]),
                "AP": get_stat(["ap", "AP", "armor_penetration", "Armor Penetration"]),
                "D": get_stat(["d", "D", "damage", "Damage"]),
            }

            raw_keywords = p.get("keywords", []) or p.get("Keywords", [])
            if isinstance(raw_keywords, (str, dict)):
                raw_keywords = [raw_keywords]
            elif not isinstance(raw_keywords, (list, tuple)):
                raw_keywords = []
            clean_keywords = []
            for keyword in raw_keywords:
                if isinstance(keyword, str):
                    clean_keywords.append(keyword)
                elif isinstance(keyword, dict):
                    keyword_id = keyword.get("keyword_id")
                    if isinstance(keyword_id, str):
                        clean_keywords.append(keyword_id.replace('-', ' ').title())
                    elif "name" in keyword:
                        clean_keywords.append(keyword["name"])

            weapons_data.append({
                "id": w.id,
                "profile_index": profile_index,
                "name": w.name,
                "stats": stats,
                "keywords": clean_keywords,
                "is_melee": is_melee,
            })

    # Extract and resolve wargear options
    wargear_data = []
    for w in getattr(unit, 'wargear_options', []):
        raw = getattr(w, 'raw', w)

        replaces_ids = raw.get('replaces', []) or []
        choice_options = raw.get('replacement', raw.get('replacement_choice', [])) or []

        replaces_names = [get_weapon_name(weapon_id) for weapon_id in replaces_ids]
        choice_names = [
            " + ".join(get_weapon_name(weapon_id) for weapon_id in choice)
            if isinstance(choice, list)
            else get_weapon_name(choice)
            for choice in choice_options
        ]

        wargear_data.append({
            "replaces": replaces_names,
            "choices": choice_names,
            "is_free": raw.get('is_free', True)
        })

    available_enhancements = []
    if detachment_id:
        detachment = next(
            (d for d in ds.detachments if d.get('id') == detachment_id),
            None
        )
        # `eligible` already accounts for Character vs Upgrade, Epic Hero and
        # keyword restrictions, so the client needs no rules of its own.
        available_enhancements = [
            enhancement_view(enhancement, unit=unit)
            for enhancement in detachment_enhancements(ds, detachment)
        ]

    # Build exactly the squad sizes allowed by the rules
    points_options = []
    seen_sizes = set()

    for tier in unit.points:
        if "models_max" in tier and tier["models_max"] is not None:
            size = tier["models_max"]
        else:
            size = tier["models"]

        if size not in seen_sizes:
            points_options.append({"models": size, "cost": tier["cost"]})
            seen_sizes.add(size)

    points_options.sort(key=lambda option: option["models"])

    return {
        "id": unit.id,
        "name": unit.name,
        "keywords": unit.keywords,
        "stats": {
            "M": profile.get("M", "-"), "T": profile.get("T", "-"),
            "SV": profile.get("Sv", "-"), "W": profile.get("W", "-"),
            "LD": profile.get("Ld", "-"), "OC": profile.get("OC", "-"),
        },
        "weapons": weapons_data,
        "wargear_options": wargear_data,
        "abilities": abilities_data,
        "points_options": points_options,
        "available_enhancements": available_enhancements
    }


@app.get("/api/legal-bodyguards/{unit_id}")
def get_legal_bodyguards(unit_id: str) -> list[str]:
    unit = ds.units.find(unit_id)
    if unit is None:
        raise HTTPException(status_code=404, detail="Unit not found")
    return [
        bodyguard.id
        for bodyguard in ds.bodyguards_attachable_from(unit.id)
    ]


@app.get("/api/codex/detachment/{detachment_name}")
async def get_codex_detachment(detachment_name: str, faction: str = ""):
    faction_id = faction.split("|", 1)[0].casefold()
    subfaction = faction.split("|", 1)[1] if "|" in faction else ""
    subfaction_id = SUBFACTION_FACTION_IDS.get(subfaction, "").casefold()
    detachment = next(
        (
            item
            for item in ds.detachments
            if normalize_rule_name(item.get("name", ""))
            == normalize_rule_name(detachment_name)
            and (
                not faction
                or item.get("faction_id", "").casefold() == faction_id
                or (
                    subfaction_id
                    and item.get("faction_id", "").casefold() == subfaction_id
                )
            )
        ),
        None,
    )
    if not detachment:
        raise HTTPException(status_code=404, detail="Detachment not found")
    details = await get_detachment_details(detachment["id"])
    return {"id": detachment_name, "text": json.dumps(details, ensure_ascii=False)}

@app.get("/api/codex/unit/{unit_name}")
async def get_codex_unit(unit_name: str, faction: str = ""):
    unit = find_unit_by_name(unit_name, faction)
    if not unit:
        raise HTTPException(status_code=404, detail="Datasheet not found")

    raw_text = await call_40k_tool(
        "get_unit",
        {"faction": mcp_faction_id(unit.faction_id), "name": unit.name},
    )
    # Extract ONLY the Abilities section
    abilities_match = re.search(r'##\s*Abilities\s*(.*?)(?=##|$)', raw_text, re.DOTALL | re.IGNORECASE)

    if abilities_match:
        abilities_text = abilities_match.group(1)
        parsed = parse_abilities_text(abilities_text)
    else:
        parsed = []

    return {
        "name": unit.name,
        "abilities": parsed,
    }

@app.get("/api/codex/enhancement/{enhancement_name}")
async def get_codex_enhancement(enhancement_name: str, faction: str = ""):
    return {"id": enhancement_name, "text": enhancement_rule_text(enhancement_name, faction)}

@app.get("/api/codex/stratagem/{stratagem_name}")
async def get_codex_stratagem(stratagem_name: str, faction: str = ""):
    result = await call_40k_tool(
        "list_stratagems",
        {
            "keyword": stratagem_name,
            "faction": mcp_faction_id(faction) if faction else "",
        },
    )
    return {"id": stratagem_name, "text": result}

@app.get("/api/codex/rule")
async def get_codex_rule(type: str, name: str, faction: str = "", detachment: str = ""):
    if type == "detachment":
        return await get_codex_detachment(name, faction)
    elif type == "stratagem":
        result = await call_40k_tool(
            "list_stratagems",
            {
                "keyword": name,
                "faction": mcp_faction_id(faction) if faction else "",
                "detachment": detachment.replace("’", "'") if detachment else "",
            },
        )
        text = result
    elif type == "enhancement":
        text = enhancement_rule_text(name, faction, detachment)
    elif type == "ability":
        unit = find_unit_by_name(name, faction)
        if not unit:
            raise HTTPException(status_code=404, detail="Datasheet not found")
        text = await call_40k_tool(
            "get_unit",
            {
                "faction": mcp_faction_id(unit.faction_id),
                "name": unit.name,
            },
        )
    else:
        raise HTTPException(status_code=400, detail="Invalid rule type")

    return {"type": type, "name": name, "text": text}

@app.get("/api/keywords/{keyword_name}")
async def get_keyword_definition(keyword_name: str):
    normalized_keyword = keyword_name.strip()
    matching_keyword = next(
        (
            keyword
            for keyword in sorted(WEAPON_ABILITIES, key=len, reverse=True)
            if normalized_keyword.casefold() == keyword.casefold()
            or normalized_keyword.casefold().startswith(keyword.casefold() + " ")
            or normalized_keyword.casefold().startswith(keyword.casefold() + "-")
        ),
        None,
    )

    if matching_keyword:
        return {
            "keyword": matching_keyword,
            "definition": WEAPON_ABILITIES[matching_keyword],
        }

    return {
        "keyword": normalized_keyword,
        "definition": "No definition found for this keyword.",
    }


@app.post("/api/mathhammer")
def calculate_mathhammer(request: MathhammerRequest):
    attacker = ds.units.find(request.attacker_id)
    if attacker is None:
        raise HTTPException(status_code=404, detail="Attacker datasheet not found")

    weapon = next(
        (item for item in attacker.weapons if item.id == request.weapon_id),
        None,
    )
    if weapon is None:
        raise HTTPException(
            status_code=404,
            detail=f"Weapon '{request.weapon_id}' not found on {attacker.name}",
        )

    profiles = weapon.raw.get("profiles", [])
    if request.profile_index >= len(profiles):
        raise HTTPException(
            status_code=404,
            detail=f"Weapon profile {request.profile_index} not found",
        )

    profile = profile_from_dataset(weapon.raw, profiles[request.profile_index])
    target = Target(
        toughness=request.defender_toughness,
        save=request.defender_save,
        wounds=request.defender_wounds,
        invuln=request.defender_invuln,
        fnp=request.defender_fnp,
        keywords=frozenset(keyword.upper() for keyword in request.defender_keywords),
    )
    result = expected_damage(
        profile,
        target,
        Context(**request.context.model_dump()),
    )
    return {
        "attacker_id": attacker.id,
        "attacker_name": attacker.name,
        "weapon_id": weapon.id,
        "weapon_name": weapon.name,
        "profile_index": request.profile_index,
        "profile_name": profiles[request.profile_index].get("name", ""),
        "result": asdict(result),
    }


@app.post("/api/validate")
def validate_roster(roster_data: RosterData):
    entries = [RosterEntry(instance_id=e.instance_id, datasheet_id=e.datasheet_id, size=e.size, is_warlord=e.is_warlord, enhancement=e.enhancement, attached_to=e.attached_to) for e in roster_data.entries]
    roster = Roster(faction_id=roster_data.faction_id, detachment_id=roster_data.detachment_id, points_limit=roster_data.points_limit, entries=entries)
    violations = validate(roster, ds)
    return {"violations": [v.__dict__ for v in violations]}

@app.post("/api/advise")
def get_advice(roster_data: RosterData):
    entries = [RosterEntry(instance_id=e.instance_id, datasheet_id=e.datasheet_id, size=e.size, is_warlord=e.is_warlord, enhancement=e.enhancement, attached_to=e.attached_to) for e in roster_data.entries]
    roster = Roster(faction_id=roster_data.faction_id, detachment_id=roster_data.detachment_id, points_limit=roster_data.points_limit, entries=entries)
    suggestions = get_suggestions(roster, "gunline", ds)
    return {"suggestions": [s.__dict__ for s in suggestions]}