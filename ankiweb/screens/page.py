from __future__ import annotations
import json
from typing import Sequence

from ankiweb.i18n import tr
from ankiweb.screens.sync_page import sync_button_html, sync_script
from ankiweb.screens import theme
from ankiweb.screens import mobile

# Base dark theme for the server-rendered screens. bootstrap.js adds the
# `night-mode` class to <html> when the persisted preference (or #night hash) is set.
_NIGHT_CSS = (
    "<style>"
    "html.night-mode body{background:#2b2b2b;color:#e0e0e0;}"
    "html.night-mode a{color:#6cb6ff;}"
    "html.night-mode button,html.night-mode input,html.night-mode select,"
    "html.night-mode textarea{background:#3a3a3a;color:#e0e0e0;border-color:#555;}"
    "html.night-mode table,html.night-mode th,html.night-mode td{border-color:#555;}"
    "html.night-mode .zero-count{color:#888;}"
    "</style>"
)

# Fork: the nav bar and all screen styling live in screens/theme.py.
_WIDE = {"browser", "reviewer"}


def render_page(
    context: str,
    body: str,
    css_files: Sequence[str] = (),
    js_files: Sequence[str] = (),
    toolbar: bool = True,
) -> str:
    """Wrap a server-rendered fragment in a full shell HTML document.

    Sets window.__ankiwebContext BEFORE any script so the Bridge connects to
    /ws?context=<context>. Vendored js_files (served from /_anki/) load BEFORE
    the shell bootstrap.js, so globals they define (e.g. reviewer.js's
    window._showQuestion) exist when the page body's inline script runs.

    `toolbar` adds the always-present top toolbar (Decks/Add/Browse/Stats); pass
    False for embedded fragments like the editor iframe inside the Browser.
    """
    links = "".join(f'<link rel="stylesheet" href="/_anki/{c}">' for c in css_files)
    scripts = "".join(f'<script src="/_anki/{j}"></script>' for j in js_files)
    if toolbar:
        css = theme.CSS
        main_cls = "aw-main aw-wide-main" if context in _WIDE else "aw-main"
        page_body = (theme.nav_html(context, sync_button_html())
                     + f"<main class='{main_cls}'>{body}</main>" + sync_script())
    else:  # embedded fragment (editor iframe): Anki's own styling + the basic night colors
        css = _NIGHT_CSS
        page_body = body
    return (
        "<!doctype html>\n"
        f'<html{mobile.html_attrs(context)}><head><meta charset="utf-8">'
        f"{mobile.HEAD}"
        f"<script>window.__ankiwebContext={json.dumps(context)}</script>"
        f"{links}"
        f"{css}"
        f"{scripts}"
        '<script src="/shell/static/bootstrap.js"></script>'
        "</head>"
        f"<body>{page_body}</body></html>"
    )
