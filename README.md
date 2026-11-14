# Stylized Maps — public site

Type a place, get an illustrated map of it (storybook, hiking, line-art, 1890 atlas, moonlight, watercolour),
add your own places, paths and notes, download PNG / SVG / PDF. Data from OpenStreetMap; no AI, no API keys.

One Docker image: a small Python server (stdlib + numpy), the map engine, fonts and `rsvg-convert`.
Storage is one folder (`/data`): an SQLite database plus each place's map data and renders.

> This repository is **generated** from the private maps project by `site_export.py`. Change the engine, themes,
> icons or site there, re-export, then commit and push here.

## How it keeps the server light
* A new place is fetched **once** (OSM + elevation) by a single background worker; identical requests are merged
  and the same place + size + language is never made twice.
* Drawing a style takes 2–6 s in a separate process (memory goes back after each map); one at a time by default.
* The browser shows a 1600 px JPG. Print PNG (3000 px) and PDFs are only made when someone downloads one, then cached.
* Zooming in past 1:1 fetches a 4000 px JPG of that style, made once per drawing and cached.
* New places get landmarks automatically (churches, fortresses, schools, caves, springs …) with icons from
  `icons/auto/`. Add a kind in `KINDS` of `webapp/landmarks_auto.py`, or a new icon to `icons/auto/`.
* Signed-in visitors can change the fonts of a style (from the fonts bundled in `fonts/`); that redraws only their copy.
* Searching for places runs in the visitor's browser (straight to OpenStreetMap's Nominatim), not on the server.
* Limits: 5 new places and 40 redraws per user per day, 30 new style drawings per day per anonymous visitor,
  60 jobs in the queue at most. All adjustable (below).

## Who can do what
| | anyone | signed in (Google) | admin |
|---|---|---|---|
| browse maps, switch styles, download | ✓ | ✓ | ✓ |
| make a map of a new place | | ✓ (daily limit) | ✓ |
| add places, paths, notes — private to them | | ✓ | ✓ |
| suggest an addition for the public map | | ✓ | ✓ |
| approve / reject suggestions, edit or remove public additions, hide / rename / delete maps, block users | | | ✓ |

The admin panel is at `/admin`; accounts whose e-mail is in `ADMIN_EMAILS` become admins when they sign in.

## Configuration (environment variables)
| variable | example | |
|---|---|---|
| `PUBLIC_URL` | `https://maps.snappages.click` | the site's address, no trailing slash. Needed for Google sign-in |
| `GOOGLE_CLIENT_ID` | `1234-abc.apps.googleusercontent.com` | from Google Cloud (below) |
| `GOOGLE_CLIENT_SECRET` | `GOCSPX-…` | from Google Cloud — keep secret |
| `ADMIN_EMAILS` | `you@gmail.com` | comma-separated |
| `SESSION_SECRET` | 64 random hex characters | signs the login cookie; `openssl rand -hex 32` |
| `PLACES_PER_DAY` / `BAKES_PER_DAY` / `ANON_RENDERS_PER_DAY` | `5` / `40` / `30` | daily limits |
| `RENDER_WORKERS` | `1` | maps drawn at the same time (each ≈ 1 CPU, ≤ 1 GB RAM) |
| `MAX_QUEUED` | `60` | refuse new jobs beyond this |
| `OSM_USER_AGENT` | `stylized-maps/1.0 (+https://maps.example.com)` | how we identify ourselves to OpenStreetMap |
| `OVERPASS_DEADLINE` | `1200` | seconds to keep retrying a busy OSM server |

Never set `DEV_LOGIN=1` on a public server — it lets anyone sign in as anyone (it exists for local testing).

## Sign in with Google — one-time setup (≈ 10 minutes)
1. Open <https://console.cloud.google.com/>, sign in, and create a project (top bar → project picker → **New project**,
   name it e.g. `stylized-maps`).
2. **APIs & Services → OAuth consent screen** (also called *Google Auth Platform → Branding*):
   * User type **External**.
   * App name `Stylized Maps`, your support e-mail, developer contact e-mail.
   * Authorized domain: `snappages.click` (or your own domain).
   * Scopes: add `openid`, `.../auth/userinfo.email`, `.../auth/userinfo.profile` — the basic, non-sensitive ones,
     so Google does not need to review the app.
   * **Audience / Publishing status → Publish app** ("In production"). While it is in *Testing*, only the test
     users you list can sign in.
3. **APIs & Services → Credentials → Create credentials → OAuth client ID**:
   * Application type **Web application**, name `stylized-maps web`.
   * Authorized JavaScript origins: `https://maps.snappages.click`
   * Authorized redirect URIs: `https://maps.snappages.click/auth/callback` — must match `PUBLIC_URL` + `/auth/callback` exactly.
   * Create → copy the **Client ID** and **Client secret**.
4. Put them in the app's environment (RivetPanel → the app → Environment): `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`,
   plus `PUBLIC_URL`, `ADMIN_EMAILS`, `SESSION_SECRET`. Restart the app.
5. Open the site → **Sign in with Google**. If Google shows `redirect_uri_mismatch`, the redirect URI in step 3 differs
   from `PUBLIC_URL/auth/callback` (check https, the subdomain, no trailing slash).

## Deploying on RivetPanel
Every push to `main` runs `.github/workflows/image.yml`, which builds the image and publishes
`ghcr.io/xenycx/stylezed-maps:latest` (and `:<commit>`).
1. First time only: GitHub → your profile → **Packages → stylezed-maps → Package settings → Change visibility → Public**
   (or give RivetPanel a registry login), so the panel can pull it.
2. RivetPanel → new app, runtime **image**, image `ghcr.io/xenycx/stylezed-maps:latest`, container port **8080**,
   a volume named `data` at **/data**, memory **2 GB**, 2 CPUs. Add the environment variables above.
3. Give it a site / domain (e.g. `maps.snappages.click`) pointing at port 8080.

**Updating:** push to `main` → wait for the *image* workflow to finish (GitHub → Actions) → in RivetPanel redeploy /
restart the app so it pulls the new `latest`. Data in `/data` is kept.

**Backups:** everything is in the `/data` volume (`site.db`, `places/`, `out/`). `out/` can be regenerated;
`site.db` and `places/*/custom.json` cannot.

## Run it on your own computer
```bash
uv run python webapp/server.py --port 8090          # http://127.0.0.1:8090
DEV_LOGIN=1 ADMIN_EMAILS=me@example.com uv run python webapp/server.py --port 8090   # sign in without Google (local only)
```
Needs `uv`, `rsvg-convert` (librsvg) and fontconfig. Or with Docker:
```bash
docker build -t stylized-maps . && docker run --rm -p 8080:8080 -v maps-data:/data -e DEV_LOGIN=1 -e ADMIN_EMAILS=me@example.com stylized-maps
```

## Where things are
| | |
|---|---|
| `webapp/server.py` | pages, JSON API, sign-in, admin API |
| `webapp/pipeline.py` | OSM lookup + download, elevation, calling the renderer |
| `webapp/jobs.py` | the two background queues |
| `webapp/db.py` | SQLite schema and helpers |
| `webapp/auth.py` | Google OAuth and the session cookie |
| `webapp/web/` | `home.html`, `map.html` (the editor), `admin.html`, their JS and CSS; UI text in `js/i18n.js` (English + Georgian) |
| `atlas/`, `styles/`, `fonts/`, `icons/library/`, `i18n/` | the map engine, themes, fonts, the icon library, the map's words per language |

Adding an icon: draw `icons/library/<id>.svg` following `CONTRACT.md`, list it in `icons/library/index.json`, push.
Adding a theme: `styles/<id>.json` (see `THEMES.md`), push. Adding a map language: `i18n/<code>.json`.

Map data © OpenStreetMap contributors (ODbL). Elevation: Mapzen / AWS Terrain Tiles. Fonts: SIL Open Font License.
