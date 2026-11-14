"""Stylized maps — the public site. One process: pages, JSON API, Google sign-in, admin, background queues.

usage: python webapp/server.py [--port 8080] [--host 0.0.0.0]

Environment (all optional for local development):
  PUBLIC_URL            https://maps.example.com   (needed for Google sign-in and secure cookies)
  GOOGLE_CLIENT_ID      from Google Cloud Console → APIs & Services → Credentials
  GOOGLE_CLIENT_SECRET
  ADMIN_EMAILS          comma-separated Google e-mails that get the admin panel
  SESSION_SECRET        long random string (sessions stay valid across restarts / deploys)
  DATA_DIR              where site.db lives (default: <repo>/var); data/ and out/ are the engine's folders
  PLACES_PER_DAY=5  BAKES_PER_DAY=40  ANON_RENDERS_PER_DAY=30  RENDER_WORKERS=1  MAX_QUEUED=60
  TRUST_PROXY=1         take the visitor's address from X-Forwarded-For (set when behind a reverse proxy)
  DEV_LOGIN=1           LOCAL TESTING ONLY: /auth/dev?email=… signs in without Google
"""
import argparse
import gzip
import json
import os
import re
import shutil
import sys
import threading
import time
from email.utils import formatdate, parsedate_to_datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

ROOT = Path(__file__).resolve().parent.parent
WEB = Path(__file__).resolve().parent / "web"
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import studio  # noqa: E402  (the local studio's validators, elevation profile, theme / icon lists)
from studio import ApiError, atomic_write, read_json, validate_custom  # noqa: E402

from webapp import auth, db, jobs, pipeline  # noqa: E402

SLUG_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,60}")
THEME_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,40}")
LANG_RE = re.compile(r"[a-z]{2,3}")
DEFAULT_THEME = "storybook"
MAX_BODY = 2 * 1024 * 1024
MIME = dict(studio.MIME, **{".pdf": "application/pdf", ".ico": "image/x-icon"})
COMPRESS = {".html", ".css", ".js", ".json", ".svg", ".txt"}
PLACES_PER_DAY = db.env_int("PLACES_PER_DAY", 5)
BAKES_PER_DAY = db.env_int("BAKES_PER_DAY", 40)
ANON_RENDERS = db.env_int("ANON_RENDERS_PER_DAY", 30)
EXPORTS_AT_ONCE = threading.Semaphore(2)
_place_locks, _locks_lock = {}, threading.Lock()


def place_lock(slug):
    with _locks_lock:
        return _place_locks.setdefault(slug, threading.Lock())


def languages():
    return sorted(p.stem for p in (ROOT / "i18n").glob("*.json") if LANG_RE.fullmatch(p.stem))


def themes():
    return [t for t in studio.list_themes() if THEME_RE.fullmatch(t["id"])]


def theme_ok(theme):
    return isinstance(theme, str) and THEME_RE.fullmatch(theme) and (ROOT / "styles" / f"{theme}.json").is_file()


# ---------------------------------------------------------------- places

def get_place(slug, me=None, need_ready=False):
    if not isinstance(slug, str) or not SLUG_RE.fullmatch(slug):
        raise ApiError(404, "unknown_place", "No such map.")
    p = db.one("SELECT * FROM places WHERE slug=?", slug)
    if not p or (p["hidden"] and not (me and me["is_admin"])):
        raise ApiError(404, "unknown_place", "No such map.")
    if need_ready and p["status"] != "ready":
        raise ApiError(409, "not_ready", "This map is still being prepared.")
    return p


def out_dir(slug, uid=None):
    d = ROOT / "out" / slug
    return d / "u" / str(uid) if uid else d


def renders_in(d):
    res = []
    if d.is_dir():
        for p in sorted(d.glob("*.json")):
            m = re.fullmatch(r"([a-z0-9_-]+)\.([a-z]{2,3})\.json", p.name)
            if m and (d / f"{m[1]}.{m[2]}.jpg").is_file():
                res.append({"id": f"{m[1]}.{m[2]}", "theme": m[1], "lang": m[2], "mtime": p.stat().st_mtime})
    return res


def doc_nonempty(doc):
    return any(doc.get(k) for k in ("places", "paths", "notes"))


def place_card(p):
    thumb = out_dir(p["slug"]) / "thumb.jpg"
    return {"slug": p["slug"], "name": p["name"], "name_local": p["name_local"], "lang": p["lang"], "size": p["size"],
            "display_name": p["display_name"], "status": p["status"], "created": p["created"], "hidden": p["hidden"],
            "thumb": f"/out/{p['slug']}/thumb.jpg?v={int(thumb.stat().st_mtime)}" if thumb.is_file() else None}


def place_entry(p, me):
    d = ROOT / "data" / p["slug"]
    renders = renders_in(out_dir(p["slug"]))
    if me:
        have = {r["id"] for r in renders}
        renders += [r for r in renders_in(out_dir(p["slug"], me["id"])) if r["id"] not in have]
    return {"slug": p["slug"], "name": p["name"], "name_local": p["name_local"], "lang": p["lang"],
            "display_name": p["display_name"], "size": p["size"], "status": p["status"], "error": p["error"],
            "renders": renders, "landmarks": None, "landmark_icons": [],
            "has_dem": (d / "dem.npy").is_file() and (d / "dem.json").is_file()}


def build_place(slug):
    """Fetch-queue job: download the data, then draw the first theme."""
    p = db.one("SELECT * FROM places WHERE slug=?", slug)
    if not p:
        return
    try:
        db.run("UPDATE places SET status='fetching', error=NULL, updated=? WHERE slug=?", time.time(), slug)
        if not (ROOT / "data" / slug / "dem.npy").is_file():
            pipeline.fetch_place(slug, p)
        db.run("UPDATE places SET status='rendering', updated=? WHERE slug=?", time.time(), slug)
        job = jobs.render_q.submit("render", ("pub", slug, DEFAULT_THEME, p["lang"]),
                                   lambda: render_public(slug, DEFAULT_THEME, p["lang"]))
        job.done.wait(900)
        if job.status != "done":
            raise pipeline.PlaceError(job.error or "Drawing took too long.")
        db.run("UPDATE places SET status='ready', updated=? WHERE slug=?", time.time(), slug)
    except Exception as e:
        msg = str(e)[:800]
        db.run("UPDATE places SET status='failed', error=?, updated=? WHERE slug=?", msg, time.time(), slug)
        if p["created_by"]:
            db.give_back(f"u{p['created_by']}", "place")
        raise


def render_public(slug, theme, lang):
    p = db.one("SELECT lang FROM places WHERE slug=?", slug)
    pipeline.render(slug, theme, lang, out_dir(slug), thumb=bool(p) and theme == DEFAULT_THEME and lang == p["lang"])


def render_mine(slug, uid, theme, lang):
    d = out_dir(slug, uid)
    d.mkdir(parents=True, exist_ok=True)
    pub = studio.load_custom(slug)
    mine = db.get_doc(uid, slug)
    # the visitor's own approved suggestions are already in their document: don't draw them twice
    lists = {"place": "places", "path": "paths", "note": "notes"}
    own_ids = {(k, it.get("id")) for k in lists.values() for it in mine[k]}
    dup = {r["public_id"] for r in db.all_("SELECT kind, item_id, public_id FROM submissions WHERE user_id=? AND slug=? AND status='approved'", uid, slug)
           if (lists.get(r["kind"]), r["item_id"]) in own_ids}
    merged = {k: [it for it in pub.get(k, []) if isinstance(it, dict) and it.get("id") not in dup] + mine[k] for k in ("places", "paths", "notes")}
    f = d / ".custom.json"
    atomic_write(f, json.dumps(merged, ensure_ascii=False))
    pipeline.render(slug, theme, lang, d, custom=f)


def refresh_public(slug):
    """The public additions changed: redraw every public render of the place (in the background)."""
    for r in renders_in(out_dir(slug)):
        th, lang = r["theme"], r["lang"]
        try:
            jobs.render_q.submit("render", ("pub", slug, th, lang), lambda th=th, lang=lang: render_public(slug, th, lang))
        except jobs.Busy:
            break


def sidecar(slug, theme, lang, me, doc=None):
    """The render to show this visitor: their own baked version if they have additions, else the public one."""
    mine = False
    path = None
    if me:
        doc = doc if doc is not None else db.get_doc(me["id"], slug)
        cand = out_dir(slug, me["id"]) / f"{theme}.{lang}.json"
        if doc_nonempty(doc) and cand.is_file():
            path, mine = cand, True
    if not path:
        path = out_dir(slug) / f"{theme}.{lang}.json"
    side = read_json(path)
    if not isinstance(side, dict):
        return None
    baked = side.get("baked") if isinstance(side.get("baked"), dict) else {}
    own = {k: [it for it in baked.get(k, []) if isinstance(it, dict) and not str(it.get("id", "")).startswith("pub-")]
           for k in ("places", "paths", "notes")}
    rel = path.parent.relative_to(ROOT / "out")
    side["baked"] = own
    side["_studio"] = {"mtime": path.stat().st_mtime, "baked": own, "mine": mine,
                       "dir": "/out/" + "/".join(quote(x) for x in rel.parts) + "/"}
    side.pop("fonts", None)
    return side


# ---------------------------------------------------------------- the handler

class Handler(BaseHTTPRequestHandler):
    server_version = "StylizedMaps/1"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        if os.environ.get("ACCESS_LOG") == "1":
            sys.stderr.write("%s %s\n" % (self.client_ip(), fmt % args))

    # -- helpers
    def client_ip(self):
        if os.environ.get("TRUST_PROXY", "1") == "1":
            fwd = self.headers.get("X-Forwarded-For", "")
            if fwd:
                return fwd.split(",")[0].strip()[:64]
        return self.client_address[0]

    def cookies(self):
        out = {}
        for part in (self.headers.get("Cookie") or "").split(";"):
            if "=" in part:
                k, v = part.strip().split("=", 1)
                out[k] = v
        return out

    def me(self):
        if not hasattr(self, "_me"):
            sess = auth.read_session(self.cookies().get(auth.COOKIE, ""))
            u = db.user(sess[0]) if sess else None
            self._me = u if u and not u["banned"] and u["session_v"] == sess[1] else None
        return self._me

    def need_me(self):
        u = self.me()
        if not u:
            raise ApiError(401, "login", "Sign in with Google first.")
        return u

    def need_admin(self):
        u = self.need_me()
        if not u["is_admin"]:
            raise ApiError(403, "forbidden", "Admins only.")
        return u

    def secure(self):
        return auth.public_url().startswith("https://")

    def headers_common(self, ctype):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        if ctype.startswith("text/html"):
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy",
                             "default-src 'self'; img-src 'self' data: blob: https://*.googleusercontent.com; "
                             "style-src 'self' 'unsafe-inline'; font-src 'self'; script-src 'self'; "
                             "connect-src 'self' https://nominatim.openstreetmap.org; frame-ancestors 'none'; base-uri 'none'")

    def send_bytes(self, data, ctype, status=200, cache="no-cache", extra=None):
        gz = (len(data) > 1024 and "gzip" in (self.headers.get("Accept-Encoding") or "")
              and any(ctype.startswith(t) for t in ("text/", "application/json", "image/svg")))
        if gz:
            data = gzip.compress(data, 5)
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", cache)
        if gz:
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Vary", "Accept-Encoding")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.headers_common(ctype)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def send_json(self, obj, status=200):
        self.send_bytes(json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8", status, "no-store")

    def redirect(self, url, cookies=()):
        self.send_response(302)
        self.send_header("Location", url)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        for c in cookies:
            self.send_header("Set-Cookie", c)
        self.end_headers()

    def send_file(self, target, cache="no-cache", download=None):
        st = target.stat()
        ims = self.headers.get("If-Modified-Since")
        if ims and not download:
            try:
                if int(st.st_mtime) <= parsedate_to_datetime(ims).timestamp():
                    self.send_response(304)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
            except (TypeError, ValueError, OverflowError):
                pass
        ctype = MIME.get(target.suffix.lower(), "application/octet-stream")
        extra = {"Last-Modified": formatdate(st.st_mtime, usegmt=True)}
        if download:
            extra["Content-Disposition"] = f"attachment; filename=\"{download}\""
        if target.suffix.lower() in COMPRESS and st.st_size < 12 * 1024 * 1024:
            return self.send_bytes(target.read_bytes(), ctype, 200, cache, extra)
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(st.st_size))
        self.send_header("Cache-Control", cache)
        for k, v in extra.items():
            self.send_header(k, v)
        self.headers_common(ctype)
        self.end_headers()
        if self.command != "HEAD":
            with open(target, "rb") as f:
                shutil.copyfileobj(f, self.wfile, 256 * 1024)

    def read_body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise ApiError(400, "bad_length")
        if n > MAX_BODY:
            raise ApiError(413, "too_large", "Request too large.")
        raw = self.rfile.read(n) if n else b""
        try:
            return json.loads(raw or b"{}")
        except ValueError:
            raise ApiError(400, "bad_json", "Body must be JSON.")

    def check_origin(self):
        """Writes must come from our own pages (cookies are SameSite=Lax as a second line)."""
        origin = self.headers.get("Origin")
        if not origin:
            raise ApiError(403, "bad_origin", "Missing Origin header.")
        want = auth.public_url() or f"http://{self.headers.get('Host', '')}"
        if origin.rstrip("/") != want and not (not auth.public_url() and origin.endswith("//" + self.headers.get("Host", ""))):
            raise ApiError(403, "bad_origin", "Request from another site.")

    def guarded(self, fn):
        # one handler object serves every request on a keep-alive connection (and a reverse proxy shares
        # connections between visitors): never carry who-is-signed-in from one request to the next
        self.__dict__.pop("_me", None)
        try:
            fn()
        except ApiError as e:
            try:
                self.send_json({"error": e.code, "message": e.message, **e.extra}, e.status)
            except OSError:
                self.close_connection = True
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            try:
                self.send_json({"error": "server_error", "message": f"{type(e).__name__}"}, 500)
            except OSError:
                self.close_connection = True

    # -- static
    def static(self, path):
        parts = [p for p in unquote(path).split("/") if p]
        if any(p in (".", "..") or p.startswith(".") or "\\" in p or "\x00" in p for p in parts) or not parts:
            raise ApiError(404, "not_found", "Not found.")
        head = parts[0]
        if head == "web":
            base, cache = WEB, "public, max-age=300"
            target = WEB.joinpath(*parts[1:])
        elif head == "fonts":
            base, cache = ROOT / "fonts", "public, max-age=604800"
            target = base.joinpath(*parts[1:])
        elif head == "icons" and len(parts) == 3 and parts[1] == "library":
            base, cache = ROOT / "icons" / "library", "public, max-age=3600"
            target = base / parts[2]
        elif head == "data" and len(parts) == 4 and parts[2] == "icons":
            get_place(parts[1], self.me())
            base, cache = ROOT / "data", "public, max-age=3600"
            target = base / parts[1] / "icons" / parts[3]
        elif head == "out" and len(parts) >= 3:
            get_place(parts[1], self.me())
            if len(parts) == 5 and parts[2] == "u":
                me = self.me()
                if not me or (str(me["id"]) != parts[3] and not me["is_admin"]):
                    raise ApiError(404, "not_found", "Not found.")
            elif len(parts) != 3:
                raise ApiError(404, "not_found", "Not found.")
            if not re.fullmatch(r"[a-z0-9_.-]+\.(jpg|svg|json)", parts[-1]):
                raise ApiError(404, "not_found", "Not found.")
            base, cache = ROOT / "out", "no-cache"
            target = base.joinpath(*parts[1:])
        else:
            raise ApiError(404, "not_found", "Not found.")
        target = target.resolve()
        if not target.is_relative_to(base.resolve()) or not target.is_file():
            raise ApiError(404, "not_found", "Not found.")
        self.send_file(target, cache)

    def page(self, name):
        self.send_file(WEB / name, "no-cache")

    # -- GET
    def route_get(self):
        url = urlparse(self.path)
        path, q = url.path, {k: v[0] for k, v in parse_qs(url.query).items()}
        if path in ("/", "/index.html"):
            return self.page("home.html")
        if re.fullmatch(r"/m/[a-z0-9-]+/?", path):
            return self.page("map.html")
        if path in ("/admin", "/admin/"):
            return self.page("admin.html")
        if path == "/robots.txt":
            return self.send_bytes(b"User-agent: *\nDisallow: /api/\nDisallow: /out/\n", "text/plain", cache="public, max-age=86400")
        if path == "/healthz":
            return self.send_bytes(b"ok", "text/plain")
        if path == "/auth/google":
            if not auth.google_configured():
                raise ApiError(503, "no_google", "Google sign-in is not configured on this server yet.")
            target, state = auth.start_google(q.get("next", "/"))
            return self.redirect(target, [auth.cookie_header(auth.STATE_COOKIE, state, 600, self.secure())])
        if path == "/auth/callback":
            return self.google_callback(q)
        if path == "/auth/dev":
            if not auth.dev_login_enabled():
                raise ApiError(404, "not_found", "Not found.")
            email = q.get("email", "dev@example.com")[:120]
            u = db.upsert_google_user(f"dev:{email}", email, q.get("name", email.split("@")[0])[:80], "", auth.admin_emails())
            if u["banned"]:
                raise ApiError(403, "banned", "This account is blocked.")
            return self.redirect(self.safe_next(q.get("next")), [auth.cookie_header(auth.COOKIE, auth.make_session(u["id"], u["session_v"]), auth.SESSION_DAYS * 86400, self.secure())])
        if path.startswith("/api/"):
            return self.api_get(path, q)
        return self.static(path)

    def safe_next(self, nxt):
        return nxt if isinstance(nxt, str) and nxt.startswith("/") and not nxt.startswith("//") else "/"

    def google_callback(self, q):
        clear = auth.cookie_header(auth.STATE_COOKIE, "", 0, self.secure())
        if q.get("error"):
            return self.redirect("/?login=cancelled", [clear])
        try:
            claims, nxt = auth.finish_google(q.get("code", ""), q.get("state", ""), self.cookies().get(auth.STATE_COOKIE))
        except ValueError as e:
            return self.redirect("/?login=failed&why=" + quote(str(e)), [clear])
        u = db.upsert_google_user(claims["sub"], claims["email"], claims.get("name", "")[:80], claims.get("picture", "")[:500], auth.admin_emails())
        if u["banned"]:
            return self.redirect("/?login=banned", [clear])
        return self.redirect(self.safe_next(nxt), [clear, auth.cookie_header(auth.COOKIE, auth.make_session(u["id"], u["session_v"]), auth.SESSION_DAYS * 86400, self.secure())])

    def me_public(self):
        me = self.me()
        if not me:
            return None
        key = f"u{me['id']}"
        return {"id": me["id"], "name": me["name"], "email": me["email"], "picture": me["picture"], "admin": bool(me["is_admin"]),
                "places_left": None if me["is_admin"] else max(0, PLACES_PER_DAY - db.used(key, "place")),
                "bakes_left": None if me["is_admin"] else max(0, BAKES_PER_DAY - db.used(key, "bake"))}

    def api_get(self, path, q):
        me = self.me()
        if path == "/api/me":
            return self.send_json({"me": self.me_public(), "google": auth.google_configured(), "dev_login": auth.dev_login_enabled(),
                                   "languages": languages(), "themes": themes(), "sizes": pipeline.SIZES,
                                   "limits": {"places_per_day": PLACES_PER_DAY, "bakes_per_day": BAKES_PER_DAY}})
        if path == "/api/places":
            return self.send_json(self.list_places(q, me))
        m = re.fullmatch(r"/api/map/([^/]+)", path)
        if m:
            p = get_place(m[1], me)
            job = jobs.find(("place", p["slug"]))
            subs = []
            if me:
                subs = db.all_("SELECT id, kind, item_id, status, admin_note FROM submissions WHERE user_id=? AND slug=? ORDER BY id",
                               me["id"], p["slug"])
            return self.send_json({"places": [place_entry(p, me)], "themes": themes(), "icons": {"library": studio.list_library()},
                                   "fonts": studio.list_fonts(), "me": self.me_public(), "google": auth.google_configured(),
                                   "dev_login": auth.dev_login_enabled(), "job": jobs.describe(job) if job else None,
                                   "submissions": subs, "public_counts": {k: len(v) for k, v in studio.load_custom(p["slug"]).items() if isinstance(v, list)}})
        if path == "/api/render":
            p = get_place(q.get("slug"), me, need_ready=True)
            if not theme_ok(q.get("theme")) or not LANG_RE.fullmatch(q.get("lang", "")):
                raise ApiError(400, "bad_request", "theme and lang are required.")
            side = sidecar(p["slug"], q["theme"], q["lang"], me)
            if side is None:
                raise ApiError(404, "not_rendered", "This theme has not been drawn in this language yet.")
            return self.send_json(side)
        m = re.fullmatch(r"/api/job/(\d+)", path)
        if m:
            job = jobs.get(int(m[1]))
            if not job:
                raise ApiError(404, "unknown_job", "That job finished long ago.")
            return self.send_json(jobs.describe(job))
        m = re.fullmatch(r"/api/custom/([^/]+)", path)
        if m:
            p = get_place(m[1], me)
            return self.send_json(db.get_doc(me["id"], p["slug"]) if me else {"places": [], "paths": [], "notes": []})
        m = re.fullmatch(r"/api/export/([^/]+)", path)
        if m:
            return self.export(m[1], q, me)
        if path.startswith("/api/admin/"):
            return self.admin_get(path, q)
        raise ApiError(404, "not_found", "No such endpoint.")

    def list_places(self, q, me):
        limit = min(60, max(1, int(q.get("limit", 24)) if q.get("limit", "").isdigit() else 24))
        offset = int(q["offset"]) if q.get("offset", "").isdigit() else 0
        where, args = ["hidden=0", "status='ready'"], []
        if q.get("mine") == "1":
            if not me:
                return {"places": [], "more": False}
            where = ["(created_by=? OR slug IN (SELECT slug FROM docs WHERE user_id=?))"]
            args += [me["id"], me["id"]]
        if q.get("q"):
            where.append("(name LIKE ? OR name_local LIKE ? OR display_name LIKE ?)")
            like = f"%{q['q'][:80]}%"
            args += [like, like, like]
        rows = db.all_(f"SELECT * FROM places WHERE {' AND '.join(where)} ORDER BY created DESC LIMIT ? OFFSET ?", *args, limit + 1, offset)
        return {"places": [place_card(r) for r in rows[:limit]], "more": len(rows) > limit}

    def export(self, slug, q, me):
        p = get_place(slug, me, need_ready=True)
        theme, lang, fmt, paper = q.get("theme", ""), q.get("lang", ""), q.get("fmt", ""), q.get("paper", "")
        if not theme_ok(theme) or not LANG_RE.fullmatch(lang) or fmt not in ("png", "svg", "pdf", "jpg"):
            raise ApiError(400, "bad_request", "theme, lang and fmt (png, svg, pdf, jpg) are required.")
        if paper and paper not in ("A4", "A3", "A2"):
            raise ApiError(400, "bad_paper", "paper must be A4, A3 or A2.")
        d = out_dir(slug)
        if q.get("mine") == "1" and me and (out_dir(slug, me["id"]) / f"{theme}.{lang}.svg").is_file() and doc_nonempty(db.get_doc(me["id"], slug)):
            d = out_dir(slug, me["id"])
        svg = d / f"{theme}.{lang}.svg"
        if not svg.is_file():
            raise ApiError(404, "not_rendered", "Draw this theme first.")
        name = f"{p['slug'].rsplit('-', 1)[0]}-{theme}-{lang}"
        if fmt in ("svg", "jpg"):
            return self.send_file(d / f"{theme}.{lang}.{fmt}", "no-cache", f"{name}.{fmt}")
        with EXPORTS_AT_ONCE, place_lock(f"x:{d}"):
            if fmt == "png":
                target = d / f"{theme}.{lang}.print.png"
                if not target.is_file() or target.stat().st_mtime < svg.stat().st_mtime:
                    import subprocess
                    from atlas.core import ENV
                    tmp = target.with_name("." + target.name + ".tmp")
                    subprocess.run(["rsvg-convert", "-w", "3000", "-o", str(tmp), str(svg)], check=True, env=ENV, timeout=180)
                    os.replace(tmp, target)
            else:
                from atlas.export import make_pdf, pdf_name
                target = svg.with_name(pdf_name(f"{theme}.{lang}", paper or None))
                if not target.is_file() or target.stat().st_mtime < svg.stat().st_mtime:
                    make_pdf(svg, target, paper or None, fontconfig=ROOT / "fonts.conf")
        return self.send_file(target, "no-cache", f"{name}{'-' + paper if paper else ''}.{fmt}")

    # -- POST / PUT / DELETE
    def route_write(self):
        self.check_origin()
        path = urlparse(self.path).path
        body = self.read_body()
        me = self.me()
        if path == "/auth/logout":
            if me:
                db.run("UPDATE users SET session_v = session_v + 1 WHERE id=?", me["id"])
            return self.send_bytes(b'{"ok":true}', "application/json", extra={"Set-Cookie": auth.cookie_header(auth.COOKIE, "", 0, self.secure())})
        if path == "/api/places":
            return self.create_place(body)
        if path == "/api/render":
            return self.request_render(body)
        m = re.fullmatch(r"/api/custom/([^/]+)", path)
        if m and self.command == "PUT":
            u = self.need_me()
            p = get_place(m[1], u, need_ready=True)
            doc = validate_custom(body)
            doc = {k: doc[k] for k in ("places", "paths", "notes")}
            if sum(len(v) for v in doc.values()) > 500:
                raise ApiError(400, "too_many", "Up to 500 additions per map.")
            for k in doc:
                for it in doc[k]:
                    if str(it.get("id", "")).startswith("pub-"):
                        raise ApiError(400, "bad_custom", "Ids starting with pub- are reserved.")
                    if isinstance(it.get("icon"), str) and not it["icon"].startswith("library/"):
                        it["icon"] = None
            db.put_doc(u["id"], p["slug"], doc)
            return self.send_json({"ok": True, "counts": {k: len(v) for k, v in doc.items()}})
        if path in ("/api/profile", "/api/elevation"):
            p = get_place(body.get("slug"), me, need_ready=True)
            if path == "/api/profile":
                return self.send_json(studio.profile(p["slug"], body.get("coords")))
            return self.send_json(studio.elevations(p["slug"], body.get("points")))
        if path == "/api/submit":
            return self.submit(body)
        m = re.fullmatch(r"/api/submit/(\d+)/withdraw", path)
        if m:
            u = self.need_me()
            n = db.run("UPDATE submissions SET status='withdrawn' WHERE id=? AND user_id=? AND status='pending'", int(m[1]), u["id"])
            return self.send_json({"ok": bool(n)})
        if path.startswith("/api/admin/"):
            return self.admin_write(path, body)
        raise ApiError(404, "not_found", "No such endpoint.")

    def create_place(self, body):
        u = self.need_me()
        size, lang = body.get("size"), body.get("lang")
        osm_type, osm_id = body.get("osm_type"), body.get("osm_id")
        if size not in pipeline.SIZES or lang not in languages():
            raise ApiError(400, "bad_request", "Choose a size and a language.")
        if osm_type not in ("node", "way", "relation") or not isinstance(osm_id, int):
            raise ApiError(400, "bad_place", "Pick a place from the search results.")
        old = db.one("SELECT * FROM places WHERE osm_type=? AND osm_id=? AND size=? AND lang=? AND status!='failed' ORDER BY created LIMIT 1",
                     osm_type, osm_id, size, lang)
        if old and not old["hidden"]:
            return self.send_json({"slug": old["slug"], "existing": True})
        key = f"u{u['id']}"
        if not u["is_admin"] and not db.take(key, "place", PLACES_PER_DAY):
            raise ApiError(429, "quota", f"You can make {PLACES_PER_DAY} new maps a day. Try again tomorrow.")
        try:
            info = pipeline.lookup(osm_type, osm_id, lang)
        except Exception as e:  # noqa: BLE001
            db.give_back(key, "place")
            raise ApiError(502, "lookup_failed", f"OpenStreetMap could not find that place ({e}).")
        slug = pipeline.slug_for(info["name"])
        now = time.time()
        db.run("INSERT INTO places(slug, osm_type, osm_id, name, name_local, display_name, lang, size, radius, lat, lon, status, created_by, created, updated) "
               "VALUES(?,?,?,?,?,?,?,?,?,?,?,'queued',?,?,?)", slug, osm_type, osm_id, info["name"], info["name_local"], info["display_name"],
               lang, size, pipeline.SIZES[size], info["lat"], info["lon"], u["id"], now, now)
        self.queue_place(slug)
        return self.send_json({"slug": slug, "existing": False})

    def queue_place(self, slug):
        try:
            jobs.fetch_q.submit("fetch", ("place", slug), lambda: build_place(slug))
        except jobs.Busy:
            db.run("UPDATE places SET status='failed', error=? WHERE slug=?", "The site is very busy. Try again later.", slug)
            raise ApiError(503, "busy", "The site is very busy right now. Try again in a few minutes.")

    def request_render(self, body):
        me = self.me()
        p = get_place(body.get("slug"), me, need_ready=True)
        slug, theme, lang = p["slug"], body.get("theme"), body.get("lang")
        if not theme_ok(theme) or lang not in ("en", p["lang"]):
            raise ApiError(400, "bad_request", "Unknown theme or language.")
        doc = db.get_doc(me["id"], slug) if me else None
        if doc and doc_nonempty(doc):
            key = f"u{me['id']}"
            if not me["is_admin"] and not db.take(key, "bake", BAKES_PER_DAY):
                raise ApiError(429, "quota", f"You can redraw {BAKES_PER_DAY} times a day. Try again tomorrow.")
            jk = ("bake", slug, me["id"], theme, lang)
            fn = lambda: render_mine(slug, me["id"], theme, lang)  # noqa: E731
        else:
            if (out_dir(slug) / f"{theme}.{lang}.json").is_file():
                return self.send_json({"job": None, "done": True})
            jk = ("pub", slug, theme, lang)
            if not jobs.find(jk) and not me and not db.take(f"ip:{self.client_ip()}", "render", ANON_RENDERS):
                raise ApiError(429, "quota", "Sign in to draw more styles today.")
            fn = lambda: render_public(slug, theme, lang)  # noqa: E731
        try:
            job = jobs.render_q.submit("render", jk, fn)
        except jobs.Busy:
            raise ApiError(503, "busy", "The site is very busy right now. Try again in a few minutes.")
        return self.send_json({"job": jobs.describe(job), "done": False})

    def submit(self, body):
        u = self.need_me()
        p = get_place(body.get("slug"), u, need_ready=True)
        kind, item_id = body.get("type"), body.get("id")
        lists = {"place": "places", "path": "paths", "note": "notes"}
        if kind not in lists or not isinstance(item_id, str):
            raise ApiError(400, "bad_request", "type and id are required.")
        doc = db.get_doc(u["id"], p["slug"])
        item = next((it for it in doc[lists[kind]] if it.get("id") == item_id), None)
        if not item:
            raise ApiError(404, "unknown_item", "Save the item first.")
        pending = db.one("SELECT id FROM submissions WHERE user_id=? AND slug=? AND item_id=? AND kind=? AND status='pending'",
                         u["id"], p["slug"], item_id, kind)
        if pending:
            db.run("UPDATE submissions SET item=?, created=? WHERE id=?", json.dumps(item, ensure_ascii=False), time.time(), pending["id"])
            return self.send_json({"ok": True, "id": pending["id"], "updated": True})
        n = db.one("SELECT COUNT(*) AS n FROM submissions WHERE user_id=? AND status='pending'", u["id"])["n"]
        if n >= 50 and not u["is_admin"]:
            raise ApiError(429, "quota", "You have 50 suggestions waiting for review already.")
        sid = db.run("INSERT INTO submissions(slug, user_id, kind, item_id, item, status, created) VALUES(?,?,?,?,?,'pending',?)",
                     p["slug"], u["id"], kind, item_id, json.dumps(item, ensure_ascii=False), time.time())
        return self.send_json({"ok": True, "id": sid})

    # -- admin
    def admin_get(self, path, q):
        self.need_admin()
        if path == "/api/admin/overview":
            def du(d):
                return sum(f.stat().st_size for f in d.rglob("*") if f.is_file()) if d.is_dir() else 0
            counts = {r["status"]: r["n"] for r in db.all_("SELECT status, COUNT(*) AS n FROM places GROUP BY status")}
            return self.send_json({"queues": jobs.stats(), "places": counts,
                                   "users": db.one("SELECT COUNT(*) AS n FROM users")["n"],
                                   "pending": db.one("SELECT COUNT(*) AS n FROM submissions WHERE status='pending'")["n"],
                                   "disk_mb": {"data": round(du(ROOT / "data") / 2**20), "out": round(du(ROOT / "out") / 2**20)},
                                   "free_mb": round(shutil.disk_usage(ROOT / "out" if (ROOT / "out").exists() else ROOT).free / 2**20)})
        if path == "/api/admin/submissions":
            status = q.get("status", "pending")
            rows = db.all_("SELECT s.*, u.email, u.name AS user_name, p.name AS place_name, p.name_local AS place_name_local "
                           "FROM submissions s JOIN users u ON u.id=s.user_id JOIN places p ON p.slug=s.slug "
                           "WHERE s.status=? ORDER BY s.created DESC LIMIT 200", status)
            for r in rows:
                r["item"] = json.loads(r["item"])
            return self.send_json({"submissions": rows})
        if path == "/api/admin/places":
            like = f"%{q.get('q', '')[:80]}%"
            rows = db.all_("SELECT p.*, u.email FROM places p LEFT JOIN users u ON u.id=p.created_by "
                           "WHERE p.name LIKE ? OR p.name_local LIKE ? OR p.slug LIKE ? OR IFNULL(u.email,'') LIKE ? "
                           "ORDER BY p.created DESC LIMIT 300", like, like, like, like)
            for r in rows:
                r["thumb"] = place_card(r)["thumb"]
                r["public_counts"] = {k: len(v) for k, v in studio.load_custom(r["slug"]).items() if isinstance(v, list)}
            return self.send_json({"places": rows})
        m = re.fullmatch(r"/api/admin/public/([^/]+)", path)
        if m:
            p = get_place(m[1], self.me())
            return self.send_json(studio.load_custom(p["slug"]))
        if path == "/api/admin/users":
            like = f"%{q.get('q', '')[:80]}%"
            rows = db.all_("SELECT u.id, u.email, u.name, u.is_admin, u.banned, u.created, u.last_seen, "
                           "(SELECT COUNT(*) FROM places p WHERE p.created_by=u.id) AS places, "
                           "(SELECT COUNT(*) FROM submissions s WHERE s.user_id=u.id) AS submissions "
                           "FROM users u WHERE u.email LIKE ? OR u.name LIKE ? ORDER BY u.last_seen DESC LIMIT 300", like, like)
            return self.send_json({"users": rows})
        raise ApiError(404, "not_found", "No such endpoint.")

    def admin_write(self, path, body):
        admin = self.need_admin()
        m = re.fullmatch(r"/api/admin/submissions/(\d+)", path)
        if m:
            s = db.one("SELECT * FROM submissions WHERE id=?", int(m[1]))
            if not s:
                raise ApiError(404, "unknown", "No such submission.")
            action = body.get("action")
            if action == "reject":
                db.run("UPDATE submissions SET status='rejected', admin_note=?, reviewed=?, reviewed_by=? WHERE id=?",
                       str(body.get("note", ""))[:500], time.time(), admin["id"], s["id"])
                return self.send_json({"ok": True})
            if action != "approve":
                raise ApiError(400, "bad_request", "action must be approve or reject.")
            item = dict(json.loads(s["item"]))
            if isinstance(body.get("item"), dict):  # the admin corrected the text before approving
                for k in ("name", "note", "text"):
                    if isinstance(body["item"].get(k), str):
                        item[k] = body["item"][k][:1000]
            item["id"] = s["public_id"] or f"pub-{s['id']}"
            lists = {"place": "places", "path": "paths", "note": "notes"}
            with place_lock(s["slug"]):
                pub = studio.load_custom(s["slug"])
                lst = pub[lists[s["kind"]]]
                pub[lists[s["kind"]]] = [it for it in lst if it.get("id") != item["id"]] + [item]
                validate_custom(pub)
                atomic_write(ROOT / "data" / s["slug"] / "custom.json", json.dumps(pub, ensure_ascii=False, indent=1) + "\n")
            db.run("UPDATE submissions SET status='approved', public_id=?, admin_note=?, reviewed=?, reviewed_by=? WHERE id=?",
                   item["id"], str(body.get("note", ""))[:500], time.time(), admin["id"], s["id"])
            refresh_public(s["slug"])
            return self.send_json({"ok": True})
        m = re.fullmatch(r"/api/admin/public/([^/]+)", path)
        if m:
            p = get_place(m[1], admin)
            doc = validate_custom(body)
            for k in ("places", "paths", "notes"):
                for it in doc[k]:
                    if not str(it["id"]).startswith("pub-"):
                        it["id"] = "pub-" + str(it["id"])
            with place_lock(p["slug"]):
                atomic_write(ROOT / "data" / p["slug"] / "custom.json", json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
            refresh_public(p["slug"])
            return self.send_json({"ok": True})
        m = re.fullmatch(r"/api/admin/places/([^/]+)", path)
        if m:
            p = get_place(m[1], admin)
            action = body.get("action")
            if action in ("hide", "unhide"):
                db.run("UPDATE places SET hidden=? WHERE slug=?", 1 if action == "hide" else 0, p["slug"])
            elif action == "rename":
                for k in ("name", "name_local"):
                    if isinstance(body.get(k), str) and body[k].strip():
                        db.run(f"UPDATE places SET {k}=? WHERE slug=?", body[k].strip()[:120], p["slug"])
                meta_f = ROOT / "data" / p["slug"] / "meta.json"
                meta = read_json(meta_f)
                if isinstance(meta, dict):
                    np_ = db.one("SELECT name, name_local FROM places WHERE slug=?", p["slug"])
                    meta.update(np_)
                    atomic_write(meta_f, json.dumps(meta, ensure_ascii=False, indent=1))
                    refresh_public(p["slug"])
            elif action == "rerender":
                refresh_public(p["slug"])
            elif action == "retry":
                if p["status"] != "failed":
                    raise ApiError(400, "bad_request", "Only failed maps can be retried.")
                db.run("UPDATE places SET status='queued', error=NULL WHERE slug=?", p["slug"])
                self.queue_place(p["slug"])
            elif action == "delete":
                db.run("DELETE FROM places WHERE slug=?", p["slug"])
                for d in (ROOT / "data" / p["slug"], ROOT / "out" / p["slug"]):
                    shutil.rmtree(d, ignore_errors=True)
            else:
                raise ApiError(400, "bad_request", "Unknown action.")
            return self.send_json({"ok": True})
        m = re.fullmatch(r"/api/admin/users/(\d+)", path)
        if m:
            uid, action = int(m[1]), body.get("action")
            if uid == admin["id"]:
                raise ApiError(400, "bad_request", "You cannot change your own account here.")
            sets = {"ban": "banned=1, session_v=session_v+1", "unban": "banned=0", "admin": "is_admin=1", "unadmin": "is_admin=0"}
            if action not in sets:
                raise ApiError(400, "bad_request", "Unknown action.")
            db.run(f"UPDATE users SET {sets[action]} WHERE id=?", uid)
            if action == "ban" and body.get("purge"):
                db.run("DELETE FROM docs WHERE user_id=?", uid)
                db.run("UPDATE submissions SET status='rejected', admin_note='account blocked' WHERE user_id=? AND status='pending'", uid)
            return self.send_json({"ok": True})
        raise ApiError(404, "not_found", "No such endpoint.")

    def do_GET(self):
        self.guarded(self.route_get)

    do_HEAD = do_GET

    def do_POST(self):
        self.guarded(self.route_write)

    do_PUT = do_POST
    do_DELETE = do_POST


def resume_unfinished():
    for p in db.all_("SELECT slug FROM places WHERE status IN ('queued', 'fetching', 'rendering')"):
        try:
            jobs.fetch_q.submit("fetch", ("place", p["slug"]), lambda s=p["slug"]: build_place(s))
        except jobs.Busy:
            break


def housekeeping():
    while True:
        try:
            db.prune_usage()
        except Exception:  # noqa: BLE001
            pass
        time.sleep(6 * 3600)


def main():
    ap = argparse.ArgumentParser(description="Stylized maps — public site")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8080")))
    ap.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    a = ap.parse_args()
    data_dir = Path(os.environ.get("DATA_DIR") or ROOT / "var")
    data_dir.mkdir(parents=True, exist_ok=True)
    for sub in ("data", "out"):
        (ROOT / sub).mkdir(exist_ok=True)
    db.init(Path(os.environ.get("DB_PATH") or data_dir / "site.db"))
    auth.setup(data_dir)
    jobs.start()
    resume_unfinished()
    threading.Thread(target=housekeeping, daemon=True).start()
    ThreadingHTTPServer.daemon_threads = True
    ThreadingHTTPServer.request_queue_size = 64
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    print(f"Stylized maps site on http://{a.host}:{a.port}/  google={'on' if auth.google_configured() else 'off'}"
          f"{'  DEV_LOGIN ON' if auth.dev_login_enabled() else ''}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
