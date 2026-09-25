"""
Access to the Sentinel camera grid: credentials, session cookie, URL templates.

How the real grid authenticates (from its Integrator's Guide, 25 Sep 2026):
  * RTSP / WebRTC: the team's registered email and access password embedded
    in the URL, the email's "@" percent-encoded as "%40":
        rtsp://you%40example.com:PASSWORD@103.250.160.189:8554/stream/cam01
  * HLS and the catalogue (cameras.json): a logged-in web session on
    cctv.corp8.cloud (an unauthenticated request redirects to /auth/login).

The rule this module enforces: credentials are added to a URL at the moment a
connection is opened, and nowhere else. URLs held in CameraInfo, stored in the
registry, returned by the API, shown in the console or written to logs are
always credential-free. A password is never persisted by PRAHARI; it lives only
in the operator's prahari.env and this process's environment.
"""
from __future__ import annotations

import os
from urllib.parse import quote, urlsplit, urlunsplit

USER_ENV = "PRAHARI_STREAM_USER"          # registered email
PASSWORD_ENV = "PRAHARI_STREAM_PASSWORD"  # access password
COOKIE_ENV = "PRAHARI_INGEST_COOKIE"      # optional browser session cookie, "name=value; name2=value2"
TEMPLATE_ENV = "PRAHARI_RTSP_TEMPLATE"    # optional, e.g. rtsp://103.250.160.189:8554/stream/{id}

_CRED_SCHEMES = ("rtsp", "rtsps", "http", "https")


def _host_port(p) -> str:
    host = p.hostname or ""
    if ":" in host and not host.startswith("["):   # IPv6 literal
        host = f"[{host}]"
    return f"{host}:{p.port}" if p.port else host


def strip_credentials(url: str) -> str:
    """Remove any user:password@ from a URL. Safe on empty/garbage input."""
    if not url:
        return url
    try:
        p = urlsplit(url)
        if p.username is not None or p.password is not None:
            return urlunsplit((p.scheme, _host_port(p), p.path, p.query, p.fragment))
    except ValueError:
        pass
    return url


def credentials() -> tuple[str, str]:
    return os.environ.get(USER_ENV, ""), os.environ.get(PASSWORD_ENV, "")


def with_credentials(url: str, user: str | None = None, password: str | None = None) -> str:
    """Return `url` with user:password inserted, percent-encoded (so an email's
    "@" becomes "%40"). Only for RTSP and WHEP-style URLs that carry none yet;
    anything else is returned unchanged. Call this ONLY when opening a connection."""
    if not url:
        return url
    if user is None or password is None:
        env_user, env_pw = credentials()
        user = env_user if user is None else user
        password = env_pw if password is None else password
    if not user:
        return url
    try:
        p = urlsplit(url)
    except ValueError:
        return url
    scheme = p.scheme.lower()
    if scheme not in _CRED_SCHEMES or p.username is not None:
        return url
    # HTTP(S) gets credentials only for WHEP endpoints; HLS uses the session cookie.
    if scheme.startswith("http") and not p.path.rstrip("/").endswith("/whep"):
        return url
    userinfo = quote(user, safe="") + (":" + quote(password, safe="") if password else "")
    return urlunsplit((p.scheme, f"{userinfo}@{_host_port(p)}", p.path, p.query, p.fragment))


def session_cookie() -> str:
    return os.environ.get(COOKIE_ENV, "").strip()


def http_headers() -> dict[str, str]:
    """Headers for HTTP requests to the grid (catalogue, HLS)."""
    c = session_cookie()
    return {"Cookie": c} if c else {}


def ffmpeg_options_for(url: str) -> dict[str, str]:
    """Extra libav options for opening `url`: the session cookie for HTTP(S)/HLS."""
    if url.lower().startswith(("http://", "https://")) and session_cookie():
        return {"headers": f"Cookie: {session_cookie()}\r\n"}
    return {}


def rtsp_from_template(camera_id: str) -> str:
    """Build a credential-free RTSP URL from PRAHARI_RTSP_TEMPLATE, if set.
    Used only when a catalogue entry carries no stream URL of its own."""
    tpl = os.environ.get(TEMPLATE_ENV, "").strip()
    if not tpl or not camera_id:
        return ""
    return strip_credentials(tpl.replace("{id}", camera_id))


def scrub(text: str) -> str:
    """Remove the stream password (raw and percent-encoded) and any URL
    credentials from free text such as an error message from libav, which
    echoes the full URL it failed to open."""
    if not text:
        return text
    import re
    _, pw = credentials()
    if pw:
        for form in {pw, quote(pw, safe="")}:
            text = text.replace(form, "***")
    # user:password@ inside any URL-looking token
    return re.sub(r"([a-z][a-z0-9+.-]*://)[^/\s@]+@", r"\1***@", text, flags=re.I)
