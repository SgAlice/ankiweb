"""Password gate for the web UI.

If `ANKIWEB_PASSWORD` (Settings.password) is empty, the app is fully open (the upstream default,
meant for localhost). When set, every web request needs a valid session cookie.

Fork: hardened for exposing the app on the internet (behind an HTTPS reverse proxy):
- session cookies are signed, expiring tokens (`<issued>.<nonce>.<hmac>`). The HMAC key comes
  from a random per-install secret (`auth_secret`, mode 0600, next to the collection) plus the
  password, so changing the password or deleting the secret file logs every device out.
  (Upstream used a fixed, unsalted hash of the password as the cookie value, which never expired.)
- cookies are HttpOnly, SameSite=Lax and Secure over HTTPS (including X-Forwarded-Proto)
- login attempts are rate-limited per client IP and globally
- the WebSocket bridge also checks Origin against Host (cross-site WebSocket hijacking)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
from collections import deque
from pathlib import Path

COOKIE = "ankiweb_auth"
# Paths reachable without a session cookie even when a password is set.
OPEN_PATHS = frozenset({"/login", "/logout", "/healthz", "/manifest.webmanifest",
                        "/ankiweb-icon.png", "/apple-touch-icon.png",
                        "/apple-touch-icon-precomposed.png"})
DEFAULT_SESSION_DAYS = 90


def password_ok(submitted: str, password: str) -> bool:
    """Constant-time check of a submitted password against the configured one."""
    return hmac.compare_digest((submitted or "").encode("utf-8"), (password or "").encode("utf-8"))


def _load_secret(path: Path) -> bytes:
    try:
        data = path.read_bytes()
        if len(data) >= 32:
            return data
    except FileNotFoundError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    data = secrets.token_bytes(32)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    return data


class Authenticator:
    """Issues and verifies session tokens. No password configured -> everything is allowed."""

    def __init__(self, password: str, secret_path: Path | None = None,
                 max_age_days: int = DEFAULT_SESSION_DAYS) -> None:
        self.password = password or ""
        self.max_age = max(1, int(max_age_days)) * 86400
        self._key = b""
        if self.password:
            secret = _load_secret(secret_path) if secret_path else secrets.token_bytes(32)
            self._key = hmac.new(secret, b"ankiweb-session-v2:" + self.password.encode("utf-8"),
                                 hashlib.sha256).digest()

    @property
    def enabled(self) -> bool:
        return bool(self.password)

    def _sign(self, payload: str) -> str:
        mac = hmac.new(self._key, payload.encode("ascii"), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(mac).decode("ascii").rstrip("=")

    def issue(self, now: float | None = None) -> str:
        payload = f"{int(now if now is not None else time.time())}.{secrets.token_urlsafe(12)}"
        return f"{payload}.{self._sign(payload)}"

    def verify(self, token: str | None, now: float | None = None) -> bool:
        if not self.enabled:
            return True
        if not token or token.count(".") != 2:
            return False
        issued_s, nonce, sig = token.split(".")
        try:
            issued = int(issued_s)
            payload = f"{issued}.{nonce}"
            expected = self._sign(payload)
        except (ValueError, UnicodeEncodeError):
            return False
        if not hmac.compare_digest(sig, expected):
            return False
        now = now if now is not None else time.time()
        return issued - 300 <= now <= issued + self.max_age


class LoginLimiter:
    """Sliding-window limit on failed logins: per client and across all clients."""

    def __init__(self, per_client: int = 5, overall: int = 30, window: float = 15 * 60) -> None:
        self.per_client = per_client
        self.overall = overall
        self.window = window
        self._fails: dict[str, deque] = {}
        self._all: deque = deque()

    def _trim(self, q: deque, now: float) -> None:
        while q and q[0] <= now - self.window:
            q.popleft()

    def blocked(self, client: str, now: float | None = None) -> bool:
        now = now if now is not None else time.monotonic()
        self._trim(self._all, now)
        q = self._fails.get(client)
        if q is not None:
            self._trim(q, now)
            if not q:
                self._fails.pop(client, None)
                q = None
        return len(self._all) >= self.overall or (q is not None and len(q) >= self.per_client)

    def failure(self, client: str, now: float | None = None) -> None:
        now = now if now is not None else time.monotonic()
        self._fails.setdefault(client, deque()).append(now)
        self._all.append(now)

    def success(self, client: str) -> None:
        self._fails.pop(client, None)


_TRUSTED_PROXIES = frozenset({"127.0.0.1", "::1", "localhost"})


def client_ip(request) -> str:
    """Peer address; behind a local reverse proxy, the forwarded client address instead
    (Cloudflare's CF-Connecting-IP, then nginx's X-Real-IP, then X-Forwarded-For)."""
    peer = request.client.host if request.client else ""
    if peer in _TRUSTED_PROXIES:
        h = request.headers
        fwd = (h.get("cf-connecting-ip") or h.get("x-real-ip")
               or (h.get("x-forwarded-for") or "").split(",")[0]).strip()
        if fwd:
            return fwd
    return peer or "unknown"


def is_https(request) -> bool:
    if request.url.scheme in ("https", "wss"):
        return True
    peer = request.client.host if request.client else ""
    return peer in _TRUSTED_PROXIES and request.headers.get("x-forwarded-proto", "") == "https"


def origin_ok(headers) -> bool:
    """WebSocket CSWSH guard: a browser always sends Origin on WS upgrades; it must match the
    Host the request was sent to. (No Origin header = a non-browser client.)"""
    origin = headers.get("origin")
    if not origin:
        return True
    host = headers.get("host", "")
    bare = origin.split("://", 1)[-1].rstrip("/")
    return bare == host
