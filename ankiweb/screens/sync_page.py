"""Fork: the /sync screen (status + full-sync conflict resolution) and the toolbar sync button.

Strings come from Anki's own translations (the same ones desktop shows, which also say
"AnkiWeb" when a custom sync server is configured)."""
from __future__ import annotations

import html
import json
import time

from ankiweb.i18n import tr


def _ago(ts: float | None) -> str:
    if not ts:
        return "—"
    secs = int(time.time() - ts)
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        return f"{secs // 60}min"
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))


def _md_bold(text: str) -> str:
    """sync_conflict_explanation2 is markdown (**bold**, '- ' bullets): render minimally."""
    out = []
    for line in html.escape(text).split("\n"):
        parts = line.split("**")
        line = "".join(f"<b>{p}</b>" if i % 2 else p for i, p in enumerate(parts))
        out.append(f"<li>{line[2:]}</li>" if line.startswith("- ") else f"<p>{line}</p>" if line else "")
    return "".join(out)


_STYLE = (
    "<style>"
    ".aw-sync{max-width:560px;margin:0 auto;padding:8px 16px;font-family:system-ui,sans-serif}"
    ".aw-sync table{border-collapse:collapse;margin:10px 0}"
    ".aw-sync td{padding:4px 12px 4px 0;vertical-align:top}"
    ".aw-sync .btns{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0}"
    ".aw-sync button{font-size:16px;padding:10px 16px;border-radius:8px;border:1px solid #888;"
    "background:#fff;cursor:pointer}"
    ".aw-sync button.primary{background:#2d7dd2;color:#fff;border-color:#2d7dd2}"
    ".aw-sync button.danger{border-color:#c0392b;color:#c0392b}"
    ".aw-sync .warn{background:#fff4e5;border:1px solid #f0b46c;border-radius:8px;padding:6px 14px}"
    ".aw-sync .err{color:#c0392b;white-space:pre-wrap}"
    "html.night-mode .aw-sync button{background:#3a3a3a;color:#e0e0e0}"
    "html.night-mode .aw-sync .warn{background:#3a2f1f;border-color:#8a6a3a}"
    "</style>"
)


def render_sync_html(mgr) -> str:
    if mgr is None or not mgr.enabled:
        return (_STYLE + "<div class='aw-sync'><h3>" + html.escape(tr.qt_misc_sync()) + "</h3>"
                "<p>Sync is not configured. Set <code>ANKIWEB_SYNC_ENDPOINT</code>, "
                "<code>ANKIWEB_SYNC_USER</code> and <code>ANKIWEB_SYNC_PASSWORD</code>.</p></div>")
    st = mgr.status()
    rows = [
        ("Server", html.escape(mgr.config.endpoint)),
        ("User", html.escape(mgr.config.username)),
        ("State", html.escape(st["state"])),
        ("Last sync", html.escape(_ago(st["last_sync"]))),
        ("Media", html.escape(st["media_state"])),
    ]
    table = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in rows)
    err = ""
    if st["last_error"]:
        err += f"<p class='err'>{html.escape(st['last_error'])}</p>"
    if st["media_error"]:
        err += f"<p class='err'>{html.escape(tr.sync_media_failed())} {html.escape(st['media_error'])}</p>"
    msg = f"<p class='warn'>{html.escape(st['server_message'])}</p>" if st["server_message"] else ""

    if st["pending"] == "conflict":
        conflict = (
            f"<div class='warn'>{_md_bold(tr.sync_conflict_explanation2())}</div>"
            "<div class='btns'>"
            f"<button class='danger' onclick=\"awFull('download')\">{html.escape(tr.sync_download_from_ankiweb())}</button>"
            f"<button class='danger' onclick=\"awFull('upload')\">{html.escape(tr.sync_upload_to_ankiweb())}</button>"
            f"<button onclick=\"awPost('/sync/recheck')\">{html.escape(tr.sync_cancel_button())} / retry</button>"
            "</div>"
        )
    elif st["pending"] == "upload":
        conflict = (
            f"<div class='warn'><p>{html.escape(tr.sync_confirm_empty_upload())}</p></div>"
            "<div class='btns'>"
            f"<button class='danger' onclick=\"awFull('upload')\">{html.escape(tr.sync_upload_to_ankiweb())}</button>"
            f"<button onclick=\"awPost('/sync/recheck')\">{html.escape(tr.sync_cancel_button())} / retry</button>"
            "</div>"
        )
    else:
        conflict = (
            "<div class='btns'>"
            f"<button class='primary' id='aw-sync-now' onclick=\"awPost('/sync')\">{html.escape(tr.qt_misc_sync())}</button>"
            "</div>"
        )

    labels = json.dumps({"syncing": tr.sync_syncing(), "sure": "This overwrites one side. Continue?"})
    script = (
        "<script>(function(){var L=" + labels + ";"
        "function busy(){document.querySelectorAll('.aw-sync button').forEach(function(b){b.disabled=true;});"
        "var s=document.getElementById('aw-sync-state');if(s)s.textContent=L.syncing;}"
        "window.awPost=function(url){busy();fetch(url,{method:'POST'}).then(function(){location.reload();},"
        "function(){location.reload();});};"
        "window.awFull=function(dir){if(!confirm(L.sure))return;awPost('/sync/full?direction='+dir);};"
        "})();</script>"
    )
    return (
        _STYLE + "<div class='aw-sync'>"
        f"<h3>{html.escape(tr.qt_misc_sync())} <small id='aw-sync-state'></small></h3>"
        f"<table>{table}</table>{err}{msg}{conflict}</div>{script}"
    )


def sync_button_html(extra_cls: str = "") -> str:
    """A sync button (icon + label + status dot). Several may exist on one page (nav, the phone
    "More" sheet, the deck list header); sync_script() drives all of them by class."""
    from ankiweb.screens.theme import icon
    label = html.escape(tr.qt_misc_sync())
    cls = f"aw-sync-btn {extra_cls}".strip()
    return (f"<a href='/sync' class='{cls}' onclick='return ankiwebSync(event)'>{icon('sync')}"
            f"<span class='aw-sync-l'>{label}</span><span class='aw-sync-dot'></span></a>")


def sync_script() -> str:
    """Tap = sync now (stays on the page, reloads if data was pulled). The dot shows the state:
    green ok, orange unsynced local changes, blue syncing, red error / needs a choice."""
    syncing = json.dumps(tr.sync_syncing())
    return (
        "<script>(function(){"
        "function all(sel){return Array.prototype.slice.call(document.querySelectorAll(sel));}"
        "function paint(s){if(!s)return;"
        "if(s.enabled===false){all('.aw-sync-btn').forEach(function(a){a.style.display='none';});return;}"
        "var c=s.state==='error'||s.state==='conflict'?'var(--aw-danger)':s.state==='syncing'?'var(--aw-accent)':"
        "s.local_changes?'#f59e0b':'var(--aw-review)';"
        "all('.aw-sync-dot').forEach(function(d){d.style.background=c;d.title=s.state+(s.last_error?': '+s.last_error:'');});"
        "all('.aw-sync-btn').forEach(function(a){a.classList.toggle('spinning',s.state==='syncing');});}"
        "window.ankiwebSync=function(ev){if(ev&&(ev.metaKey||ev.ctrlKey))return true;"
        "var labels=all('.aw-sync-l');var old=labels.map(function(l){return l.textContent;});"
        f"labels.forEach(function(l){{l.textContent={syncing};}});paint({{enabled:true,state:'syncing'}});"
        "function restore(){labels.forEach(function(l,i){l.textContent=old[i];});}"
        "fetch('/sync',{method:'POST'}).then(function(r){return r.json();}).then(function(s){"
        "restore();paint(s);"
        "if(s.state==='conflict'||s.state==='error'){location.href='/sync';return;}"
        "if(s.changed)location.reload();}).catch(function(){restore();"
        "paint({enabled:true,state:'error'});});return false;};"
        "fetch('/sync/status').then(function(r){return r.json();}).then(paint).catch(function(){});"
        "})();</script>"
    )
