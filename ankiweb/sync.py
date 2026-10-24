"""Sync the web collection with an Anki sync server (self-hosted `anki.syncserver` or AnkiWeb).

Fork addition (not in upstream ankiweb). The web app is just one more sync client, exactly like
desktop Anki: it keeps its own collection and merges with the server through Anki's own sync
code (pylib `Collection.sync_collection` / `full_upload_or_download` / `sync_media`). The flow
mirrors aqt/sync.py:

- normal sync -> done (NO_CHANGES after the call means the incremental sync succeeded)
- FULL_DOWNLOAD (local collection empty, e.g. first run) -> download automatically
- FULL_UPLOAD (server empty, local has data) / FULL_SYNC (schema conflict) -> stop and ask the
  user on /sync which side wins; never overwrite either side silently
- media sync runs afterwards on the aux pool (the Rust backend syncs media on its own DB handle,
  like aqt's `uses_collection=False`), so a long first media download doesn't block reviewing

Configured from env (all optional; without an endpoint + user sync is disabled):
  ANKIWEB_SYNC_ENDPOINT   e.g. http://127.0.0.1:8090/  (same URL you'd type into desktop Anki)
  ANKIWEB_SYNC_USER / ANKIWEB_SYNC_PASSWORD
  ANKIWEB_SYNC_MEDIA      1 (default) / 0
  ANKIWEB_SYNC_INTERVAL   seconds between background syncs, default 600, 0 = off
  ANKIWEB_SYNC_DEBOUNCE   seconds after the last local change before an auto sync, default 60
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from anki.errors import SyncError, SyncErrorKind
from anki.sync import SyncOutput

log = logging.getLogger("ankiweb.sync")


@dataclass(frozen=True)
class SyncConfig:
    endpoint: str = ""
    username: str = ""
    password: str = field(default="", repr=False)
    media: bool = True
    interval: int = 600
    debounce: int = 60

    @property
    def enabled(self) -> bool:
        return bool(self.endpoint and self.username)

    @classmethod
    def from_env(cls) -> "SyncConfig":
        def _int(name: str, default: int) -> int:
            try:
                return int(os.environ.get(name, default))
            except ValueError:
                return default

        return cls(
            endpoint=os.environ.get("ANKIWEB_SYNC_ENDPOINT", "").strip(),
            username=os.environ.get("ANKIWEB_SYNC_USER", "").strip(),
            password=os.environ.get("ANKIWEB_SYNC_PASSWORD", ""),
            media=os.environ.get("ANKIWEB_SYNC_MEDIA", "1").strip().lower() not in ("0", "false", "no"),
            interval=_int("ANKIWEB_SYNC_INTERVAL", 600),
            debounce=_int("ANKIWEB_SYNC_DEBOUNCE", 60),
        )


# What a pulled sync may have touched: every page reloads / re-queries (bootstrap.ts listener).
_ALL_CHANGED = {"study_queues": True, "deck": True, "card": True, "note": True,
                "notetype": True, "deck_config": True, "tag": True, "browser_table": True,
                "note_text": True, "mtime": True}

# SyncOutput.required values (anki/sync.proto ChangesRequired)
NO_CHANGES = SyncOutput.NO_CHANGES
FULL_SYNC = SyncOutput.FULL_SYNC
FULL_DOWNLOAD = SyncOutput.FULL_DOWNLOAD
FULL_UPLOAD = SyncOutput.FULL_UPLOAD


# Cheap content fingerprint to tell whether a normal sync pulled anything. (col.mod is no use:
# every sync that does work bumps it on both sides.) Sums of per-row mtimes change when any row
# is added, edited or removed.
_FINGERPRINT_SQL = (
    "select (select total(mod) from cards), (select count() from cards),"
    " (select total(mod) from notes), (select count() from notes),"
    " (select count() from revlog), (select max(id) from revlog),"
    " (select total(mtime_secs) from decks), (select count() from decks),"
    " (select total(mtime_secs) from notetypes), (select total(mtime_secs) from deck_config)"
)


def _fingerprint(col) -> tuple:
    return tuple(col.db.first(_FINGERPRINT_SQL) or ())


class SyncManager:
    """Owns sync auth + state for the single collection. All collection work goes through the
    CollectionService worker, so a sync never races a review answer or an edit."""

    def __init__(self, service, config: SyncConfig, hub=None, backup_dir: Path | None = None) -> None:
        self.service = service
        self.config = config
        self.hub = hub
        self.backup_dir = backup_dir or (service.settings.collection_path.parent / "backups")
        self._auth = None
        self._lock = asyncio.Lock()
        self._tasks: set[asyncio.Task] = set()
        self._debounce_task: asyncio.Task | None = None
        self._media_task: asyncio.Task | None = None
        # --- public state (rendered on /sync and the toolbar) ---
        self.state = "idle" if config.enabled else "disabled"  # idle|syncing|conflict|error|disabled
        self.last_sync: float | None = None
        self.last_error: str = ""
        self.pending: int | None = None   # FULL_SYNC / FULL_UPLOAD awaiting a user choice
        self.server_media_usn: int | None = None
        self.server_message: str = ""
        self.media_state = "idle"         # idle|syncing|error
        self.media_error: str = ""
        self.local_changes = False

    # ------------------------------------------------------------------ helpers
    @property
    def enabled(self) -> bool:
        return self.config.enabled

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "state": self.state,
            "last_sync": self.last_sync,
            "last_error": self.last_error,
            "pending": {FULL_SYNC: "conflict", FULL_UPLOAD: "upload"}.get(self.pending, None),
            "server_message": self.server_message,
            "media_state": self.media_state,
            "media_error": self.media_error,
            "local_changes": self.local_changes,
        }

    def _spawn(self, coro) -> asyncio.Task:
        t = asyncio.get_running_loop().create_task(coro)
        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)
        return t

    async def _login(self):
        if self._auth is None:
            cfg = self.config
            self._auth = await self.service.run(
                lambda col: col.sync_login(cfg.username, cfg.password, cfg.endpoint))
        return self._auth

    def _fail(self, err: Exception) -> None:
        if isinstance(err, SyncError) and err.kind is SyncErrorKind.AUTH:
            self._auth = None  # bad/expired credentials: re-login next time
        self.state = "error"
        self.last_error = str(err) or err.__class__.__name__
        log.warning("sync failed: %s", self.last_error)

    async def _notify_clients(self) -> None:
        """Tell every open page the collection changed underneath it."""
        if self.hub is None:
            return
        try:
            await self.hub.broadcast_opchanges(_ALL_CHANGED, "sync")
        except Exception:  # a dead socket must not fail the sync
            log.exception("broadcast after sync failed")

    # ------------------------------------------------------------------ normal sync
    async def sync(self, reason: str = "manual") -> dict[str, Any]:
        """Incremental sync. Returns status() plus `changed` (local data was modified)."""
        if not self.enabled:
            return {**self.status(), "changed": False}
        if self._lock.locked():  # another sync is running: just report it
            async with self._lock:
                pass
            return {**self.status(), "changed": False}
        async with self._lock:
            if self.pending is not None:  # unresolved full-sync choice: don't retry silently
                return {**self.status(), "changed": False}
            self.state = "syncing"
            log.info("sync start (%s)", reason)
            try:
                auth = await self._login()

                def _do(col):
                    before = _fingerprint(col)
                    try:
                        out = col.sync_collection(auth, sync_media=False)
                    finally:
                        col._load_scheduler()
                    return out, _fingerprint(col) != before

                out, changed = await self.service.run(_do)
            except Exception as err:
                self._fail(err)
                return {**self.status(), "changed": False}

            if out.new_endpoint:
                auth.endpoint = out.new_endpoint
            self.server_message = out.server_message or ""
            self.server_media_usn = out.server_media_usn if self.config.media else None
            self.local_changes = False

            if out.required == NO_CHANGES:
                self.state = "idle"
                self.last_error = ""
                self.last_sync = time.time()
                if changed:
                    await self._notify_clients()
                self._start_media()
                return {**self.status(), "changed": changed}

            if out.required == FULL_DOWNLOAD:
                # local collection is empty (first run): nothing local to lose
                return await self._full(upload=False, locked=True)

            # FULL_UPLOAD or FULL_SYNC: the user must decide which side wins
            self.pending = out.required
            self.state = "conflict"
            return {**self.status(), "changed": False}

    # ------------------------------------------------------------------ full sync
    async def full_sync(self, upload: bool) -> dict[str, Any]:
        """User-confirmed one-way sync (from /sync). upload=True replaces the server copy."""
        if not self.enabled:
            return {**self.status(), "changed": False}
        async with self._lock:
            return await self._full(upload=upload, locked=True)

    async def recheck(self) -> dict[str, Any]:
        """Drop a pending full-sync choice and try a normal sync again (e.g. after the
        conflict was resolved from another device)."""
        async with self._lock:
            self.pending = None
            self.state = "idle"
        return await self.sync("recheck")

    async def _full(self, upload: bool, locked: bool) -> dict[str, Any]:
        assert locked and self._lock.locked()
        self.state = "syncing"
        log.info("full sync start (%s)", "upload" if upload else "download")
        try:
            auth = await self._login()
            server_usn = self.server_media_usn if self.config.media else None
            backup_dir = self.backup_dir
            backup_dir.mkdir(parents=True, exist_ok=True)

            def _do(col):
                if not upload:
                    # same safety net as desktop: back up before replacing local data
                    col.create_backup(backup_folder=str(backup_dir), force=True,
                                      wait_for_completion=True)
                col.close_for_full_sync()
                try:
                    col.full_upload_or_download(auth=auth, server_usn=server_usn, upload=upload)
                finally:
                    col.reopen(after_full_sync=True)
                    col._load_scheduler()

            await self.service.run(_do)
        except Exception as err:
            self._fail(err)
            return {**self.status(), "changed": False}
        self.pending = None
        self.state = "idle"
        self.last_error = ""
        self.last_sync = time.time()
        self.local_changes = False
        await self._notify_clients()
        self._start_media()
        return {**self.status(), "changed": not upload}

    # ------------------------------------------------------------------ media
    def _start_media(self) -> None:
        if not self.config.media or self._auth is None:
            return
        if self._media_task and not self._media_task.done():
            return
        self._media_task = self._spawn(self._media())

    async def _media(self) -> None:
        auth = self._auth
        self.media_state = "syncing"
        try:
            # sync_media spawns a backend thread and returns; poll its status like aqt does
            # (media_sync_status raises if that thread failed)
            await self.service.run(lambda col: col.sync_media(auth))
            while True:
                st = await self.service.run_concurrent(lambda col: col.media_sync_status())
                if not st.active:
                    break
                await asyncio.sleep(0.5)
            self.media_state = "idle"
            self.media_error = ""
        except Exception as err:
            self.media_state = "error"
            self.media_error = str(err) or err.__class__.__name__
            log.warning("media sync failed: %s", self.media_error)

    # ------------------------------------------------------------------ triggers
    def note_local_change(self) -> None:
        """Called after every mutating op: sync `debounce` seconds after the last change."""
        if not self.enabled:
            return
        self.local_changes = True
        if self.config.debounce <= 0:
            return
        if self._debounce_task and not self._debounce_task.done():
            self._debounce_task.cancel()
        self._debounce_task = self._spawn(self._debounced())

    async def _debounced(self) -> None:
        try:
            await asyncio.sleep(self.config.debounce)
        except asyncio.CancelledError:
            return
        await self.sync("after changes")

    async def sync_if_stale(self, max_age: float, timeout: float = 15.0) -> None:
        """Before rendering the home screen: pull if the last sync is older than max_age.
        Bounded by `timeout` so a dead server never blocks the UI for long."""
        if not self.enabled or self.state in ("syncing", "conflict"):
            return
        if self.last_sync is not None and time.time() - self.last_sync < max_age:
            return
        task = self._spawn(self.sync("open"))
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout)
        except asyncio.TimeoutError:
            pass

    async def run_periodic(self) -> None:
        """Background loop: initial sync at startup, then every `interval` seconds."""
        if not self.enabled:
            return
        await self.sync("startup")
        if self.config.interval <= 0:
            return
        while True:
            await asyncio.sleep(self.config.interval)
            await self.sync("periodic")

    async def close(self) -> None:
        for t in list(self._tasks):
            t.cancel()
        for t in list(self._tasks):
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
        if self._media_task and not self._media_task.done():
            try:
                await self.service.run_concurrent(lambda col: col.abort_media_sync())
            except Exception:
                pass
