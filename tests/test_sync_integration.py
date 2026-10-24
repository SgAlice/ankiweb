"""Fork: end-to-end sync against a real `python -m anki.syncserver`.

A plain pylib Collection plays "desktop Anki"; the web app is the second client."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest
from anki.collection import Collection
from fastapi.testclient import TestClient

from ankiweb.app import create_app
from ankiweb.config import Settings
from ankiweb.sync import SyncConfig

USER, PASSWORD = "tester", "secret"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def sync_server(tmp_path: Path):
    port = _free_port()
    env = {**os.environ, "SYNC_USER1": f"{USER}:{PASSWORD}", "SYNC_BASE": str(tmp_path / "server"),
           "SYNC_HOST": "127.0.0.1", "SYNC_PORT": str(port)}
    proc = subprocess.Popen([sys.executable, "-m", "anki.syncserver"], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.monotonic() + 20
    while True:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            if time.monotonic() > deadline or proc.poll() is not None:
                proc.kill()
                raise RuntimeError("sync server did not start")
            time.sleep(0.1)
    yield f"http://127.0.0.1:{port}/"
    proc.terminate()
    proc.wait(timeout=10)


class Desktop:
    """Minimal stand-in for desktop Anki: one collection + its sync auth."""

    def __init__(self, path: Path, endpoint: str):
        self.col = Collection(str(path))
        self.auth = self.col.sync_login(USER, PASSWORD, endpoint)
        self.server_media_usn = 0

    def sync(self, allow_full_upload: bool = True):
        out = self.col.sync_collection(self.auth, sync_media=False)
        self.server_media_usn = out.server_media_usn
        if out.required == out.FULL_UPLOAD and allow_full_upload:
            self.col.close_for_full_sync()
            self.col.full_upload_or_download(auth=self.auth, server_usn=out.server_media_usn, upload=True)
            self.col.reopen(after_full_sync=True)
        return out

    def sync_media(self):
        self.col.sync_media(self.auth)
        while self.col.media_sync_status().active:
            time.sleep(0.1)

    def add_note(self, front: str, back: str = "b") -> int:
        n = self.col.new_note(self.col.models.by_name("Basic"))
        n["Front"], n["Back"] = front, back
        self.col.add_note(n, self.col.decks.id("Default"))
        return n.id


def _web(tmp_path: Path, endpoint: str, **cfg) -> TestClient:
    sync = SyncConfig(endpoint=endpoint, username=USER, password=PASSWORD, media=True,
                      interval=0, debounce=0, **cfg)
    settings = Settings(collection_path=tmp_path / "web" / "collection.anki2", sync=sync)
    return TestClient(create_app(settings))


def _web_fronts(client) -> set[str]:
    svc = client.app.state.service
    return set(client.portal.call(
        svc.run, lambda col: [col.get_note(n)["Front"] for n in col.find_notes("")]))


def _wait_idle(client, timeout=20):
    mgr = client.app.state.service.sync
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        st = client.get("/sync/status").json()
        if st["state"] not in ("syncing",) and st["media_state"] != "syncing" and mgr.last_sync:
            return st
        time.sleep(0.1)
    raise AssertionError(f"sync did not settle: {client.get('/sync/status').json()}")


def test_first_run_downloads_then_merges_both_ways(tmp_path, sync_server):
    desk = Desktop(tmp_path / "desk.anki2", sync_server)
    desk.add_note("from-desktop-1")
    desk.col.media.write_data("pic.png", b"\x89PNG fake")
    desk.sync()  # server empty -> desktop does the initial full upload
    desk.sync_media()

    with _web(tmp_path, sync_server) as client:
        st = _wait_idle(client)  # startup sync: empty local -> automatic full download
        assert st["state"] == "idle", st
        assert _web_fronts(client) == {"from-desktop-1"}
        # media came down too (startup kicks off media sync)
        media_dir = Path(client.portal.call(client.app.state.service.run, lambda col: col.media.dir()))
        deadline = time.monotonic() + 10
        while not (media_dir / "pic.png").exists() and time.monotonic() < deadline:
            time.sleep(0.1)
        assert (media_dir / "pic.png").read_bytes() == b"\x89PNG fake"

        # desktop adds a note -> web pulls it on a manual sync, and reports changed
        desk.add_note("from-desktop-2")
        desk.sync()
        r = client.post("/sync").json()
        assert r["state"] == "idle" and r["changed"] is True
        assert _web_fronts(client) == {"from-desktop-1", "from-desktop-2"}

        # web adds a note -> desktop pulls it
        svc = client.app.state.service

        def add_web(col):
            n = col.new_note(col.models.by_name("Basic"))
            n["Front"], n["Back"] = "from-web", "b"
            return col.add_note(n, col.decks.id("Default"))

        client.portal.call(svc.run_op, add_web)
        assert client.post("/sync").json()["state"] == "idle"
        desk.sync()
        fronts = {desk.col.get_note(n)["Front"] for n in desk.col.find_notes("")}
        assert fronts == {"from-desktop-1", "from-desktop-2", "from-web"}

        # a sync with nothing new reports changed=False
        assert client.post("/sync").json()["changed"] is False
    desk.col.close()


def test_schema_conflict_requires_choice_then_download(tmp_path, sync_server):
    desk = Desktop(tmp_path / "desk.anki2", sync_server)
    desk.add_note("base")
    desk.sync()
    with _web(tmp_path, sync_server) as client:
        _wait_idle(client)
        # both sides make a schema change -> the server demands a one-way full sync
        svc = client.app.state.service

        def web_schema(col):
            m = col.models.by_name("Basic")
            col.models.add_field(m, col.models.new_field("WebField"))
            col.models.update_dict(m)

        client.portal.call(svc.run, web_schema)
        m = desk.col.models.by_name("Basic")
        desk.col.models.add_field(m, desk.col.models.new_field("DeskField"))
        desk.col.models.update_dict(m)
        desk.add_note("desk-after-schema")
        out = desk.sync(allow_full_upload=False)
        if out.required != out.NO_CHANGES:  # desktop's schema change forces a full upload
            desk.col.close_for_full_sync()
            desk.col.full_upload_or_download(auth=desk.auth, server_usn=out.server_media_usn, upload=True)
            desk.col.reopen(after_full_sync=True)

        r = client.post("/sync").json()
        assert r["state"] == "conflict" and r["pending"] == "conflict", r
        # page offers both choices
        page = client.get("/sync").text
        assert "awFull('download')" in page and "awFull('upload')" in page
        # a normal sync stays blocked until the user chooses
        assert client.post("/sync").json()["state"] == "conflict"

        r = client.post("/sync/full?direction=download").json()
        assert r["state"] == "idle" and r["changed"] is True, r
        assert _web_fronts(client) == {"base", "desk-after-schema"}
        fields = client.portal.call(
            svc.run, lambda col: [f["name"] for f in col.models.by_name("Basic")["flds"]])
        assert "DeskField" in fields and "WebField" not in fields
        # a backup was taken before the local copy was replaced
        assert list((tmp_path / "web" / "backups").glob("*.colpkg"))
        # and normal syncing resumes
        assert client.post("/sync").json()["state"] == "idle"
    desk.col.close()


def test_bad_password_reports_error(tmp_path, sync_server):
    sync = SyncConfig(endpoint=sync_server, username=USER, password="wrong", interval=0, debounce=0)
    settings = Settings(collection_path=tmp_path / "web" / "collection.anki2", sync=sync)
    with TestClient(create_app(settings)) as client:
        r = client.post("/sync").json()
        assert r["state"] == "error" and r["last_error"]
        assert "err" in client.get("/sync").text


def test_disabled_without_config(tmp_path):
    with TestClient(create_app(Settings(collection_path=tmp_path / "c.anki2"))) as client:
        assert client.get("/sync/status").json()["enabled"] is False
        assert client.post("/sync").json()["changed"] is False
        assert "not configured" in client.get("/sync").text


def test_local_change_triggers_debounced_sync_and_home_pulls(tmp_path, sync_server):
    desk = Desktop(tmp_path / "desk.anki2", sync_server)
    desk.add_note("seed")
    desk.sync()
    with _web(tmp_path, sync_server, ) as client:
        _wait_idle(client)
        mgr = client.app.state.service.sync
        object.__setattr__(mgr.config, "debounce", 1)  # frozen dataclass: test-only tweak
        svc = client.app.state.service

        def add_web(col):
            n = col.new_note(col.models.by_name("Basic"))
            n["Front"], n["Back"] = "auto", "b"
            return col.add_note(n, col.decks.id("Default"))

        client.portal.call(svc.run_op, add_web)
        assert client.get("/sync/status").json()["local_changes"] is True
        deadline = time.monotonic() + 10
        while client.get("/sync/status").json()["local_changes"] and time.monotonic() < deadline:
            time.sleep(0.1)
        desk.sync()
        assert {desk.col.get_note(n)["Front"] for n in desk.col.find_notes("")} == {"seed", "auto"}

        # opening the home screen pulls when the last sync is stale
        desk.add_note("pulled-on-open")
        desk.sync()
        mgr.last_sync = time.time() - 3600
        assert "Default" in client.get("/").text
        assert "pulled-on-open" in _web_fronts(client)
    desk.col.close()
