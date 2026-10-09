# Zeli Recruitment — deployment (Railway)

Target hostname: `recruitment.lab.zeli.lat`

## What gets deployed

The main app at `/` is **Calibrador de perfil** — a static Preact app served by `server.py`. No build step, no Python packages.

`railway.json` is already configured:

- **Start command:** `python server.py`
- **Health check:** `/health` (returns `{"ok": true, "version": "calibrador-1"}`)
- **Port:** Railway sets `PORT` automatically

## Minimum setup

Push the repo and deploy. No env vars are required for the calibrador demo.

Railway will run Nixpacks, detect Python, and start the server. Static assets live in `static/` and are served from the same process.

## Optional: legacy operator dashboard

The V4 sourcing engine is still available at `/admin` if you set:

```bash
ZELI_ADMIN_TOKEN=<long-random-value>
```

Without this variable, `/admin` and its API routes return 401 in production.

If you use the operator dashboard, also consider:

- **Volume** mounted at `/data` (ephemeral disk resets on redeploy without it)
- `ZELI_DB_PATH=/data/recruitment.db`
- Search provider keys (`BRAVE_SEARCH_API_KEY`, `SERPER_API_KEY`, or `SEARXNG_URL`) for public-web discovery

## Custom domain

1. Attach `recruitment.lab.zeli.lat` to the Railway service.
2. Add the DNS record Railway provides at the DNS host for `zeli.lat`.

| URL | What |
|---|---|
| `https://recruitment.lab.zeli.lat/` | Calibrador (main) |
| `https://recruitment.lab.zeli.lat/?b=contador` | Open a specific demo brief |
| `https://recruitment.lab.zeli.lat/admin` | Legacy operator dashboard (needs `ZELI_ADMIN_TOKEN`) |

## Deploy checklist

1. Push to the branch Railway watches (usually `main`).
2. Confirm `/health` passes in Railway deploy logs.
3. Open `/` and verify the calibrador loads (JS/CSS from `/app.js`, `/styles.css`, etc.).
4. Optionally attach the custom domain.

No Dockerfile needed — the Python static server is enough. If you later want a pure-static deploy with no backend, you can switch to Railway's static template or nginx, but the current setup works as-is.
