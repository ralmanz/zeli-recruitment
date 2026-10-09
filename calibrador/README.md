# Calibrador de perfil — demo (PR-01)

A demo for recruiters and their hiring clients. The client reacts to 6 example profiles (sí / no + why).
The page learns a **master profile** from those reactions and derives every outreach piece from it.

Five predetermined briefs ship with it, so testers can explore freely without typing a brief from scratch.

## Run it

No build step. Any static server works:

```bash
npx serve .            # or: python3 -m http.server 8080
```

Open `http://localhost:8080`.

- `?b=contador` opens a specific brief (`ventas`, `contador`, `bodega`, `dev`, `marketing`).
- `?research=1` shows the before/after research strip (for our own demos, not for testers).

## Deploy (Railway)

Static site. Either:
- add a `Dockerfile` with `FROM nginx:alpine` + `COPY . /usr/share/nginx/html`, or
- use Railway's static template with this folder as the root.

Everything is vendored (`vendor/`), so the only external request is Google Fonts.

## Files

| File | What it is |
|---|---|
| `index.html` | Shell. Loads fonts, `styles.css`, `app.js`. |
| `styles.css` | All styles and animations. Colors are CSS variables at the top. |
| `app.js` | UI (Preact + htm, no JSX, no build). Components: `App`, `Picker`, `Card`, `LivePanel`, `Kit`. |
| `engine.js` | Pure logic, no DOM. `computeProfile(brief, state)` and `buildChannels(brief, profile, state)`. |
| `data/briefs.js` | The 5 demo briefs, as data. The shape is documented at the top of the file. |
| `vendor/` | Preact 10.24.3 and htm 3.1.1 ES modules (MIT). |

## Core rule: the reaction log is the source of truth

`state.decisions` (`[{ i, v: 'yes'|'no', r: [reasonIndex] }]`) plus `state.confirmed` hold everything the client said.
The live panel, master profile, and all channel texts are **derived** on every render, never stored.
Keep it this way. It is what lets a client re-react later and have the whole kit update.

## How learning works (engine.js)

- Each criterion starts at `base` (0–100). Its `src` explains where that starting value came from (the brief, or a recruiter assumption).
- Each reason chip carries `fx`:
  - a `critId` key adds or subtracts weight;
  - a `db_*` key flags a dealbreaker;
  - an `n_*` key counts toward the brief's hidden-constraint insight.
- Accepting a card adds +5 to the `lead` criterion and to `exp`.
- Weight ≥ 60 means **Imprescindible**; 1–59 means **Deseable**; 0 means it is not shown.
- **Insight**: when `n_*` reaches `threshold`, the live panel asks the client to confirm a hidden constraint. Confirming does three things:
  - raises that criterion to `confirm.min`;
  - flags `confirm.db`;
  - switches the criterion to its `confirmedLabel` and `confirmedPost`.
- **Evidence**: every weight change records "Sí/No a X: “reason”". The master profile shows the last 3 per criterion.
- A `fromBrief` criterion that ends below Imprescindible gets the note "El brief lo pedía; las reacciones lo dejaron como deseable".
- The clarity % is a demo heuristic, not a real measure: `18 + 11·reactions + 2·reasons (+8 if confirmed)`, capped at 97.

## Channels (buildChannels)

Grouped by search stage. All are generic templates filled from the profile and the brief's `meta` and `boolean` fields.

- **Publicar**: ATS opening (Zoho Recruit or similar: description, requirements, tags, yes/no screening questions), job boards (Konzerta / Computrabajo), LinkedIn post.
- **Buscar**: LinkedIn boolean + filters, GitHub (only if the brief has `github`), own candidate base.
- **Contactar**: InMail or email to a passive candidate, WhatsApp to the network for referrals.
- **Filtrar**: first-call script (must questions in order, then dealbreakers).

## Adding a brief

Copy one entry in `data/briefs.js`. Each brief needs:
- 6 cards, each with `yes` and `no` reason lists;
- one `insight` whose `counter` matches the `n_*` keys used in its reasons;
- `confirm.crit` and `confirm.db` pointing at an existing criterion and dealbreaker.

Design each card to contrast with the others, so every reaction teaches something.

Sanity checks:
- every `fx` key is a crit id, a db id, or the insight counter;
- run through all-yes, all-no and mixed paths, and check that no channel text contains `undefined`.

## Copy conventions

- Spanish, formal "usted", Panamá context.
- Placeholders in brackets for anything not learned: `[RANGO]`, `[ENLACE O CORREO]`, `[Nombre]`.
- Never invent salary or modality. If the client didn't decide it, it goes to "Por confirmar con el cliente".

## Out of scope for this demo

- Free-text briefs or LLM-generated examples (planned next: generate the 6 cards + chips from a typed brief).
- Persistence and auth (state lives in memory; reload resets it).
- Separate recruiter and client links. The demo shows both sides on one page; in production the client would get a link and the recruiter would receive the master profile.

## Ideas for the next iteration

1. Persist sessions (Postgres on Railway): `searches`, `decisions`, `confirmations`.
2. Separate client link (react + send) from recruiter view (master profile + kit).
3. "Re-calibrar": the recruiter adds 3 more example cards after the first real candidates come back.
4. LLM step: brief → 6 contrasting cards + chips + `fx`, validated with the same sanity checks as above.
