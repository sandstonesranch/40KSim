import { Link, useLocation } from 'react-router-dom';

export default function Navbar() {
  const location = useLocation();

  return (
    <nav className="main-navigation" aria-label="Main navigation">
      <Link to="/" className="navigation-brand">
        <span className="navigation-brand-mark" aria-hidden="true">⚙</span>
        <span>Warscribe 40K</span>
      </Link>

      <div className="navigation-links">
        <Link to="/" className={`navigation-link${location.pathname === '/' ? ' active' : ''}`} aria-current={location.pathname === '/' ? 'page' : undefined}>Home</Link>
        <Link to="/roster" className={`navigation-link${location.pathname === '/roster' ? ' active' : ''}`} aria-current={location.pathname === '/roster' ? 'page' : undefined}>Roster Builder</Link>
        <Link to="/codex" className={`navigation-link${location.pathname === '/codex' ? ' active' : ''}`} aria-current={location.pathname === '/codex' ? 'page' : undefined}>Codex</Link>
        <Link to="/game" className={`navigation-link${location.pathname === '/game' ? ' active' : ''}`} aria-current={location.pathname === '/game' ? 'page' : undefined}>Simulator</Link>
        <Link to="/profile" className={`navigation-link${location.pathname === '/profile' ? ' active' : ''}`} aria-current={location.pathname === '/profile' ? 'page' : undefined}>Profile</Link>
      </div>
    </nav>
  );
}