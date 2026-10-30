import { useEffect, useMemo, useState, type CSSProperties } from 'react';
import '../App.css';

type Faction = { id: string; name: string };
type Unit = { id: string; name: string; points: number };
type Detachment = { id: string; name: string };
type UnitAbility = { name: string; text: string };
type UnitRules = { name: string; abilities: UnitAbility[] };
type DetachmentRule = { name: string; description: string };
type Enhancement = {
  name: string;
  cost: number | string;
  description: string;
  description_available?: boolean;
  upgrade?: boolean;
  max_targets?: number;
  keyword_restrictions?: string[];
};
type Stratagem = { name: string; cp_cost: number | string; description: string };
type DetachmentRules = {
  id: string;
  name: string;
  rules: DetachmentRule[];
  enhancements: Enhancement[];
  stratagems: Stratagem[];
  warnings?: string[];
  error?: string;
};
type Tab = 'units' | 'detachments' | 'stratagems' | 'enhancements';

const API_URL = 'http://127.0.0.1:8000';

const cleanMarkdown = (text: string | undefined | null) => {
  if (!text || typeof text !== 'string') return '';
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

const enhancementMeta = (item: Enhancement): string => {
  const parts: string[] = [];
  if (item.upgrade) {
    parts.push(`Upgrade: up to ${item.max_targets ?? 3} non-Character units, one enhancement slot`);
  }
  if (item.keyword_restrictions && item.keyword_restrictions.length > 0) {
    parts.push(`Requires: ${item.keyword_restrictions.join(' + ')}`);
  }
  return parts.join(' · ');
};

const enhancementCard = (item: Enhancement): RuleItem => ({
  name: `${item.name} · ${item.cost} pts`,
  description: item.description,
  meta: enhancementMeta(item),
  unavailable: item.description_available === false,
});

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export default function Codex() {
  const [factions, setFactions] = useState<Faction[]>([]);
  const [selectedFaction, setSelectedFaction] = useState<Faction | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>('units');
  const [units, setUnits] = useState<Unit[]>([]);
  const [detachments, setDetachments] = useState<Detachment[]>([]);
  const [expandedUnitId, setExpandedUnitId] = useState<string | null>(null);
  const [unitRules, setUnitRules] = useState<Record<string, UnitRules>>({});
  const [selectedDetachmentId, setSelectedDetachmentId] = useState<string | null>(null);
  const [detachmentRules, setDetachmentRules] = useState<Record<string, DetachmentRules>>({});
  const [loadingFactionList, setLoadingFactionList] = useState(true);
  const [loadingFactionContent, setLoadingFactionContent] = useState(false);
  const [loadingUnitId, setLoadingUnitId] = useState<string | null>(null);
  const [loadingDetachmentId, setLoadingDetachmentId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    fetchJson<Faction[]>(`${API_URL}/api/factions`)
      .then(data => {
        if (active) setFactions(data);
      })
      .catch(fetchError => {
        console.error('Failed to load factions', fetchError);
        if (active) setError('Could not load factions. Check that the backend is running.');
      })
      .finally(() => {
        if (active) setLoadingFactionList(false);
      });

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!selectedFaction) return;
    let active = true;
    setLoadingFactionContent(true);
    setError(null);
    setUnits([]);
    setDetachments([]);
    setExpandedUnitId(null);
    setUnitRules({});
    setSelectedDetachmentId(null);
    setDetachmentRules({});

    const [factionId, subfaction] = selectedFaction.id.split('|', 2);
    const detachmentParams = new URLSearchParams({ faction_id: factionId });
    if (subfaction) detachmentParams.set('subfaction', subfaction);

    Promise.all([
      fetchJson<Record<string, Unit[]>>(
        `${API_URL}/api/search?faction_id=${encodeURIComponent(selectedFaction.id)}&limit=1000`,
      ),
      fetchJson<Detachment[]>(
        `${API_URL}/api/detachments?${detachmentParams.toString()}`,
      ),
    ])
      .then(([groupedUnits, factionDetachments]) => {
        if (!active) return;
        const factionUnits = Object.values(groupedUnits).flat();
        setUnits(factionUnits);
        setDetachments(factionDetachments);
        setSelectedDetachmentId(factionDetachments[0]?.id ?? null);
      })
      .catch(fetchError => {
        console.error('Failed to load faction codex', fetchError);
        if (active) setError('Could not load this faction’s codex. Please try again.');
      })
      .finally(() => {
        if (active) setLoadingFactionContent(false);
      });

    return () => {
      active = false;
    };
  }, [selectedFaction]);

  const selectedDetachment = useMemo(
    () => detachments.find(detachment => detachment.id === selectedDetachmentId) ?? null,
    [detachments, selectedDetachmentId],
  );
  const selectedDetachmentRules = selectedDetachmentId
    ? detachmentRules[selectedDetachmentId]
    : undefined;

  const handleFactionSelect = (faction: Faction) => {
    setActiveTab('units');
    setSelectedFaction(faction);
  };

  const handleUnitSelect = async (unit: Unit) => {
    if (expandedUnitId === unit.id) {
      setExpandedUnitId(null);
      return;
    }

    setExpandedUnitId(unit.id);
    if (unitRules[unit.id]) return;

    setLoadingUnitId(unit.id);
    setError(null);
    try {
      const rules = await fetchJson<UnitRules>(
        `${API_URL}/api/codex/unit/${encodeURIComponent(unit.name)}`,
      );
      setUnitRules(current => ({ ...current, [unit.id]: rules }));
    } catch (fetchError) {
      console.error(`Failed to load rules for ${unit.name}`, fetchError);
      setError(`Could not load rules for ${unit.name}.`);
    } finally {
      setLoadingUnitId(null);
    }
  };

  const handleDetachmentSelect = async (detachment: Detachment) => {
    setSelectedDetachmentId(detachment.id);
    if (detachmentRules[detachment.id]) return;

    setLoadingDetachmentId(detachment.id);
    setError(null);
    try {
      const rules = await fetchJson<DetachmentRules>(
        `${API_URL}/api/detachments/${encodeURIComponent(detachment.id)}`,
      );
      setDetachmentRules(current => ({ ...current, [detachment.id]: rules }));
    } catch (fetchError) {
      console.error(`Failed to load ${detachment.name}`, fetchError);
      setError(`Could not load ${detachment.name}.`);
    } finally {
      setLoadingDetachmentId(null);
    }
  };

  if (!selectedFaction) {
    return (
      <div className="codex-bookshelf">
        <div className="codex-bookshelf-heading">
          <span className="codex-eyebrow">THE LIBRARY</span>
          <h1>Codex Bookshelf</h1>
          <p>Select a faction to explore its datasheets, detachments, stratagems, and enhancements.</p>
        </div>
        {loadingFactionList ? (
          <p className="codex-status">Loading factions...</p>
        ) : (
          <div className="codex-book-grid">
            {factions.map((faction, index) => (
              <button
                key={faction.id}
                className="codex-book"
                onClick={() => handleFactionSelect(faction)}
                style={{ '--book-index': index } as CSSProperties}
              >
                <span className="codex-book-mark">40K</span>
                <span className="codex-book-title">{faction.name}</span>
                <span className="codex-book-action">OPEN CODEX <span aria-hidden="true">→</span></span>
              </button>
            ))}
          </div>
        )}
        {error && <p className="codex-error" role="alert">{error}</p>}
      </div>
    );
  }

  const tabs: { id: Tab; label: string }[] = [
    { id: 'units', label: 'Datasheets' },
    { id: 'detachments', label: 'Detachments' },
    { id: 'stratagems', label: 'Stratagems' },
    { id: 'enhancements', label: 'Enhancements' },
  ];

  return (
    <main className="codex-reader">
      <button className="codex-back-button" onClick={() => setSelectedFaction(null)}>
        <span aria-hidden="true">←</span> Back to Codexes
      </button>

      <header className="codex-reader-heading">
        <span className="codex-eyebrow">FACTION ARCHIVE</span>
        <h1>{selectedFaction.name} <span>Codex</span></h1>
      </header>

      <nav className="codex-tabs" aria-label="Codex sections">
        {tabs.map(tab => (
          <button
            key={tab.id}
            className={`codex-tab ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
            aria-current={activeTab === tab.id ? 'page' : undefined}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      {error && <p className="codex-error" role="alert">{error}</p>}
      {loadingFactionContent ? (
        <p className="codex-status">Opening the codex...</p>
      ) : (
        <section className="codex-content">
          {activeTab === 'units' && (
            <div className="codex-list">
              <div className="codex-section-heading">
                <h2>Datasheets</h2>
                <span>{units.length} entries</span>
              </div>
              {units.length === 0 ? (
                <p className="codex-empty">No datasheets found for this faction.</p>
              ) : units.map(unit => {
                const isExpanded = expandedUnitId === unit.id;
                const rules = unitRules[unit.id];
                return (
                  <article className={`codex-entry ${isExpanded ? 'expanded' : ''}`} key={unit.id}>
                    <button className="codex-entry-toggle" onClick={() => void handleUnitSelect(unit)}>
                      <span>
                        <strong>{unit.name}</strong>
                        <small>{unit.points} pts</small>
                      </span>
                      <span className="codex-entry-chevron" aria-hidden="true">{isExpanded ? '−' : '+'}</span>
                    </button>
                    {isExpanded && (
                      <div className="codex-entry-details">
                        {loadingUnitId === unit.id ? <p className="codex-status">Reading datasheet...</p> : (
                          rules?.abilities.length ? rules.abilities.map((ability, index) => (
                            <div className="codex-rule" key={`${ability.name}-${index}`}>
                              <h3>{ability.name}</h3>
                              <p>{cleanMarkdown(ability.text)}</p>
                            </div>
                          )) : rules ? (
                            <p className="codex-empty">No ability text is available for this datasheet.</p>
                          ) : null
                        )}
                      </div>
                    )}
                  </article>
                );
              })}
            </div>
          )}

          {activeTab === 'detachments' && (
            <DetachmentSection
              detachments={detachments}
              selectedDetachment={selectedDetachment}
              selectedRules={selectedDetachmentRules}
              loadingId={loadingDetachmentId}
              onSelect={detachment => void handleDetachmentSelect(detachment)}
              content="all"
            />
          )}

          {activeTab === 'stratagems' && (
            <DetachmentSection
              detachments={detachments}
              selectedDetachment={selectedDetachment}
              selectedRules={selectedDetachmentRules}
              loadingId={loadingDetachmentId}
              onSelect={detachment => void handleDetachmentSelect(detachment)}
              content="stratagems"
            />
          )}

          {activeTab === 'enhancements' && (
            <DetachmentSection
              detachments={detachments}
              selectedDetachment={selectedDetachment}
              selectedRules={selectedDetachmentRules}
              loadingId={loadingDetachmentId}
              onSelect={detachment => void handleDetachmentSelect(detachment)}
              content="enhancements"
            />
          )}
        </section>
      )}
    </main>
  );
}

function DetachmentSection({
  detachments,
  selectedDetachment,
  selectedRules,
  loadingId,
  onSelect,
  content,
}: {
  detachments: Detachment[];
  selectedDetachment: Detachment | null;
  selectedRules: DetachmentRules | undefined;
  loadingId: string | null;
  onSelect: (detachment: Detachment) => void;
  content: 'all' | 'stratagems' | 'enhancements';
}) {
  const heading = content === 'stratagems'
    ? 'Stratagems'
    : content === 'enhancements' ? 'Enhancements' : 'Detachments';

  return (
    <div className="codex-reference-layout">
      <aside className="codex-reference-list">
        <div className="codex-section-heading">
          <h2>{heading}</h2>
          <span>{detachments.length} detachments</span>
        </div>
        {detachments.length === 0 ? (
          <p className="codex-empty">No detachments found for this faction.</p>
        ) : detachments.map(detachment => (
          <button
            className={`codex-reference-item ${selectedDetachment?.id === detachment.id ? 'active' : ''}`}
            key={detachment.id}
            onClick={() => onSelect(detachment)}
          >
            {detachment.name}
          </button>
        ))}
      </aside>

      <div className="codex-reference-details">
        {!selectedDetachment ? (
          <p className="codex-empty">Choose a detachment to read its rules.</p>
        ) : loadingId === selectedDetachment.id ? (
          <p className="codex-status">Loading {selectedDetachment.name}...</p>
        ) : selectedRules?.error ? (
          <p className="codex-error" role="alert">{selectedRules.error}</p>
        ) : !selectedRules ? (
          <div className="codex-detail-placeholder">
            <span className="codex-eyebrow">SELECTED VOLUME</span>
            <h2>{selectedDetachment.name}</h2>
            <p>Select this detachment to load its rules and references.</p>
          </div>
        ) : content === 'all' ? (
          <>
            <RuleWarnings warnings={selectedRules.warnings} />
            <div className="codex-detail-heading">
              <span className="codex-eyebrow">DETACHMENT</span>
              <h2>{selectedRules.name}</h2>
            </div>
            <RuleCards title="Detachment Rule" items={selectedRules.rules.map(rule => ({
              name: rule.name,
              description: rule.description,
            }))} />
            <RuleCards title="Enhancements" items={selectedRules.enhancements.map(enhancementCard)} />
            <RuleCards title="Stratagems" items={selectedRules.stratagems.map(item => ({
              name: `${item.name} · ${item.cp_cost} CP`,
              description: item.description,
            }))} />
          </>
        ) : content === 'stratagems' ? (
          <>
            <RuleWarnings warnings={selectedRules.warnings} />
            <RuleCards
            title={`${selectedRules.name} · Stratagems`}
            items={selectedRules.stratagems.map(item => ({
              name: `${item.name} · ${item.cp_cost} CP`,
              description: item.description,
            }))}
          />
          </>
        ) : (
          <>
          <RuleWarnings warnings={selectedRules.warnings} />
          <RuleCards
            title={`${selectedRules.name} · Enhancements`}
            items={selectedRules.enhancements.map(enhancementCard)}
          />
          </>
        )}
      </div>
    </div>
  );
}

type RuleItem = { name: string; description: string; meta?: string; unavailable?: boolean };

function RuleWarnings({ warnings }: { warnings?: string[] }) {
  if (!warnings || warnings.length === 0) return null;
  return (
    <details className="codex-status" style={{ marginBottom: '1rem' }}>
      <summary>Some rules text could not be loaded from the 40k MCP data</summary>
      <ul>
        {warnings.map(warning => <li key={warning}>{warning}</li>)}
      </ul>
    </details>
  );
}

function RuleCards({ title, items }: { title: string; items: RuleItem[] }) {
  return (
    <section className="codex-rule-section">
      <h3>{title}</h3>
      {items.length === 0 ? (
        <p className="codex-empty">No entries are available.</p>
      ) : items.map((item, index) => (
        <article className="codex-rule" key={`${item.name}-${index}`}>
          <h4>{item.name}</h4>
          {item.meta && <p style={{ opacity: 0.75, fontSize: '0.85rem', margin: '0 0 0.4rem' }}>{item.meta}</p>}
          <p>
            {cleanMarkdown(item.description)
              || (item.unavailable
                ? 'Rules text is not available in the 40k MCP data for this edition.'
                : 'Rule text is not available.')}
          </p>
        </article>
      ))}
    </section>
  );
}
