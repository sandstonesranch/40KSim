import { Link } from 'react-router-dom';

export default function Home() {
  return (
    <div style={{ padding: '4rem', textAlign: 'center', color: 'white' }}>
      <h1 style={{ fontSize: '3rem', marginBottom: '1rem', color: '#8a2be2' }}>Warscribe 40K</h1>
      <p style={{ fontSize: '1.2rem', marginBottom: '3rem', color: '#aaa' }}>
        The ultimate open-source Warhammer 40k companion.
      </p>

      <div style={{ display: 'flex', gap: '2rem', justifyContent: 'center', flexWrap: 'wrap' }}>
        <Link to="/roster" style={{ textDecoration: 'none' }}>
          <div style={{ backgroundColor: '#2a2a2a', padding: '3rem', borderRadius: '8px', border: '1px solid #444', width: '250px', transition: 'transform 0.2s' }}>
            <h2 style={{ color: '#fff', marginBottom: '1rem' }}>🛡️ Roster Builder</h2>
            <p style={{ color: '#888' }}>Create and validate your army lists.</p>
          </div>
        </Link>

        <Link to="/codex" style={{ textDecoration: 'none' }}>
          <div style={{ backgroundColor: '#2a2a2a', padding: '3rem', borderRadius: '8px', border: '1px solid #444', width: '250px', transition: 'transform 0.2s' }}>
            <h2 style={{ color: '#fff', marginBottom: '1rem' }}>📖 Codex</h2>
            <p style={{ color: '#888' }}>Read full rules and stratagems.</p>
          </div>
        </Link>

        <Link to="/game" style={{ textDecoration: 'none' }}>
          <div style={{ backgroundColor: '#2a2a2a', padding: '3rem', borderRadius: '8px', border: '1px solid #444', width: '250px', transition: 'transform 0.2s' }}>
            <h2 style={{ color: '#fff', marginBottom: '1rem' }}>⚔️ Game Simulator</h2>
            <p style={{ color: '#888' }}>Play out battles on a virtual tabletop.</p>
          </div>
        </Link>
      </div>
    </div>
  );
}