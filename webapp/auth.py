"""Sign-in with Google (OAuth 2.0 authorization-code flow) and signed session cookies. Stdlib + requests only.

Flow: /auth/google → Google's consent page → /auth/callback?code&state → we swap the code for an ID token at
Google's token endpoint (server to server, over TLS, so the token can be trusted without checking its signature —
Google documents this for tokens taken straight from the token endpoint), check audience / issuer / expiry /
verified e-mail, then set our own cookie. No passwords or Google tokens are stored.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path
from urllib.parse import urlencode

import requests

COOKIE = "sm_session"
STATE_COOKIE = "sm_oauth"
SESSION_DAYS = 30
GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"

_secret = None


def setup(data_dir):
    global _secret
    s = os.environ.get("SESSION_SECRET", "").strip()
    if not s:  # local development: keep a random secret next to the database so sessions survive restarts
        f = Path(data_dir) / ".session_secret"
        if not f.exists():
            f.write_text(secrets.token_hex(32))
            f.chmod(0o600)
        s = f.read_text().strip()
    _secret = s.encode()


def public_url():
    return os.environ.get("PUBLIC_URL", "").rstrip("/")


def google_configured():
    return bool(os.environ.get("GOOGLE_CLIENT_ID") and os.environ.get("GOOGLE_CLIENT_SECRET") and public_url())


def dev_login_enabled():
    return os.environ.get("DEV_LOGIN") == "1"


def admin_emails():
    return {e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "").split(",") if e.strip()}


def _sign(payload):
    return hmac.new(_secret, payload.encode(), hashlib.sha256).hexdigest()[:40]


def make_session(uid, version=0):
    exp = int(time.time()) + SESSION_DAYS * 86400
    payload = f"{uid}.{version}.{exp}"
    return f"{payload}.{_sign(payload)}"


def read_session(value):
    """(user id, session version) from a valid cookie, else None. Signing out bumps the version server-side."""
    try:
        uid, ver, exp, sig = value.split(".")
        if not hmac.compare_digest(sig, _sign(f"{uid}.{ver}.{exp}")) or int(exp) < time.time():
            return None
        return int(uid), int(ver)
    except (ValueError, AttributeError):
        return None


def cookie_header(name, value, max_age, secure):
    parts = [f"{name}={value}", "Path=/", "HttpOnly", "SameSite=Lax", f"Max-Age={max_age}"]
    if max_age == 0:
        parts.append("Expires=Thu, 01 Jan 1970 00:00:00 GMT")
    if secure:
        parts.append("Secure")
    return "; ".join(parts)


def redirect_uri():
    return f"{public_url()}/auth/callback"


def start_google(next_path):
    """URL to send the browser to, plus the value of the short-lived state cookie."""
    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(16)
    if not (isinstance(next_path, str) and next_path.startswith("/") and not next_path.startswith("//")):
        next_path = "/"
    params = {"client_id": os.environ["GOOGLE_CLIENT_ID"], "redirect_uri": redirect_uri(), "response_type": "code",
              "scope": "openid email profile", "state": state, "nonce": nonce, "prompt": "select_account"}
    cookie = base64.urlsafe_b64encode(json.dumps([state, nonce, next_path[:300]]).encode()).decode()
    return f"{GOOGLE_AUTH}?{urlencode(params)}", f"{cookie}.{_sign(cookie)}"


def finish_google(code, state, state_cookie):
    """Returns (claims, next_path) or raises ValueError with a short reason."""
    try:
        raw, sig = (state_cookie or "").rsplit(".", 1)
        if not hmac.compare_digest(sig, _sign(raw)):
            raise ValueError
        want_state, nonce, next_path = json.loads(base64.urlsafe_b64decode(raw.encode()))
    except (ValueError, TypeError):
        raise ValueError("The sign-in took too long or was started in another browser. Please try again.")
    if not state or not hmac.compare_digest(state, want_state):
        raise ValueError("Sign-in state did not match. Please try again.")
    r = requests.post(GOOGLE_TOKEN, data={"code": code, "client_id": os.environ["GOOGLE_CLIENT_ID"],
                                          "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
                                          "redirect_uri": redirect_uri(), "grant_type": "authorization_code"},
                      timeout=20)
    if r.status_code != 200:
        raise ValueError("Google refused the sign-in code.")
    id_token = r.json().get("id_token", "")
    try:
        body = id_token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    except (IndexError, ValueError):
        raise ValueError("Google sent an unreadable ID token.")
    if claims.get("aud") != os.environ["GOOGLE_CLIENT_ID"]:
        raise ValueError("ID token is for another application.")
    if claims.get("iss") not in ("https://accounts.google.com", "accounts.google.com"):
        raise ValueError("ID token has the wrong issuer.")
    if int(claims.get("exp", 0)) < time.time() - 60:
        raise ValueError("ID token expired.")
    if claims.get("nonce") != nonce:
        raise ValueError("ID token nonce did not match.")
    if not claims.get("email") or not claims.get("email_verified"):
        raise ValueError("Your Google account has no verified e-mail address.")
    return claims, next_path
