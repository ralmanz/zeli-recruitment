# Zeli Recruitment — Calibrador de perfil

Profile calibration for recruiters and hiring clients. The client reacts to 6 example profiles (sí / no + why). The app learns a **master profile** from those reactions and derives every outreach piece from it.

Five predetermined briefs ship with it, so testers can explore freely without typing a brief from scratch.

## Run locally

```bash
python server.py
```

Open `http://localhost:8080`.

No build step. The app is static (Preact + htm, ES modules vendored in `static/vendor/`).

Query params:

- `?b=contador` — open a specific brief (`ventas`, `contador`, `bodega`, `dev`, `marketing`)
- `?research=1` — show the before/after research strip (for internal demos)

Or serve `static/` directly:

```bash
cd static && python3 -m http.server 8080
```

## Deploy (Railway)

- Start command: `python server.py`
- Health check: `/health`
- Port: Railway-provided `PORT`

Set `ZELI_ADMIN_TOKEN` if you use the legacy operator dashboard at `/admin`.

## Files

| File | What it is |
|---|---|
| `static/index.html` | Shell. Loads fonts, `styles.css`, `app.js`. |
| `static/styles.css` | All styles and animations. |
| `static/app.js` | UI (Preact + htm). Components: `App`, `Picker`, `Card`, `LivePanel`, `Kit`. |
| `static/engine.js` | Pure logic. `computeProfile(brief, state)` and `buildChannels(brief, profile, state)`. |
| `static/data/briefs.js` | The 5 demo briefs. |
| `static/vendor/` | Preact and htm ES modules (MIT). |
| `server.py` | Static file server + legacy V4 API (optional). |

## Core rule

`state.decisions` (`[{ i, v: 'yes'|'no', r: [reasonIndex] }]`) plus `state.confirmed` hold everything the client said. The live panel, master profile, and all channel texts are **derived** on every render, never stored.

## Legacy V4 sourcing engine

The previous multi-source sourcing agent (internal pool, public web, GitHub) remains in `server.py` and is accessible at `/admin` for operator use. The main recruiter flow at `/` is now the calibrador.
