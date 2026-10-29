import { Link, useLocation } from 'react-router-dom';

export default function Navbar() {
  const location = useLocation();
  const isActive = (path: string) => location.pathname === path ? { color: '#8a2be2', fontWeight: 'bold' } : { color: '#aaa' };

  return (
    <nav style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '1rem 2rem', backgroundColor: '#1a1a1a', borderBottom: '1px solid #333' }}>
      <Link to="/" style={{ textDecoration: 'none' }}>
        <h2 style={{ margin: 0, color: '#fff', fontSize: '1.2rem' }}>Warscribe 40K</h2>
      </Link>

      <div style={{ display: 'flex', gap: '2rem', fontSize: '1rem' }}>
        <Link to="/" style={{ ...isActive('/'), textDecoration: 'none' }}>Home</Link>
        <Link to="/roster" style={{ ...isActive('/roster'), textDecoration: 'none' }}>Roster Builder</Link>
        <Link to="/codex" style={{ ...isActive('/codex'), textDecoration: 'none' }}>Codex</Link>
        <Link to="/game" style={{ ...isActive('/game'), textDecoration: 'none' }}>Simulator</Link>
        <Link to="/profile" style={{ ...isActive('/profile'), textDecoration: 'none' }}>Profile</Link>
      </div>
    </nav>
  );
}