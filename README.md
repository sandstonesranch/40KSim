# 40Ksim

Warhammer 40,000 roster builder, codex reference and (eventually) game simulator.

## Quick start

Requires Python 3.12+ and Node.js 20+.

```bash
./dev.sh            # first run installs dependencies, then starts both servers
```

| Command | What it does |
|---|---|
| `./dev.sh` | Backend (http://127.0.0.1:8000) and frontend (http://localhost:5173) together. Ctrl+C stops both. |
| `./dev.sh backend` | FastAPI backend only. API docs at `/docs`. |
| `./dev.sh frontend` | Vite frontend only. |
| `./dev.sh test` | Backend test suite. Extra args go to pytest, e.g. `./dev.sh test -k validator`. |
| `./dev.sh setup` | Install dependencies and exit. |

In VS Code, run **Terminal > Run Build Task** (default: "40Ksim: start all"), or pick any
"40Ksim:" task from **Terminal > Run Task**.

The frontend calls the backend at `http://127.0.0.1:8000`, so keep the backend on that port.

### Optional pieces

- **Codex rules text** comes from the 40k MCP server. Point `FORTYK_MCP_SERVER_DIR` at a built
  copy (default `~/40k-mcp-server`). Without it, roster building works but Codex text is unavailable.
- **Faction lore** is read from `data-schema/factions/faction_metadata.json`. Generate it with
  `scripts/generate_lore.py` if it is missing.
