# Zeli Recruitment — deployment target

Target hostname: `recruitment.lab.zeli.lat`

## Railway service

- Start command: `python server.py`
- Health check: `/health`
- Port: Railway-provided `PORT`
- Persistent database: mount a Railway volume at `/data`
- Set `ZELI_DB_PATH=/data/recruitment.db`
- Set a long random `ZELI_ADMIN_TOKEN`

## Public-web discovery

The app can run without an external search provider, but the **Public web** adapter will remain unavailable. Configure one of:

- `BRAVE_SEARCH_API_KEY`
- `SERPER_API_KEY`
- `SEARXNG_URL`

The app does not log into or scrape LinkedIn. Search providers can be used to locate public professional-profile URLs, including indexed LinkedIn profile URLs.

## Custom domain

Attach `recruitment.lab.zeli.lat` to the Railway service, then add the DNS record Railway provides at the DNS host for `zeli.lat`.

Recruiter app: `https://recruitment.lab.zeli.lat/`
Operator app: `https://recruitment.lab.zeli.lat/admin`
