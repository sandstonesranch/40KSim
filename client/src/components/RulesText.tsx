import { useEffect, useState } from 'react';

type RuleType = 'detachment' | 'stratagem' | 'enhancement' | 'ability';

type RulesTextProps = {
  type: RuleType;
  name: string;
  faction?: string;
  detachment?: string;
};

export default function RulesText({ type, name, faction = '', detachment = '' }: RulesTextProps) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <details onToggle={(event) => setIsOpen(event.currentTarget.open)}>
      <summary style={{ cursor: 'pointer', color: '#aaa' }}>Read Rules Text</summary>
      {isOpen && <RulesTextContent type={type} name={name} faction={faction} detachment={detachment} />}
    </details>
  );
}

function RulesTextContent({ type, name, faction, detachment }: Required<RulesTextProps>) {
  const [text, setText] = useState('Loading rules...');

  useEffect(() => {
    const controller = new AbortController();
    const params = new URLSearchParams({ type, name, faction, detachment });

    fetch(`http://127.0.0.1:8000/api/codex/rule?${params.toString()}`, {
      signal: controller.signal,
    })
      .then(async (res) => {
        const data: { text?: string; detail?: string } = await res.json();
        if (!res.ok) {
          throw new Error(data.detail || `Request failed with status ${res.status}`);
        }
        return data;
      })
      .then((data) => {
        setText(data.text || 'No rules text found.');
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const message = error instanceof Error ? error.message : 'Unknown error';
        setText(`Failed to load rules: ${message}`);
      });

    return () => controller.abort();
  }, [type, name, faction, detachment]);

  return <p style={{ whiteSpace: 'pre-wrap', color: '#ddd' }}>{text}</p>;
}
