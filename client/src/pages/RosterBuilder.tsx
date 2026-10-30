import { useState, useEffect, useRef, type ChangeEvent } from 'react';
import { Link } from 'react-router-dom';
import '../App.css';
import RulesText from '../components/RulesText';

const cleanMarkdown = (text: string | undefined | null) => {
  if (!text || typeof text !== 'string') return "";
  return text
    .replace(/#{1,6}\s/g, '')
    .replace(/\*\*/g, '')
    .replace(/\*/g, '')
    .replace(/\^\^/g, '')
    .replace(/\[Mode:.*?\]\n?/gi, '')
    .replace(/Game: Warhammer 40,000.*?\n?/gi, '')
    .replace(/^>.*$/gm, '')
    .replace(/^Effect\n/gi, '')
    .replace(/Detachment Ability:\s?/gi, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
};

type Faction = { id: string; name: string; subfactions: string[]; };
type Detachment = { id: string; name: string; };
type Unit = { id: string; name: string; points: number; };
type GroupedUnits = { [key: string]: Unit[]; };
type WargearSelection = { name: string; replaced: string[]; quantity: number };
type RosterItem = Unit & { instanceId: string; size: number; is_warlord: boolean; wargear: WargearSelection[]; keywords: string[]; enhancement: any | null; attached_to?: string | null; };
type Violation = { code: string; severity: string; message: string; };
type Suggestion = { missing_role: string; suggested_unit_id: string; suggested_unit_name: string; points: number; reason: string; };
type WargearOption = { replaces: string[]; choices: string[]; is_free: boolean; };

const normalizeWargear = (wargear: unknown): WargearSelection[] => {
  if (!Array.isArray(wargear)) return [];

  return wargear.flatMap((item): WargearSelection[] => {
    if (typeof item === 'string') return [{ name: item, replaced: [], quantity: 1 }];
    if (
      typeof item === 'object' &&
      item !== null &&
      'name' in item &&
      typeof item.name === 'string'
    ) {
      return [{
        name: item.name,
        replaced: 'replaced' in item && Array.isArray(item.replaced)
          ? item.replaced.filter((name: unknown): name is string => typeof name === 'string')
          : [],
        quantity: 'quantity' in item && typeof item.quantity === 'number' && Number.isInteger(item.quantity) && item.quantity > 0
          ? item.quantity
          : 1,
      }];
    }
    return [];
  });
};

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

type DetachmentDetails = {
  id?: string;
  name: string;
  rules?: { name?: string; description?: string }[];
  stratagems?: { name?: string; cp_cost?: number | string; description?: string }[];
  enhancements?: { name?: string; cost?: number | string; description?: string }[];
  error?: string;
};

type UnitDetails = {
  id: string;
  name: string;
  keywords: string[];
  stats: { M: string; T: string; SV: string; W: string; LD: string; OC: string; };
  weapons: { id: string; profile_index: number; name: string; stats: any; keywords: string[]; is_melee?: boolean }[];
  wargear_options?: WargearOption[];
  available_enhancements: any[];
  abilities: { name: string; text: string }[];
  points_options: {
    cost: number;
    models: number;
    unit_count_min?: number | null;
    unit_count_max?: number | null;
  }[];
};

type SavedRosterData = {
  roster?: RosterItem[];
  selectedFaction?: string;
  selectedDetachment?: string;
  pointsLimit?: number;
};

function RosterBuilder() {
  const [savedData] = useState<SavedRosterData>(() => {
    try {
      const saved = localStorage.getItem('40k_roster_data');
      if (!saved) return {};

      const parsed: unknown = JSON.parse(saved);
      if (!isRecord(parsed)) return {};
      const roster = Array.isArray(parsed.roster)
        ? parsed.roster.flatMap((item): RosterItem[] => {
            if (!isRecord(item)) return [];
            const { id, name, instanceId, size, points } = item;
            if (
              typeof id !== 'string' ||
              typeof name !== 'string' ||
              typeof instanceId !== 'string' ||
              typeof size !== 'number' ||
              !Number.isFinite(size) ||
              typeof points !== 'number' ||
              !Number.isFinite(points)
            ) {
              return [];
            }

            return [{
              id,
              name,
              instanceId,
              size,
              points,
              is_warlord: item.is_warlord === true,
              wargear: normalizeWargear(item.wargear),
              keywords: Array.isArray(item.keywords)
                ? item.keywords.filter((keyword): keyword is string => typeof keyword === 'string')
                : [],
              enhancement: item.enhancement ?? null,
              attached_to: typeof item.attached_to === 'string' ? item.attached_to : null,
            }];
          })
        : [];

      return {
        roster,
        selectedFaction: typeof parsed.selectedFaction === 'string' ? parsed.selectedFaction : undefined,
        selectedDetachment: typeof parsed.selectedDetachment === 'string' ? parsed.selectedDetachment : undefined,
        pointsLimit: typeof parsed.pointsLimit === 'number' && Number.isFinite(parsed.pointsLimit)
          ? parsed.pointsLimit
          : undefined,
      };
    } catch (error) {
      console.error('Failed to load saved roster data', error);
      return {};
    }
  });
  const [factions, setFactions] = useState<Faction[]>([]);
  const [selectedFaction, setSelectedFaction] = useState<string>(savedData.selectedFaction || "");
  const [selectionStep, setSelectionStep] = useState<'grid' | 'faction' | 'subfaction' | 'subfaction-details'>('grid');
  const [tempFaction, setTempFaction] = useState<any>(null);
  const [factionMeta, setFactionMeta] = useState<any>(null);
  const [previewDetachments, setPreviewDetachments] = useState<any[]>([]);
  const [tempSubfaction, setTempSubfaction] = useState<any>(null);
  const [selectionError, setSelectionError] = useState<string | null>(null);
  const [isLoadingFaction, setIsLoadingFaction] = useState(false);

  // NEW: Detachment & Points State
  const [detachments, setDetachments] = useState<Detachment[]>([]);
  const [selectedDetachment, setSelectedDetachment] = useState<string>(savedData.selectedDetachment || "");
  const [pointsLimit, setPointsLimit] = useState<number>(savedData.pointsLimit || 2000);

  const [search, setSearch] = useState("");
  const [unitCategoryFilter, setUnitCategoryFilter] = useState("all");
  const [groupedUnits, setGroupedUnits] = useState<GroupedUnits>({});
  const [searchError, setSearchError] = useState<string | null>(null);
  const [openGroups, setOpenGroups] = useState<{ [key: string]: boolean }>({
    Characters: true,
    Battleline: true,
    Vehicles: true,
    Monsters: true,
    Infantry: true,
  });

  const [roster, setRoster] = useState<RosterItem[]>(
    savedData.roster || []
  );
  const [violations, setViolations] = useState<Violation[]>([]);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);

  const [selectedUnitDetails, setSelectedUnitDetails] = useState<UnitDetails | null>(null);
  const [unitDetailsError, setUnitDetailsError] = useState<string | null>(null);
  const [canLeadUnits, setCanLeadUnits] = useState<string[]>([]);
  const [legalBodyguardIds, setLegalBodyguardIds] = useState<Record<string, string[]>>({});
  const [leaderAttachmentErrors, setLeaderAttachmentErrors] = useState<Record<string, string>>({});
  const [unitRulesText, setUnitRulesText] = useState<{ name: string; text: string }[]>([]);
  const [selectedSize, setSelectedSize] = useState<number>(0);
  const [selectedWargear, setSelectedWargear] = useState<WargearSelection[]>([]);
  const [selectedEnhancement, setSelectedEnhancement] = useState<any | null>(null);
  const [editingUnitId, setEditingUnitId] = useState<string | null>(null);
  const [detachmentDetails, setDetachmentDetails] = useState<DetachmentDetails | null>(null);
  const [keywordPopup, setKeywordPopup] = useState<{ name: string; text: string } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const leaders = roster.filter(unit =>
      unit.keywords.some(keyword => keyword.toUpperCase() === 'CHARACTER') &&
      !unit.keywords.some(keyword => ['VEHICLE', 'MONSTER'].includes(keyword.toUpperCase()))
    );
    if (leaders.length === 0) {
      setLegalBodyguardIds({});
      setLeaderAttachmentErrors({});
      return;
    }

    let active = true;
    Promise.all(leaders.map(async leader => {
      try {
        const response = await fetch(
          `http://127.0.0.1:8000/api/legal-bodyguards/${encodeURIComponent(leader.id)}`
        );
        if (!response.ok) {
          throw new Error(`Legal bodyguard lookup failed with status ${response.status}`);
        }
        const bodyguards: unknown = await response.json();
        if (!Array.isArray(bodyguards) || !bodyguards.every(id => typeof id === 'string')) {
          throw new Error('Legal bodyguard lookup returned an invalid response.');
        }
        return { instanceId: leader.instanceId, bodyguards, error: null };
      } catch (error) {
        console.error(`Failed to load legal bodyguards for ${leader.name}`, error);
        return {
          instanceId: leader.instanceId,
          bodyguards: [],
          error: 'Could not load legal bodyguards. Check the backend and try again.',
        };
      }
    })).then(results => {
      if (!active) return;
      setLegalBodyguardIds(Object.fromEntries(
        results.map(result => [result.instanceId, result.bodyguards])
      ));
      setLeaderAttachmentErrors(Object.fromEntries(
        results
          .filter(result => result.error)
          .map(result => [result.instanceId, result.error as string])
      ));
    });

    return () => {
      active = false;
    };
  }, [roster]);

  // 1. Fetch Factions
  useEffect(() => {
    fetch('http://127.0.0.1:8000/api/factions')
      .then(res => res.json())
      .then(data => {
        setFactions(data);
      });
  }, []);

  // 2. Fetch Detachments when Faction changes
  useEffect(() => {
    if (!selectedFaction) return;
    const [factionId, subfaction] = selectedFaction.split("|", 2);
    const params = new URLSearchParams({ faction_id: factionId });
    if (subfaction) params.set('subfaction', subfaction);
    fetch(`http://127.0.0.1:8000/api/detachments?${params.toString()}`)
      .then(res => res.json())
      .then(data => {
        setDetachments(data);
        if (data.length > 0) {
          setSelectedDetachment(current =>
            data.some((detachment: Detachment) => detachment.id === current)
              ? current
              : data[0].id
          );
        } else {
          setSelectedDetachment("");
        }
      });
  }, [selectedFaction]);

  // 3. Fetch Units for Search
  useEffect(() => {
    if (!selectedFaction) {
      setGroupedUnits({});
      setSearchError(null);
      return;
    }

    let active = true;
    setSearchError(null);
    fetch(`http://127.0.0.1:8000/api/search?q=${search}&faction_id=${encodeURIComponent(selectedFaction)}`)
      .then(res => {
        if (!res.ok) throw new Error(`Unit search failed with status ${res.status}`);
        return res.json() as Promise<GroupedUnits>;
      })
      .then(data => {
        if (active) setGroupedUnits(data);
      })
      .catch(error => {
        console.error('Failed to search units', error);
        if (active) {
          setGroupedUnits({});
          setSearchError('Could not load units. Check that the backend is running and try again.');
        }
      });

    return () => {
      active = false;
    };
  }, [search, selectedFaction]);

  // 4. Validate Roster & Get Advice
  useEffect(() => {
    if (roster.length === 0) {
      setViolations([]);
      setValidationError(null);
      setSuggestions([]);
      return;
    }

    let active = true;
    setValidationError(null);
    const payload = {
      faction_id: selectedFaction.split("|")[0],
      detachment_id: selectedDetachment || "none",
      points_limit: pointsLimit, // Use dynamic points limit
      entries: roster.map(r => ({
        instance_id: r.instanceId,
        datasheet_id: r.id,
        size: r.size,
        is_warlord: r.is_warlord,
        enhancement: r.enhancement ? r.enhancement.name : null,
        attached_to: r.attached_to ?? null
      }))
    };

    // Validate
    fetch('http://127.0.0.1:8000/api/validate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    .then(res => {
      if (!res.ok) throw new Error(`Roster validation failed with status ${res.status}`);
      return res.json() as Promise<{ violations: Violation[] }>;
    })
    .then(data => {
      if (active) setViolations(data.violations);
    })
    .catch(error => {
      console.error('Failed to validate roster', error);
      if (active) {
        setValidationError('Roster validation failed. Please check the backend and try again.');
      }
    });

    // Get AI Advice (We only ask for advice if the list is valid)
    // Note: For now we are hardcoding "gunline" until we add a playstyle selector
    fetch(`http://127.0.0.1:8000/api/advise?archetype=gunline`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    .then(res => res.json())
    .then(data => setSuggestions(data.suggestions || []))
    .catch(() => setSuggestions([]));

    return () => {
      active = false;
    };
  }, [roster, selectedFaction, selectedDetachment, pointsLimit]);

  useEffect(() => {
    try {
      localStorage.setItem('40k_roster_data', JSON.stringify({
        roster, selectedFaction, selectedDetachment, pointsLimit
      }));
    } catch (error) {
      console.error('Failed to save roster data', error);
    }
  }, [roster, selectedFaction, selectedDetachment, pointsLimit]);

  const openUnitModal = (unitId: string, instanceId: string | null = null) => {
    setUnitDetailsError(null);
    setSelectedUnitDetails(null);
    setCanLeadUnits([]);
    fetch(`http://127.0.0.1:8000/api/units/${encodeURIComponent(unitId)}?detachment_id=${encodeURIComponent(selectedDetachment)}`)
      .then(async res => {
        if (!res.ok) {
          const errorBody = await res.json().catch(() => null);
          throw new Error(errorBody?.detail || `Unit lookup failed with status ${res.status}.`);
        }
        const data: unknown = await res.json();
        if (!isRecord(data) || typeof data.id !== 'string' || typeof data.name !== 'string' || !Array.isArray(data.keywords)) {
          throw new Error('The unit details response is invalid.');
        }
        return data as UnitDetails;
      })
      .then(data => {
        setSelectedUnitDetails(data);
        setEditingUnitId(instanceId);

        if (data.keywords.some(
          keyword => typeof keyword === 'string' && keyword.toUpperCase() === 'CHARACTER'
        )) {
          fetch(`http://127.0.0.1:8000/api/legal-bodyguards/${encodeURIComponent(unitId)}`)
            .then(async response => {
              if (!response.ok) {
                throw new Error(`Legal bodyguard lookup failed with status ${response.status}`);
              }
              const bodyguardIds: unknown = await response.json();
              if (!Array.isArray(bodyguardIds) || !bodyguardIds.every(id => typeof id === 'string')) {
                throw new Error('Legal bodyguard lookup returned an invalid response.');
              }
              return Promise.all(bodyguardIds.map(async id => {
                const bodyguardResponse = await fetch(
                  `http://127.0.0.1:8000/api/units/${encodeURIComponent(id)}`
                );
                if (!bodyguardResponse.ok) {
                  throw new Error(`Bodyguard unit lookup failed with status ${bodyguardResponse.status}`);
                }
                const bodyguard: unknown = await bodyguardResponse.json();
                if (!isRecord(bodyguard) || typeof bodyguard.name !== 'string') {
                  throw new Error('Bodyguard unit lookup returned an invalid response.');
                }
                return bodyguard.name;
              }));
            })
            .then(setCanLeadUnits)
            .catch(error => {
              console.error('Failed to load legal attachment options', error);
              setCanLeadUnits([]);
            });
        } else {
          setCanLeadUnits([]);
        }

        setUnitRulesText([]);
        fetch(`http://127.0.0.1:8000/api/codex/unit/${encodeURIComponent(data.name)}`)
          .then(res => res.json())
          .then(textData => {
            if (textData.abilities && Array.isArray(textData.abilities)) {
              setUnitRulesText(textData.abilities);
            } else {
              setUnitRulesText([]);
            }
          })
          .catch(() => console.error("Failed to fetch abilities"));

        if (instanceId) {
          const existingUnit = roster.find(r => r.instanceId === instanceId);
          if (existingUnit) {
            setSelectedSize(existingUnit.size);
            setSelectedWargear(normalizeWargear(existingUnit.wargear));
            setSelectedEnhancement(existingUnit.enhancement || null);
          }
        } else {
          setSelectedWargear([]);
          setSelectedEnhancement(null);
          if (data.points_options && data.points_options.length > 0) {
            setSelectedSize(data.points_options[0].models);
          }
        }
      })
      .catch(error => {
        console.error('Failed to load unit details', error);
        setSelectedUnitDetails(null);
        setUnitDetailsError(error instanceof Error ? error.message : 'Could not load unit details.');
      });
  };

  const openDetachmentDetails = () => {
    fetch(`http://127.0.0.1:8000/api/detachments/${selectedDetachment}`)
      .then(async res => {
        if (!res.ok) throw new Error(`Request failed with status ${res.status}`);
        const data: DetachmentDetails = await res.json();
        if (data.error) throw new Error(data.error);
        setDetachmentDetails(data);
      })
      .catch(error => {
        console.error('Failed to load detachment details', error);
        setDetachmentDetails({
          name: 'Detachment details unavailable',
          error: error instanceof Error ? error.message : 'Could not load detachment details.'
        });
      });
  };

  const selectWargearChoice = (
    choices: string[],
    replaces: string[],
    choiceName: string,
    quantity: number,
  ) => {
    setSelectedWargear(prev => {
      const withoutOption = prev.filter(w =>
        !choices.includes(w.name) &&
        !(
          replaces.length > 0 &&
          w.replaced.length === replaces.length &&
          w.replaced.every((weapon, index) => weapon === replaces[index])
        )
      );
      return choiceName && quantity > 0
        ? [...withoutOption, { name: choiceName, replaced: replaces, quantity }]
        : withoutOption;
    });
  };

  const setWargearQuantity = (choiceName: string, quantity: number) => {
    setSelectedWargear(prev =>
      prev.map(w => w.name === choiceName ? { ...w, quantity } : w)
    );
  };

  const getSelectedOptionChoice = (choices: string[]) =>
    selectedWargear.find(w => w.quantity > 0 && choices.includes(w.name));

  const exportRoster = () => {
    const dataStr = JSON.stringify({
      selectedFaction,
      selectedDetachment,
      pointsLimit,
      roster
    }, null, 2);

    const blob = new Blob([dataStr], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = "my_40k_roster.json";
    a.click();
    URL.revokeObjectURL(url);
  };

  const printRoster = () => {
    const printWindow = window.open('', '_blank');
    if (!printWindow) {
      window.alert('Please allow pop-ups to print your roster.');
      return;
    }

    const escapeHtml = (value: string) => value.replace(/[&<>"']/g, character => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;',
    })[character] || character);
    const [factionId, subfaction] = selectedFaction.split('|', 2);
    const factionName = factions.find(faction => faction.id === factionId)?.name || factionId;
    const factionLabel = subfaction ? `${factionName} - ${subfaction}` : factionName;
    const detachmentName = detachments.find(detachment => detachment.id === selectedDetachment)?.name
      || selectedDetachment
      || 'None';
    const unitRows = roster.map(unit => {
      const wargear = normalizeWargear(unit.wargear);
      const details = [
        `${unit.size} model${unit.size === 1 ? '' : 's'}`,
        ...wargear.map(item => `${item.quantity > 1 ? `${item.quantity}x ` : ''}${item.name}`),
        ...(unit.enhancement ? [`Enhancement: ${unit.enhancement.name}`] : []),
      ];
      return `<li>
        <div class="unit-heading"><strong>${escapeHtml(unit.name)}</strong><strong>${unit.points} pts</strong></div>
        <div>${details.map(detail => escapeHtml(detail)).join(' · ')}</div>
      </li>`;
    }).join('');

    printWindow.document.write(`<!doctype html>
      <html lang="en">
        <head>
          <meta charset="utf-8">
          <title>${escapeHtml(factionLabel)} Roster</title>
          <style>
            body { font-family: Arial, sans-serif; color: #000; background: #fff; margin: 2rem; }
            h1, p { margin: 0 0 0.75rem; }
            ul { list-style: none; padding: 0; }
            li { padding: 0.75rem 0; border-bottom: 1px solid #ccc; }
            .unit-heading { display: flex; justify-content: space-between; margin-bottom: 0.35rem; }
            @media print { body { margin: 1cm; } }
          </style>
        </head>
        <body>
          <h1>${escapeHtml(factionLabel)} Roster</h1>
          <p><strong>Detachment:</strong> ${escapeHtml(detachmentName)}</p>
          <p><strong>Total:</strong> ${totalPoints} pts</p>
          <ul>${unitRows}</ul>
        </body>
      </html>`);
    printWindow.document.close();
    printWindow.focus();
    printWindow.print();
  };

  const handleImport = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const content = e.target?.result;
        if (typeof content !== 'string') {
          throw new Error('The selected file could not be read as text.');
        }

        const data: unknown = JSON.parse(content);
        if (!isRecord(data) ||
          typeof data.selectedFaction !== 'string' ||
          typeof data.selectedDetachment !== 'string' ||
          typeof data.pointsLimit !== 'number' ||
          !Number.isFinite(data.pointsLimit) ||
          !Array.isArray(data.roster)) {
          throw new Error('Invalid roster file format.');
        }

        const importedRoster = data.roster.map((item: unknown) => {
          if (!isRecord(item)) {
            throw new Error('Invalid unit entry in roster file.');
          }

          const { id, name, instanceId, size, points } = item;
          if (
            typeof id !== 'string' ||
            typeof name !== 'string' ||
            typeof instanceId !== 'string' ||
            typeof size !== 'number' ||
            !Number.isFinite(size) ||
            typeof points !== 'number' ||
            !Number.isFinite(points)
          ) {
            throw new Error('Invalid unit entry in roster file.');
          }

          return {
            id,
            name,
            instanceId,
            size,
            points,
            is_warlord: item.is_warlord === true,
            wargear: normalizeWargear(item.wargear),
            keywords: Array.isArray(item.keywords)
              ? item.keywords.filter((keyword): keyword is string => typeof keyword === 'string')
              : [],
            enhancement: item.enhancement ?? null,
            attached_to: typeof item.attached_to === 'string' ? item.attached_to : null,
          };
        });

        setSelectedFaction(data.selectedFaction);
        setSelectedDetachment(data.selectedDetachment);
        setPointsLimit(data.pointsLimit);
        setRoster(importedRoster);
      } catch (error) {
        console.error('Failed to parse imported roster', error);
        alert(error instanceof Error && error.message === 'Invalid roster file format.'
          ? error.message
          : "Failed to read the file. Make sure it's a valid roster JSON file.");
      }
    };
    reader.onerror = () => {
      console.error('Failed to read imported roster file', reader.error);
      alert('Failed to read the selected roster file.');
    };
    reader.readAsText(file);

    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const saveUnit = () => {
    if (!selectedUnitDetails) return;
    const pointsTier = selectedUnitDetails.points_options.find(p => p.models === selectedSize);
    const baseCost = pointsTier ? pointsTier.cost : selectedUnitDetails.points_options[0].cost;
    const enhancementCost = selectedEnhancement ? selectedEnhancement.cost : 0;

    if (editingUnitId) {
      setRoster(roster.map(r => r.instanceId === editingUnitId ? {
        ...r,
        size: selectedSize,
        points: baseCost + enhancementCost,
        wargear: selectedWargear,
        enhancement: selectedEnhancement
      } : r));
    } else {
      const newItem: RosterItem = {
        id: selectedUnitDetails.id,
        name: selectedUnitDetails.name,
        points: baseCost + enhancementCost,
        size: selectedSize,
        is_warlord: false,
        wargear: selectedWargear,
        instanceId: crypto.randomUUID(),
        keywords: selectedUnitDetails.keywords,
        enhancement: selectedEnhancement
      };
      setRoster([...roster, newItem]);
    }

    setSelectedUnitDetails(null);
    setEditingUnitId(null);
  };

  const removeUnit = (index: number) => {
    const removedInstanceId = roster[index]?.instanceId;
    setRoster(roster
      .filter((_, rosterIndex) => rosterIndex !== index)
      .map(unit => unit.attached_to === removedInstanceId
        ? { ...unit, attached_to: null }
        : unit));
  };

  const setAttachedTo = (characterId: string, bodyguardId: string | null) => {
    setRoster(current => current.map(unit =>
      unit.instanceId === characterId ? { ...unit, attached_to: bodyguardId } : unit
    ));
  };

  const setWarlord = (instanceId: string) => {
    const newRoster = roster.map(r => ({
      ...r,
      is_warlord: r.instanceId === instanceId
    }));
    setRoster(newRoster);
  };

  const toggleGroup = (group: string) => {
    setOpenGroups(prev => ({ ...prev, [group]: !prev[group] }));
  };

  const showKeywordDefinition = (keyword: string) => {
    setKeywordPopup({ name: keyword, text: "Loading definition..." });
    fetch(`http://127.0.0.1:8000/api/keywords/${encodeURIComponent(keyword)}`)
      .then(res => {
        if (!res.ok) throw new Error(`Keyword lookup failed with status ${res.status}`);
        return res.json();
      })
      .then(data => setKeywordPopup({ name: data.keyword, text: data.definition }))
      .catch(() => setKeywordPopup({ name: keyword, text: "Failed to load definition." }));
  };

  const totalPoints = roster.reduce((sum, unit) => sum + unit.points, 0);
  const remainingPoints = Math.max(pointsLimit - totalPoints, 0);
  const rosterModelCount = roster.reduce((sum, unit) => sum + unit.size, 0);
  const rosterCharacterCount = roster.filter(unit =>
    unit.keywords.some(keyword => keyword.toUpperCase() === 'CHARACTER')
  ).length;
  const rosterBattlelineCount = roster.filter(unit =>
    unit.keywords.some(keyword => keyword.toUpperCase() === 'BATTLELINE')
  ).length;
  const rosterVehicleCount = roster.filter(unit =>
    unit.keywords.some(keyword => keyword.toUpperCase() === 'VEHICLE')
  ).length;
  const rosterProgress = pointsLimit > 0 ? Math.min((totalPoints / pointsLimit) * 100, 100) : 0;
  // Calculate the live loadout preview for the Datacard
  // 1. Find all weapons that are part of the options (the ones you can swap to)
  const allChoiceNames = selectedUnitDetails?.wargear_options
    ?.flatMap(opt => opt.choices.flatMap(choice => choice.split(' + '))) || [];

  // 2. The base weapons are those on the datasheet that are not optional choices
  const baseWeapons = selectedUnitDetails?.weapons
    .filter(w => !allChoiceNames.includes(w.name))
    .map(w => w.name) || [];

  // 3. Find out which base weapons were replaced
  const activeWargear = selectedWargear.filter(w => w.quantity > 0);
  const replacedWeapons = activeWargear.flatMap(w => w.replaced || []);

  // 4. Remove the replaced weapons from the base list
  const remainingBaseWeapons = baseWeapons.filter(w => !replacedWeapons.includes(w));

  // 5. Add the new weapons the user selected
  const newSelectedWeapons = activeWargear.map(w =>
    w.quantity > 1 ? `${w.quantity}x ${w.name}` : w.name
  );

  // 6. Combine them
  const currentLoadout = Array.from(new Set([...remainingBaseWeapons, ...newSelectedWeapons]));
  const takenEnhancementIds = roster
    .filter(r => r.instanceId !== editingUnitId)
    .map(r => r.enhancement?.id)
    .filter(id => id !== undefined);
  const isOverLimit = violations.some(v => v.code === "POINTS_EXCEEDED");

  const handleFactionClick = async (f: Faction) => {
    setTempFaction(f);
    setFactionMeta(null);
    setPreviewDetachments([]);
    setTempSubfaction(null);
    setSelectionError(null);
    setIsLoadingFaction(true);
    setSelectionStep('faction');

    try {
      const [metadataResponse, detachmentsResponse] = await Promise.all([
        fetch(`http://127.0.0.1:8000/api/faction-metadata/${encodeURIComponent(f.id)}`),
        fetch(`http://127.0.0.1:8000/api/detachments?faction_id=${encodeURIComponent(f.id)}`),
      ]);
      if (!metadataResponse.ok) {
        throw new Error(`Faction metadata request failed (${metadataResponse.status})`);
      }
      if (!detachmentsResponse.ok) {
        throw new Error(`Detachment request failed (${detachmentsResponse.status})`);
      }
      const [metadata, detachmentsData] = await Promise.all([
        metadataResponse.json(),
        detachmentsResponse.json(),
      ]);
      setFactionMeta(metadata);
      setPreviewDetachments(detachmentsData);
    } catch (error) {
      console.error('Failed to load faction details', error);
      setSelectionError('Could not load faction details. Please try again.');
    } finally {
      setIsLoadingFaction(false);
    }
  };

  const handleConfirmFaction = () => {
    const metadataSubfactions = factionMeta?.subfactions ?? {};
    const subfactions = Object.keys(metadataSubfactions).length > 0
      ? metadataSubfactions
      : Object.fromEntries((tempFaction?.subfactions ?? []).map((name: string) => [name, {}]));

    if (Object.keys(subfactions).length > 0) {
      setFactionMeta((current: any) => ({ ...current, subfactions }));
      setSelectionStep('subfaction');
    } else if (tempFaction) {
      setSelectedFaction(tempFaction.id);
      setSearch("");
      setSelectionStep('grid');
    }
  };

  const handleSubfactionClick = (subName: string, subData: any) => {
    setTempSubfaction({ name: subName, ...subData });
    setSelectionStep('subfaction-details');
  };

  const handleConfirmSubfaction = () => {
    if (!tempFaction || !tempSubfaction) return;
    setSelectedFaction(`${tempFaction.id}|${tempSubfaction.name}`);
    setSearch("");
    setSelectionStep('grid');
  };

  if (!selectedFaction) {
    const subfactions = Object.entries(factionMeta?.subfactions ?? {}) as [string, any][];

    return (
      <div className="faction-selection-screen" style={{ flex: 1 }}>
        <div className="faction-selection-content">
          {selectionStep === 'grid' && (
            <>
              <h1>Select Your Faction</h1>
              <p>Choose the army you want to command.</p>
              <div className="faction-grid">
                {factions.map(f => (
                  <button key={f.id} className="faction-card" onClick={() => handleFactionClick(f)}>
                    <h2>{f.name}</h2>
                    <span>{f.subfactions.length} Subfactions</span>
                  </button>
                ))}
              </div>
            </>
          )}

          {selectionStep === 'faction' && tempFaction && (
            <section>
              <h1>{tempFaction.name}</h1>
              <p>{factionMeta?.lore || 'Faction lore is not available yet.'}</p>
              <p><strong>Playstyle:</strong> {factionMeta?.playstyle || 'Playstyle information is not available yet.'}</p>
              <h2 style={{ marginBottom: '1rem' }}>Available Detachments</h2>
              {isLoadingFaction ? <p>Loading faction details...</p> : (
                <div className="faction-grid">
                  {previewDetachments.map(detachment => (
                    <div className="faction-card" key={detachment.id}>
                      <h2>{detachment.name}</h2>
                    </div>
                  ))}
                </div>
              )}
              {selectionError && <p role="alert" style={{ color: '#ff7070' }}>{selectionError}</p>}
              <div style={{ display: 'flex', justifyContent: 'center', gap: '1rem', marginTop: '1rem' }}>
                <button className="info-btn" onClick={() => setSelectionStep('grid')}>Back</button>
                <button className="export-btn" onClick={handleConfirmFaction} disabled={isLoadingFaction || !factionMeta}>
                  Continue
                </button>
              </div>
            </section>
          )}

          {selectionStep === 'subfaction' && (
            <section>
              <h1>Choose a {tempFaction?.name} Subfaction</h1>
              <p>Select a subfaction to see its details.</p>
              <div className="faction-grid">
                {subfactions.map(([name, data]) => (
                  <button key={name} className="faction-card" onClick={() => handleSubfactionClick(name, data)}>
                    <h2>{name}</h2>
                    {data.playstyle && <span>{data.playstyle}</span>}
                  </button>
                ))}
              </div>
              <button className="info-btn" onClick={() => setSelectionStep('faction')}>Back</button>
            </section>
          )}

          {selectionStep === 'subfaction-details' && tempSubfaction && (
            <section>
              <h1>{tempSubfaction.name}</h1>
              <p>{tempSubfaction.lore || 'Subfaction lore is not available yet.'}</p>
              <p><strong>Playstyle:</strong> {tempSubfaction.playstyle || 'Playstyle information is not available yet.'}</p>
              <div style={{ display: 'flex', justifyContent: 'center', gap: '1rem', marginTop: '1rem' }}>
                <button className="info-btn" onClick={() => setSelectionStep('subfaction')}>Back</button>
                <button className="export-btn" onClick={handleConfirmSubfaction}>Choose Subfaction</button>
              </div>
            </section>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="app-container roster-screen">
      <header className="top-bar">
        <div className="header-left">
          <div className="roster-terminal-brand">
            <span className="roster-terminal-kicker">TACTICAL COGITATOR // ARRAY 01</span>
            <h1>40Ksim Roster Builder</h1>
          </div>

          {/* UPDATED HEADER CONTROLS */}
          <div className="header-controls">
            <div className="selected-faction-display" style={{ fontSize: '1.2rem', fontWeight: 'bold', color: '#fff', marginRight: '1rem', display: 'flex', alignItems: 'center' }}>
              {selectedFaction.includes('|') ? (
                <>
                  {factions.find(f => f.id === selectedFaction.split('|')[0])?.name || selectedFaction.split('|')[0]}
                  <span style={{ color: 'var(--border-gold)', margin: '0 0.5rem' }}>›</span>
                  {selectedFaction.split('|')[1]}
                </>
              ) : (
                factions.find(f => f.id === selectedFaction)?.name || selectedFaction
              )}
            </div>
            <button
              className="info-btn"
              style={{ marginLeft: '-0.5rem', borderColor: '#dc3545', color: '#dc3545' }}
              onClick={() => {
                if (roster.length > 0 && !window.confirm("Changing factions will clear your current roster. Are you sure?")) return;
                setRoster([]);
                setSelectedFaction("");
                setSelectionStep('grid');
              }}
            >
              Change
            </button>

            <div className="detachment-group">
              <select className="detachment-select" value={selectedDetachment} onChange={(e) => setSelectedDetachment(e.target.value)}>
                {detachments.length === 0 && <option value="">No Detachments</option>}
                {detachments.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
              </select>
              {selectedDetachment && (
                <button className="info-btn" onClick={openDetachmentDetails}>
                  ℹ️ Rules
                </button>
              )}
            </div>

            <select className="points-select" value={pointsLimit} onChange={(e) => setPointsLimit(Number(e.target.value))}>
              <option value={500}>500 pts</option>
              <option value={1000}>1000 pts</option>
              <option value={2000}>2000 pts</option>
              <option value={3000}>3000 pts</option>
            </select>
          </div>
        </div>

        <div className="header-right">
          <div className={`points-display ${isOverLimit ? 'points-error' : ''}`}>
            Total: <strong>{totalPoints}</strong> / {pointsLimit} pts
          </div>
          <input
            type="file"
            accept=".json"
            ref={fileInputRef}
            onChange={handleImport}
            style={{ display: 'none' }}
          />
          <button className="import-btn" onClick={() => fileInputRef.current?.click()}>
            Import List
          </button>
          <button className="export-btn" onClick={exportRoster} disabled={roster.length === 0}>
            Save List
          </button>
          <button className="export-btn" onClick={printRoster} disabled={roster.length === 0}>
            🖨️ Print List
          </button>
        </div>
      </header>

      <div className="main-content">
        <nav className="roster-rail" aria-label="Roster console">
          <span className="roster-rail-heading">TACTICAL CONSOLE</span>
          <a className="roster-rail-link active" href="#current-roster">
            <span aria-hidden="true">▤</span>
            <span>Muster Roster</span>
          </a>
          <a className="roster-rail-link" href="#datasheet-list">
            <span aria-hidden="true">⌕</span>
            <span>Holy Datasheets</span>
          </a>
          <Link className="roster-rail-link" to="/codex">
            <span aria-hidden="true">✣</span>
            <span>Stratagems &amp; Liturgies</span>
          </Link>
          <a className="roster-rail-link" href="#validation-diagnostics">
            <span aria-hidden="true">⚠</span>
            <span>Validation Diagnostics</span>
          </a>
          <a className="roster-rail-link" href="#points-overview">
            <span aria-hidden="true">◉</span>
            <span>Cogitator Telemetry</span>
          </a>
          <Link className="roster-rail-link" to="/">
            <span aria-hidden="true">⌂</span>
            <span>Main Terminal</span>
          </Link>
          <Link className="roster-rail-link" to="/game">
            <span aria-hidden="true">⚔</span>
            <span>Battle Simulator</span>
          </Link>
          <Link className="roster-rail-link" to="/profile">
            <span aria-hidden="true">◉</span>
            <span>Operative Profile</span>
          </Link>
          <div className="roster-rail-footer">
            <span>DOCTRINA DIRECTIVES</span>
            <span>COGITATOR ONLINE</span>
          </div>
        </nav>

        <aside className="left-pane">
          <div className="datasheet-browser-header" id="datasheet-list">
            <span>LEX TACTICA IMPERIALIS</span>
            <span>{Object.values(groupedUnits).reduce((count, units) => count + units.length, 0)} RECORDS</span>
          </div>
          <input type="text" placeholder="Search datasheets..." value={search} onChange={(e) => setSearch(e.target.value)} className="search-input" />
          <div className="unit-category-filters" aria-label="Filter datasheets">
            {[
              { id: 'all', label: 'ALL' },
              { id: 'character', label: 'CHARACTER' },
              { id: 'battleline', label: 'BATTLELINE' },
              { id: 'infantry', label: 'INFANTRY' },
              { id: 'vehicle', label: 'VEHICLE' },
            ].map(filter => (
              <button
                key={filter.id}
                type="button"
                className={`unit-category-filter${unitCategoryFilter === filter.id ? ' active' : ''}`}
                aria-pressed={unitCategoryFilter === filter.id}
                onClick={() => setUnitCategoryFilter(filter.id)}
              >
                {filter.label}
              </button>
            ))}
          </div>
          {searchError && <p role="alert">{searchError}</p>}
          <div className="search-results">
            {Object.entries(groupedUnits).map(([groupName, units]) => {
              if (!units || units.length === 0) return null;
              const normalizedGroup = groupName.toLowerCase();
              const matchesFilter = unitCategoryFilter === 'all' ||
                (unitCategoryFilter === 'character' && ['characters', 'epic heroes'].includes(normalizedGroup)) ||
                (unitCategoryFilter === 'battleline' && normalizedGroup === 'battleline') ||
                (unitCategoryFilter === 'infantry' && normalizedGroup === 'infantry') ||
                (unitCategoryFilter === 'vehicle' && normalizedGroup === 'vehicles');
              if (!matchesFilter) return null;
              return (
                <div key={groupName} className="unit-group">
                  <div className="group-header" onClick={() => toggleGroup(groupName)}>
                    <h3>{groupName} ({units.length})</h3>
                    <span>{openGroups[groupName] ? '▼' : '▶'}</span>
                  </div>
                  {openGroups[groupName] && (
                    <div className="group-items">
                      {units.map(unit => (
                        <div key={unit.id} className="unit-card" onClick={() => openUnitModal(unit.id)}>
                          <span>{unit.name}</span>
                          <span>{unit.points} pts</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </aside>

        <main className="right-pane" id="current-roster">
          <section className="roster-command-overview" id="points-overview">
            <div className="roster-overview-heading">
              <div>
                <span className="roster-overview-kicker">IMPERIAL ORDER OF BATTLE // STRIKE FORCE</span>
                <h2>Active Muster Roster</h2>
                <span className="roster-overview-subtitle">
                  {selectedFaction.includes('|') ? selectedFaction.split('|')[1] : factions.find(f => f.id === selectedFaction)?.name}
                  {selectedDetachment && ` · ${detachments.find(detachment => detachment.id === selectedDetachment)?.name || 'Detachment'}`}
                </span>
              </div>
              {roster.length > 0 && (
                <div className={`validation-status ${validationError || violations.length > 0 ? 'invalid' : 'valid'}`}>
                  {validationError ? '⚠ VALIDATION UNAVAILABLE' : violations.length === 0 ? '✓ LEX VALIDATED' : `✕ ${violations.length} OMISSIONS`}
                </div>
              )}
            </div>

            <div className="roster-force-readout">
              <span>FORCE QUOTA</span>
              <strong>{totalPoints.toLocaleString()} <small>/ {pointsLimit.toLocaleString()} PTS</small></strong>
              <div
                className="roster-force-progress"
                role="progressbar"
                aria-label="Points limit used"
                aria-valuemin={0}
                aria-valuemax={pointsLimit}
                aria-valuenow={Math.min(totalPoints, pointsLimit)}
              >
                <span style={{ width: `${rosterProgress}%` }} />
              </div>
              <span>{remainingPoints.toLocaleString()} PTS SURPLUS</span>
            </div>

            <div className="roster-metrics-grid">
              <div className="roster-metric"><span>COMMAND</span><strong>{rosterCharacterCount} UNIT{rosterCharacterCount === 1 ? '' : 'S'}</strong></div>
              <div className="roster-metric"><span>BATTLELINE CORE</span><strong>{rosterBattlelineCount} UNIT{rosterBattlelineCount === 1 ? '' : 'S'}</strong></div>
              <div className="roster-metric"><span>ARMORED ASSETS</span><strong>{rosterVehicleCount} UNIT{rosterVehicleCount === 1 ? '' : 'S'}</strong></div>
              <div className="roster-metric"><span>FORCE STRENGTH</span><strong>{rosterModelCount} MODEL{rosterModelCount === 1 ? '' : 'S'}</strong></div>
            </div>
          </section>

          <div className="right-pane-header" id="validation-diagnostics">
            <h2>Current Roster</h2>
            <span className="roster-record-count">{roster.length} SELECTED RECORDS</span>
          </div>

          {validationError && <p role="alert">{validationError}</p>}
          {unitDetailsError && <p role="alert">{unitDetailsError}</p>}
          {violations.length > 0 && (
            <div className="violations-box">
              {violations.map((v, i) => (
                <div key={i} className="violation-item">
                  <strong>{v.code}:</strong> {v.message}
                </div>
              ))}
            </div>
          )}

          {roster.length === 0 ? <p className="empty-text">Click a unit to view its datasheet.</p> : (
            <ul className="roster-list">
              {roster.map((unit, index) => (
                <li key={unit.instanceId} className={`roster-item ${unit.is_warlord ? 'warlord' : ''}`}>
                  <div className="item-info clickable" onClick={() => openUnitModal(unit.id, unit.instanceId)}>
                    <div style={{ display: 'flex', flexDirection: 'column', width: '100%' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div>
                          <span className="roster-unit-type">
                            {unit.is_warlord
                              ? 'SUPREME WARLORD // HIGH COMMAND'
                              : unit.keywords.some(keyword => keyword.toUpperCase() === 'CHARACTER')
                                ? 'CHARACTER // OFFICER'
                                : unit.keywords.some(keyword => keyword.toUpperCase() === 'BATTLELINE')
                                  ? 'BATTLELINE COHORT'
                                  : unit.keywords.some(keyword => keyword.toUpperCase() === 'VEHICLE')
                                    ? 'ARMORED ASSET'
                                      : unit.keywords.some(keyword => keyword.toUpperCase() === 'MONSTER')
                                        ? 'MONSTROUS ASSET'
                                        : unit.keywords.some(keyword => keyword.toUpperCase() === 'MOUNTED')
                                          ? 'MOUNTED AUXILIA'
                                          : unit.keywords.some(keyword => keyword.toUpperCase() === 'AIRCRAFT')
                                            ? 'AERIAL ASSET'
                                            : 'FIELD FORMATION'}
                          </span>
                          <span className="roster-unit-name">{unit.name}</span>
                          <span className="item-size">({unit.size} models)</span>
                          {unit.is_warlord && <span className="warlord-badge" style={{ marginLeft: '0.5rem' }}>WARLORD</span>}
                        </div>
                        <div className="item-actions">
                          <span className="item-pts">{unit.points} PTS</span>
                          {unit.keywords && unit.keywords.some(k => k.toUpperCase() === 'CHARACTER') && (
                            <button className="warlord-btn" onClick={(event) => { event.stopPropagation(); setWarlord(unit.instanceId); }}>👑</button>
                          )}
                          <button className="remove-btn" onClick={(event) => { event.stopPropagation(); removeUnit(index); }}>X</button>
                        </div>
                      </div>
                      {unit.keywords?.some(keyword => keyword.toUpperCase() === 'CHARACTER') &&
                        !unit.keywords.some(keyword => ['VEHICLE', 'MONSTER'].includes(keyword.toUpperCase())) && (
                          <label
                            style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '0.5rem', fontSize: '0.85rem' }}
                            onClick={event => event.stopPropagation()}
                          >
                            <span>Attach to:</span>
                            <select
                              aria-label={`Attach ${unit.name} to a unit`}
                              value={unit.attached_to ?? ''}
                              onChange={event => setAttachedTo(unit.instanceId, event.target.value || null)}
                            >
                              <option value="">Select Unit</option>
                              {roster
                                .filter(candidate =>
                                  legalBodyguardIds[unit.instanceId]?.includes(candidate.id)
                                )
                                .map(candidate => (
                                  <option key={candidate.instanceId} value={candidate.instanceId}>
                                    {candidate.name}
                                  </option>
                                ))}
                            </select>
                          </label>
                        )}
                      {leaderAttachmentErrors[unit.instanceId] && (
                        <p role="alert" style={{ margin: '0.35rem 0 0', color: '#ff8585', fontSize: '0.8rem' }}>
                          {leaderAttachmentErrors[unit.instanceId]}
                        </p>
                      )}
                      {roster
                        .filter(character =>
                          character.attached_to === unit.instanceId &&
                          character.keywords?.some(keyword => keyword.toUpperCase() === 'CHARACTER')
                        )
                        .map(character => (
                          <div key={character.instanceId} className="roster-led-indicator">
                            🛡️ Led by {character.name}
                          </div>
                        ))}
                      {/* Bottom Row: Custom Wargear Loadout */}
                      {unit.wargear && unit.wargear.length > 0 && (
                        <div style={{ marginTop: '0.5rem', paddingLeft: '0.5rem', borderLeft: '2px solid #444' }}>
                          {normalizeWargear(unit.wargear).map((w, wIdx) => (
                            <div key={wIdx} style={{ fontSize: '0.8rem', color: '#aaa', marginTop: '0.2rem' }}>
                              <span className="roster-wargear-marker">+</span>{' '}
                              <span className="roster-wargear-name">
                                {w.quantity > 1 ? `${w.quantity}x ` : ''}{w.name}
                              </span>
                              {w.replaced && w.replaced.length > 0 && (
                                <span style={{ color: '#666' }}> (replaces {w.replaced.join(', ')})</span>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    {unit.enhancement && (
                      <div style={{ marginTop: '0.5rem', fontSize: '0.8rem', color: 'var(--border-gold)' }}>
                        ✨ {unit.enhancement.name}
                      </div>
                    )}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </main>

        {/* AI ADVISOR PANEL */}
        {suggestions.length > 0 && (
          <aside className="advisor-pane">
            <h2>🤖 AI Advisor</h2>
            <p className="advisor-sub">Based on your Gunline playstyle, here is what you are missing:</p>
            {suggestions.map((s, i) => (
              <div key={i} className="suggestion-card">
                <div className="suggestion-header">
                  <strong>{s.suggested_unit_name}</strong>
                  <span>{s.points} pts</span>
                </div>
                <p className="suggestion-reason">{s.reason}</p>
                <button className="advisor-add-btn" onClick={() => openUnitModal(s.suggested_unit_id)}>
                  + View Datacard
                </button>
              </div>
            ))}
          </aside>
        )}
      </div>

      {/* DATACARD MODAL (Same as before, omitted for brevity but keep it in your file) */}
      {selectedUnitDetails && (
        // ... Keep your existing Datacard modal code here ...
        <div className="modal-overlay">
          <div className="datacard">
            <div className="dc-header">
              <div className="dc-title">
                <h1>{selectedUnitDetails.name}</h1>
                <div className="dc-keywords">{selectedUnitDetails.keywords.slice(0, 4).join(' · ')}</div>
              </div>
              <button className="dc-close" onClick={() => setSelectedUnitDetails(null)}>×</button>
            </div>

            <div className="dc-stats-row">
              <div className="dc-stat-box"><span>M</span><strong>{selectedUnitDetails.stats.M}"</strong></div>
              <div className="dc-stat-box"><span>T</span><strong>{selectedUnitDetails.stats.T}</strong></div>
              <div className="dc-stat-box"><span>SV</span><strong>{selectedUnitDetails.stats.SV}+</strong></div>
              <div className="dc-stat-box"><span>W</span><strong>{selectedUnitDetails.stats.W}</strong></div>
              <div className="dc-stat-box"><span>LD</span><strong>{selectedUnitDetails.stats.LD}+</strong></div>
              <div className="dc-stat-box"><span>OC</span><strong>{selectedUnitDetails.stats.OC}</strong></div>
            </div>

            <div className="dc-scroll-area">
              {/* RANGED WEAPONS */}
              <div className="dc-weapon-section">
                <h3>RANGED WEAPONS</h3>
                <table className="dc-weapon-table">
                  <thead>
                    <tr><th>WEAPON</th><th>RANGE</th><th>A</th><th>BS</th><th>S</th><th>AP</th><th>D</th><th>KEYWORDS</th></tr>
                  </thead>
                  <tbody>
                    {selectedUnitDetails.weapons.filter(w => !w.is_melee).map((w, i) => (
                      <tr key={i}>
                        <td className="w-name">{w.name}</td>
                        <td>{w.stats?.Range || '-'}</td>
                        <td>{w.stats?.A || '-'}</td>
                        <td>{w.stats?.BS || '-'}</td>
                        <td>{w.stats?.S || '-'}</td>
                        <td>{w.stats?.AP || '-'}</td>
                        <td>{w.stats?.D || '-'}</td>
                        <td style={{ fontSize: '0.75rem', color: 'var(--accent-green-bright)', maxWidth: '150px' }}>
                          {w.keywords && w.keywords.length > 0 ? (
                            w.keywords.map((kw, idx) => (
                              <span
                                key={idx}
                                onClick={() => showKeywordDefinition(kw)}
                                style={{
                                  cursor: 'pointer',
                                  textDecoration: 'underline',
                                  marginRight: '4px',
                                  display: 'inline-block'
                                }}
                                title="Click to read rule"
                              >
                                {kw}
                              </span>
                            ))
                          ) : '-'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* MELEE WEAPONS */}
              {selectedUnitDetails.weapons.some(w => w.is_melee) && (
                <div className="dc-weapon-section">
                  <h3>MELEE WEAPONS</h3>
                  <table className="dc-weapon-table">
                    <thead>
                      <tr><th>WEAPON</th><th>RANGE</th><th>A</th><th>WS</th><th>S</th><th>AP</th><th>D</th><th>KEYWORDS</th></tr>
                    </thead>
                    <tbody>
                      {selectedUnitDetails.weapons.filter(w => w.is_melee).map((w, i) => (
                        <tr key={i}>
                          <td className="w-name">{w.name}</td>
                          <td>Melee</td>
                          <td>{w.stats?.A || '-'}</td>
                          <td>{w.stats?.BS || '-'}</td>
                          <td>{w.stats?.S || '-'}</td>
                          <td>{w.stats?.AP || '-'}</td>
                          <td>{w.stats?.D || '-'}</td>
                          <td style={{ fontSize: '0.75rem', color: 'var(--accent-green-bright)', maxWidth: '150px' }}>
                            {w.keywords && w.keywords.length > 0 ? (
                              w.keywords.map((kw, idx) => (
                                <span
                                  key={idx}
                                  onClick={() => showKeywordDefinition(kw)}
                                  style={{
                                    cursor: 'pointer',
                                    textDecoration: 'underline',
                                    marginRight: '4px',
                                    display: 'inline-block'
                                  }}
                                  title="Click to read rule"
                                >
                                  {kw}
                                </span>
                              ))
                            ) : '-'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              <div className="dc-weapon-section">
                <h3>CURRENT LOADOUT</h3>
                <p>{currentLoadout.length > 0 ? currentLoadout.join(', ') : '-'}</p>
              </div>

              <div className="dc-abilities-section" style={{ marginTop: '1.5rem' }}>
                <h3>DATASHEET RULES &amp; ABILITIES</h3>

                {unitRulesText.length === 0 ? (
                  <p className="dc-empty">No abilities found or loading...</p>
                ) : (
                  <div className="dc-ability-grid">
                    {unitRulesText.map((ability, index) => (
                      <div key={index} className="dc-ability-card" style={{ borderLeftColor: 'var(--accent-green)', background: 'var(--surface-card)' }}>
                        <strong style={{ fontSize: '1rem', color: '#fff' }}>{ability.name}</strong>
                        <p style={{ whiteSpace: 'pre-wrap', lineHeight: '1.6', color: '#ccc', marginTop: '0.5rem', fontSize: '0.9rem' }}>
                          {ability.text}
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {canLeadUnits.length > 0 && (
                <div className="dc-abilities-section" style={{ marginTop: '1.5rem' }}>
                  <h3>CAN LEAD (ATTACHMENTS)</h3>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                    {canLeadUnits.map(unitName => (
                      <span
                        key={unitName}
                        style={{
                          background: '#333',
                          color: '#ddd',
                          padding: '0.25rem 0.6rem',
                          borderRadius: '4px',
                        }}
                      >
                        {unitName}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {selectedUnitDetails.wargear_options && selectedUnitDetails.wargear_options.length > 0 && (
                <div className="dc-abilities-section" style={{ marginTop: '1.5rem' }}>
                  <h3>WARGEAR OPTIONS</h3>
                  <div style={{ background: 'var(--surface-inset)', padding: '1rem', borderRadius: '0', marginBottom: '1rem', border: '1px solid var(--border-metal)' }}>
                    <strong style={{ color: '#fff', fontSize: '0.9rem', display: 'block', marginBottom: '0.5rem' }}>Current Loadout:</strong>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                      {currentLoadout.map((weapon, index) => (
                        <span key={index} style={{ background: 'var(--surface-raised)', color: 'var(--border-gold)', padding: '0.2rem 0.6rem', borderRadius: '0', fontSize: '0.8rem' }}>
                          {weapon}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="dc-ability-grid">
                    {selectedUnitDetails.wargear_options.map((opt, i) => (
                      <div key={i} className="dc-ability-card" style={{ borderLeftColor: 'var(--border-gold)' }}>
                        <p style={{ margin: 0, color: '#ddd', fontSize: '0.9rem' }}>
                          Replace <strong>{opt.replaces.join(', ')}</strong> with:
                        </p>
                        {(() => {
                          const selectedChoice = getSelectedOptionChoice(opt.choices);
                          return (
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginTop: '0.5rem' }}>
                              <select
                                aria-label={`Replacement for ${opt.replaces.join(', ')}`}
                                value={selectedChoice?.name ?? ''}
                                onChange={event => selectWargearChoice(
                                  opt.choices,
                                  opt.replaces,
                                  event.target.value,
                                  1,
                                )}
                                style={{ flex: 1 }}
                              >
                                <option value="">Select replacement</option>
                                {opt.choices.map(choice => (
                                  <option key={choice} value={choice}>{choice}</option>
                                ))}
                              </select>
                              <select
                                aria-label={`Replacement quantity for ${opt.replaces.join(', ')}`}
                                value={selectedChoice?.quantity ?? 1}
                                disabled={!selectedChoice}
                                onChange={event => selectedChoice && setWargearQuantity(
                                  selectedChoice.name,
                                  Number(event.target.value),
                                )}
                              >
                                {Array.from({ length: selectedSize }, (_, index) => index + 1).map(quantity => (
                                  <option key={quantity} value={quantity}>{quantity}</option>
                                ))}
                              </select>
                            </div>
                          );
                        })()}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div className="dc-footer" style={{ flexWrap: 'wrap', gap: '1rem' }}>
              <div className="dc-size-picker">
                <label>UNIT SIZE</label>
                <select
                  value={selectedSize}
                  onChange={event => {
                    const size = Number(event.target.value);
                    setSelectedSize(size);
                    setSelectedWargear(previous =>
                      previous.map(item => ({ ...item, quantity: Math.min(item.quantity, size) }))
                    );
                  }}
                >
                  {selectedUnitDetails.points_options
                    .filter((opt, index, options) => options.findIndex(option => option.models === opt.models) === index)
                    .map(opt => (
                    <option key={opt.models} value={opt.models}>
                      {opt.models} model{opt.models > 1 ? 's' : ''} — {opt.cost} pts
                    </option>
                  ))}
                </select>
              </div>

              {selectedUnitDetails.available_enhancements &&
               selectedUnitDetails.available_enhancements.length > 0 &&
               selectedUnitDetails.keywords.some(k => k.toUpperCase() === 'CHARACTER') &&
               !selectedUnitDetails.keywords.some(k => k.toUpperCase() === 'EPIC HERO') && (
                <>
                  <div className="dc-size-picker">
                    <label style={{ color: 'var(--border-gold)' }}>ENHANCEMENT</label>
                    <select
                      value={selectedEnhancement ? selectedEnhancement.id : ""}
                      onChange={(e) => {
                        const enh = selectedUnitDetails.available_enhancements.find(x => x.id === e.target.value);
                        setSelectedEnhancement(enh || null);
                      }}
                      style={{ borderColor: selectedEnhancement ? 'var(--border-gold)' : 'var(--border-metal)' }}
                    >
                      <option value="">None (0 pts)</option>
                      {selectedUnitDetails.available_enhancements
                        .filter(enh => !takenEnhancementIds.includes(enh.id))
                        .map(enh => (
                          <option key={enh.id} value={enh.id}>{enh.name} (+{enh.cost} pts)</option>
                        ))}
                    </select>
                  </div>
                  {selectedEnhancement && (
                    <div style={{ width: '100%', background: 'var(--surface-card)', padding: '1rem', borderRadius: '0', borderLeft: '3px solid var(--border-gold)', marginTop: '1rem' }}>
                        <RulesText
                          type="enhancement"
                          name={selectedEnhancement.name}
                          faction={selectedFaction}
                          detachment={selectedDetachment}
                        />
                    </div>
                  )}
                </>
              )}

              <div className="dc-actions" style={{ marginLeft: 'auto' }}>
                <button className="dc-cancel" onClick={() => setSelectedUnitDetails(null)}>Cancel</button>
                <button className="dc-add" onClick={saveUnit}>
                  {editingUnitId ? 'Save Changes' : 'Add to Roster'} ({(selectedUnitDetails.points_options.find(p => p.models === selectedSize)?.cost || 0) + (selectedEnhancement ? selectedEnhancement.cost : 0)} pts)
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {detachmentDetails && (
        <div className="modal-overlay">
          <div className="datacard" style={{ maxWidth: '600px' }}>
            <div className="dc-header">
              <div className="dc-title">
                <h1>{detachmentDetails.name}</h1>
                <div className="dc-keywords">DETACHMENT RULES</div>
              </div>
              <button className="dc-close" onClick={() => setDetachmentDetails(null)}>×</button>
            </div>

            <div className="dc-scroll-area">
              {detachmentDetails.error ? (
                <p className="dc-empty">{detachmentDetails.error}</p>
              ) : (
                <>
                  <div className="dc-abilities-section">
                    <h3>DETACHMENT RULES</h3>
                    {detachmentDetails.rules?.map((r, i) => (
                      <div key={i} className="dc-ability-card" style={{ borderLeftColor: 'var(--accent-green)' }}>
                        <strong>{r.name}</strong>
                        <p style={{ whiteSpace: 'pre-wrap', lineHeight: '1.6', color: '#ccc', marginTop: '0.5rem' }}>
                          {cleanMarkdown(r.description ?? '')}
                        </p>
                      </div>
                    ))}
                  </div>

                  <div className="dc-abilities-section" style={{ marginTop: '1.5rem' }}>
                    <h3>ENHANCEMENTS</h3>
                    {detachmentDetails.enhancements?.map((e, i) => (
                      <div key={i} className="dc-ability-card" style={{ borderLeftColor: 'var(--border-gold)' }}>
                        <strong>{e.name} ({e.cost} pts)</strong>
                        <p style={{ whiteSpace: 'pre-wrap', lineHeight: '1.6', color: '#ccc', marginTop: '0.5rem' }}>
                          {cleanMarkdown(e.description ?? '')}
                        </p>
                      </div>
                    ))}
                  </div>

                  <div className="dc-abilities-section" style={{ marginTop: '1.5rem' }}>
                    <h3>STRATAGEMS</h3>
                    {detachmentDetails.stratagems?.map((s, i) => (
                      <div key={i} className="dc-ability-card" style={{ borderLeftColor: '#007bff' }}>
                        <strong>{s.name} ({s.cp_cost} CP)</strong>
                        <p style={{ whiteSpace: 'pre-wrap', lineHeight: '1.6', color: '#ccc', marginTop: '0.5rem' }}>
                          {cleanMarkdown(s.description ?? '')}
                        </p>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}
      {keywordPopup && (
        <div className="modal-overlay" onClick={() => setKeywordPopup(null)}>
          <div
            className="datacard"
            style={{ maxWidth: '400px', padding: '2rem' }}
            onClick={event => event.stopPropagation()}
          >
            <h2 style={{ color: 'var(--border-gold)', marginBottom: '1rem' }}>{keywordPopup.name}</h2>
            <p style={{ lineHeight: '1.6', color: '#ddd' }}>{keywordPopup.text}</p>
            <button
              onClick={() => setKeywordPopup(null)}
              style={{ marginTop: '1.5rem', padding: '0.5rem 1rem', background: '#444', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer', width: '100%' }}
            >
              Close
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default RosterBuilder;