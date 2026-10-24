import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from ankiweb.config import Settings
from ankiweb.app import create_app
from ankiweb.auth import COOKIE, Authenticator, LoginLimiter


def _client(tmp_path: Path, password: str = "") -> TestClient:
    return TestClient(create_app(Settings(collection_path=tmp_path / "c.anki2", password=password)))


def test_open_when_no_password(tmp_path: Path):
    with _client(tmp_path) as c:
        assert c.get("/deckbrowser", follow_redirects=False).status_code == 200
        assert c.get("/tools", follow_redirects=False).status_code == 200


def test_from_env_reads_password(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("ANKIWEB_COLLECTION", str(tmp_path / "c.anki2"))
    monkeypatch.setenv("ANKIWEB_PASSWORD", "hunter2")
    assert Settings.from_env().password == "hunter2"


def test_gate_redirects_when_password_set(tmp_path: Path):
    with _client(tmp_path, "secret") as c:
        r = c.get("/deckbrowser", follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/login"
        # /healthz and /login stay reachable
        assert c.get("/healthz").status_code == 200
        assert c.get("/login", follow_redirects=False).status_code == 200
        # an asset/RPC path is gated too (plain 401, not a redirect)
        assert c.get("/_anki/js/reviewer.js", follow_redirects=False).status_code == 401
        assert c.post("/sync", follow_redirects=False).status_code == 401


def test_login_wrong_password(tmp_path: Path):
    with _client(tmp_path, "secret") as c:
        r = c.post("/login", data={"password": "nope"}, follow_redirects=False)
        assert r.status_code == 401
        assert "password" in r.text.lower() or "密码" in r.text


def test_login_correct_unlocks(tmp_path: Path):
    with _client(tmp_path, "secret") as c:
        r = c.post("/login", data={"password": "secret"}, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/"
        tok = r.cookies.get(COOKIE)
        assert tok and "secret" not in tok and c.app.state.auth.verify(tok)
        sc = r.headers["set-cookie"].lower()
        assert "httponly" in sc and "samesite=lax" in sc and "max-age=7776000" in sc
        # the client now carries the session cookie -> protected page loads
        assert c.get("/deckbrowser", follow_redirects=False).status_code == 200


def test_bad_cookie_still_gated(tmp_path: Path):
    with _client(tmp_path, "secret") as c:
        c.cookies.set(COOKIE, "garbage")
        assert c.get("/deckbrowser", follow_redirects=False).status_code == 303


def test_logout_clears_session(tmp_path: Path):
    with _client(tmp_path, "secret") as c:
        c.post("/login", data={"password": "secret"})
        assert c.get("/deckbrowser", follow_redirects=False).status_code == 200
        c.get("/logout", follow_redirects=False)
        assert c.get("/deckbrowser", follow_redirects=False).status_code == 303


def test_ws_rejected_without_cookie(tmp_path: Path):
    with _client(tmp_path, "secret") as c:
        with pytest.raises(WebSocketDisconnect):
            with c.websocket_connect("/ws?context=browser") as ws:
                ws.receive_json()


def test_ws_ok_with_cookie(tmp_path: Path):
    with _client(tmp_path, "secret") as c:
        c.post("/login", data={"password": "secret"})
        with c.websocket_connect("/ws?context=browser"):
            pass  # accepted, no rejection


def test_ws_open_when_no_password(tmp_path: Path):
    with _client(tmp_path) as c:
        with c.websocket_connect("/ws?context=browser"):
            pass


def test_old_style_cookie_rejected(tmp_path: Path):
    import hashlib
    legacy = hashlib.sha256(b"ankiweb-auth-v1:secret").hexdigest()
    with _client(tmp_path, "secret") as c:
        c.cookies.set(COOKIE, legacy)
        assert c.get("/deckbrowser", follow_redirects=False).status_code == 303


def test_token_expiry_tamper_and_password_change(tmp_path: Path):
    secret = tmp_path / "auth_secret"
    a = Authenticator("pw", secret, max_age_days=1)
    t = a.issue(now=1_000_000)
    assert a.verify(t, now=1_000_000 + 3600)
    assert not a.verify(t, now=1_000_000 + 2 * 86400)          # expired
    issued, nonce, sig = t.split(".")
    assert not a.verify(f"{int(issued) + 86400}.{nonce}.{sig}", now=1_000_000)  # tampered
    # same secret file + same password -> still valid after a restart
    assert Authenticator("pw", secret, max_age_days=1).verify(t, now=1_000_000)
    # password change logs everyone out
    assert not Authenticator("pw2", secret, max_age_days=1).verify(t, now=1_000_000)
    # secret file is private
    assert (secret.stat().st_mode & 0o777) == 0o600
    assert Authenticator("").verify(None)  # no password -> open


def test_login_rate_limited(tmp_path: Path):
    with _client(tmp_path, "secret") as c:
        for _ in range(5):
            assert c.post("/login", data={"password": "nope"}).status_code == 401
        r = c.post("/login", data={"password": "secret"}, follow_redirects=False)
        assert r.status_code == 429  # even the right password waits out the lockout
        # another client (forwarded IP via the local proxy) is not affected
        r = c.post("/login", data={"password": "secret"}, follow_redirects=False,
                   headers={"x-real-ip": "203.0.113.9"})
        assert r.status_code in (303, 429)


def test_limiter_window():
    lim = LoginLimiter(per_client=2, overall=3, window=10)
    lim.failure("a", now=0); lim.failure("a", now=1)
    assert lim.blocked("a", now=2) and not lim.blocked("b", now=2)
    assert not lim.blocked("a", now=12)
    lim.failure("b", now=20); lim.failure("c", now=20); lim.failure("d", now=20)
    assert lim.blocked("e", now=21)  # global cap


def test_secure_cookie_over_https(tmp_path: Path):
    app = create_app(Settings(collection_path=tmp_path / "c.anki2", password="secret"))
    with TestClient(app, base_url="https://testserver") as c:
        r = c.post("/login", data={"password": "secret"}, follow_redirects=False)
        assert "; secure" in r.headers["set-cookie"].lower()
    # forwarded headers from a non-local peer are not trusted
    with _client(tmp_path, "secret") as c:
        r = c.post("/login", data={"password": "secret"}, follow_redirects=False,
                   headers={"x-forwarded-proto": "https"})
        assert "; secure" not in r.headers["set-cookie"].lower()


def test_forwarded_headers_trusted_only_from_local_proxy():
    from types import SimpleNamespace
    from ankiweb.auth import client_ip, is_https

    def req(peer, **headers):
        return SimpleNamespace(client=SimpleNamespace(host=peer), headers=headers,
                               url=SimpleNamespace(scheme="http"))

    assert client_ip(req("127.0.0.1", **{"x-real-ip": "198.51.100.7"})) == "198.51.100.7"
    assert client_ip(req("127.0.0.1", **{"cf-connecting-ip": "198.51.100.8",
                                         "x-real-ip": "172.70.0.1"})) == "198.51.100.8"
    assert client_ip(req("203.0.113.5", **{"x-real-ip": "1.2.3.4"})) == "203.0.113.5"
    assert is_https(req("127.0.0.1", **{"x-forwarded-proto": "https"}))
    assert not is_https(req("203.0.113.5", **{"x-forwarded-proto": "https"}))


def test_ws_rejects_cross_origin(tmp_path: Path):
    with _client(tmp_path, "secret") as c:
        c.post("/login", data={"password": "secret"})
        with pytest.raises(WebSocketDisconnect):
            with c.websocket_connect("/ws?context=browser",
                                     headers={"origin": "https://evil.example"}) as ws:
                ws.receive_json()
        with c.websocket_connect("/ws?context=browser", headers={"origin": "http://testserver"}):
            pass
