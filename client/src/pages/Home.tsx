import { Link } from 'react-router-dom';

export default function Home() {
  return (
    <main className="home-screen">
      <p className="home-eyebrow">ADEPTUS MECHANICUS // COGITATOR ACCESS</p>
      <h1 className="home-title">Warscribe 40K</h1>
      <p className="home-intro">
        The ultimate open-source Warhammer 40k companion.
      </p>

      <div className="home-module-grid">
        <Link to="/roster" className="home-module-link">
          <section className="home-module-card">
            <span className="home-module-code">01 // COMMAND</span>
            <h2>Roster Builder</h2>
            <p>Create and validate your army lists.</p>
            <span className="home-module-action">INITIALIZE MODULE →</span>
          </section>
        </Link>

        <Link to="/codex" className="home-module-link">
          <section className="home-module-card">
            <span className="home-module-code">02 // ARCHIVES</span>
            <h2>Codex</h2>
            <p>Read full rules and stratagems.</p>
            <span className="home-module-action">ACCESS ARCHIVES →</span>
          </section>
        </Link>

        <Link to="/game" className="home-module-link">
          <section className="home-module-card">
            <span className="home-module-code">03 // BATTLEFIELD</span>
            <h2>Game Simulator</h2>
            <p>Play out battles on a virtual tabletop.</p>
            <span className="home-module-action">ENTER SIMULATOR →</span>
          </section>
        </Link>
      </div>
    </main>
  );
}