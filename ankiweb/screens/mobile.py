"""Fork: phone layout + "Add to Home Screen" (PWA) support for the server-rendered screens.

Upstream renders desktop-only pages with no viewport meta, so iOS Safari shows a zoomed-out
980px page. This adds the viewport/PWA head tags and one stylesheet. The rules apply only at
phone widths (<= 760px), so the desktop layout is unchanged. The reused SvelteKit pages (graphs,
deck options, ...) are already responsive and are left alone.

The page context goes on <html data-aw-ctx=...> rather than on <body>, because reviewer.js
overwrites body.className with the card's classes.
"""
from __future__ import annotations

import json

APP_NAME = "Anki"

HEAD = (
    "<meta name='viewport' content='width=device-width,initial-scale=1,viewport-fit=cover'>"
    "<meta name='apple-mobile-web-app-capable' content='yes'>"
    "<meta name='mobile-web-app-capable' content='yes'>"
    "<meta name='apple-mobile-web-app-status-bar-style' content='default'>"
    f"<meta name='apple-mobile-web-app-title' content='{APP_NAME}'>"
    "<meta name='theme-color' content='#f0f0f0' media='(prefers-color-scheme: light)'>"
    "<meta name='theme-color' content='#1e1e1e' media='(prefers-color-scheme: dark)'>"
    "<meta name='format-detection' content='telephone=no'>"
    "<link rel='manifest' href='/manifest.webmanifest'>"
    "<link rel='apple-touch-icon' href='/apple-touch-icon.png'>"
)

_SAFE_TOP = "env(safe-area-inset-top,0px)"
_SAFE_BOTTOM = "env(safe-area-inset-bottom,0px)"

CSS = (
    "<style>"
    "html{-webkit-text-size-adjust:100%}"
    # ---- reviewer answer bar: styled at every width (upstream had no styles for it) ----
    "#ankiweb-answer{text-align:center;margin:18px 0 8px}"
    "#ankiweb-answer .ansbut{font-size:16px;padding:8px 28px;border-radius:6px;cursor:pointer}"
    "#ankiweb-answer .ease-row{display:inline-flex;gap:8px}"
    "#ankiweb-answer .ease{display:flex;flex-direction:column;align-items:center;min-width:84px;"
    "padding:6px 10px;border-radius:6px;cursor:pointer;font-size:15px}"
    "#ankiweb-answer .ease-ivl{font-size:12px;opacity:.75}"
    "#ankiweb-answer .ease[data-ease='1'] .ease-label{color:#c0392b}"
    "#ankiweb-answer .ease[data-ease='2'] .ease-label{color:#7f8c8d}"
    "#ankiweb-answer .ease[data-ease='3'] .ease-label{color:#27ae60}"
    "#ankiweb-answer .ease[data-ease='4'] .ease-label{color:#2d7dd2}"
    "#rev-more{display:none}"
    "#rev-actions{text-align:center}"
    # ---- phones ----
    "@media (max-width:760px){"
    f"body{{padding-top:calc(54px + {_SAFE_TOP})!important;margin:0 10px}}"
    # toolbar: one swipeable row with bigger tap targets, sitting under the notch. Fixed height:
    # some vendored stylesheets (reviewer.css) restyle <button> and would stretch it.
    f"#ankiweb-toolbar{{height:calc(46px + {_SAFE_TOP})!important;box-sizing:border-box;"
    f"padding:{_SAFE_TOP} 4px 0!important;gap:0!important;overflow-x:auto;overflow-y:hidden;"
    "-webkit-overflow-scrolling:touch;scrollbar-width:none}"
    "#ankiweb-toolbar::-webkit-scrollbar{display:none}"
    "#ankiweb-toolbar>a{padding:12px 9px;font-size:16px;white-space:nowrap;flex:none}"
    "#ankiweb-toolbar .aw-wide{display:none!important}"
    "#ankiweb-toolbar .nm{flex:none;padding:0 10px!important;margin:0!important;height:40px;"
    "min-height:0!important;min-width:0!important;background:transparent!important;border:0!important}"
    # 16px inputs stop iOS from zooming in on focus
    "input,select,textarea{font-size:16px!important}"
    "button{min-height:36px;font-size:15px}"
    # deck list
    "table.decks{width:100%!important;max-width:none}"
    "table.decks th,table.decks td{padding:11px 4px!important;font-size:16px}"
    "table.decks td.decktd{white-space:normal;word-break:break-word;min-width:0!important;max-width:none!important}"
    "table.decks .count{min-width:0!important;width:3em;font-size:15px}"
    "table.decks th.count{font-size:12px;font-weight:normal;white-space:nowrap}"
    "table.decks a.deck{display:inline-block;padding:3px 0}"
    "table.decks .gears{width:22px;height:22px}"
    "#studiedToday{margin:16px 0;font-size:14px}"
    ".dyn-buttons{display:flex;flex-wrap:wrap;gap:8px;justify-content:center}"
    # add screen: its deck/notetype bar flows under the toolbar instead of being fixed
    "#add-chrome{position:static!important;height:auto!important;flex-wrap:wrap;margin:0 -10px 6px;"
    "padding:8px 10px!important}"
    "#add-chrome label{display:flex;flex-direction:column;font-size:12px;flex:1 1 40%}"
    "#add-chrome select{width:100%}"
    "#add-btn{font-size:17px!important;padding:8px 22px;border-radius:8px}"
    # deck overview
    ".overview-counts td{font-size:18px;padding:6px 12px!important}"
    "#study{font-size:20px;padding:12px 44px;border-radius:10px;margin:14px 0}"
    ".bottom-buttons{display:flex;flex-wrap:wrap;gap:8px;justify-content:center}"
    "#descbox{width:100%;box-sizing:border-box}"
    # reviewer: big answer buttons pinned to the bottom (thumb reach), actions behind a ⋯ button
    f"html[data-aw-ctx=reviewer] body{{padding-bottom:calc(96px + {_SAFE_BOTTOM})!important}}"
    "#ankiweb-answer{position:fixed;left:0;right:0;bottom:0;margin:0;z-index:1500;"
    f"padding:8px 8px calc(8px + {_SAFE_BOTTOM});background:rgba(244,244,244,.96);"
    "border-top:1px solid #ccc;-webkit-backdrop-filter:blur(8px);backdrop-filter:blur(8px)}"
    "#ankiweb-answer,#ankiweb-answer *{box-sizing:border-box}"
    "#ankiweb-answer .ansbut{width:100%;height:56px;font-size:19px;border-radius:12px;margin:0}"
    "#ankiweb-answer .ease-row{display:grid;grid-auto-flow:column;grid-auto-columns:1fr;gap:8px;width:100%}"
    "#ankiweb-answer .ease{min-width:0;width:100%;margin:0;height:60px;justify-content:center;border-radius:12px;"
    "font-size:17px;padding:4px}"
    "#ankiweb-answer .ease-ivl{font-size:13px}"
    f"#rev-more{{display:block;position:fixed;right:8px;top:calc(52px + {_SAFE_TOP});min-width:0;z-index:1600;"
    "width:40px;height:40px;border-radius:20px;border:1px solid #bbb;background:rgba(255,255,255,.9);"
    "font-size:20px;line-height:1;padding:0}"
    "#rev-actions{display:none}"
    f"#rev-actions.open{{display:flex;flex-wrap:wrap;gap:6px;position:fixed;left:8px;right:8px;"
    f"top:calc(98px + {_SAFE_TOP});z-index:1600;padding:10px;background:#fff;border:1px solid #bbb;"
    "border-radius:12px;box-shadow:0 6px 24px rgba(0,0,0,.2);max-height:60vh;overflow:auto}"
    "#rev-actions.open .rev-act{flex:1 1 40%;min-height:42px}"
    # browser: stack search / results / editor, sidebar hidden behind a toggle
    "#browser-top{display:flex;flex-wrap:wrap;gap:6px;align-items:center}"
    "#search{width:100%!important;box-sizing:border-box;padding:8px!important}"
    "#browser-actions{display:flex;gap:6px;overflow-x:auto;width:100%;padding-bottom:4px}"
    "#browser-actions button{flex:none}"
    "#browser-main{flex-direction:column}"
    "#sidebar{display:none;width:auto!important;border-right:0!important;"
    "border-bottom:1px solid #ccc;max-height:40vh;overflow:auto}"
    "#browser.aw-side #sidebar{display:block}"
    "#sidebar .side-item{padding:8px 4px!important;font-size:15px}"
    "#aw-side-toggle{display:inline-block!important}"
    "#results-wrap{width:100%;max-height:42vh!important}"
    "#results td,#results th{padding:9px 6px!important;font-size:14px}"
    "#detail{width:auto!important;border-left:0!important;border-top:1px solid #ccc;padding:6px 0!important}"
    ".editor-frame{height:70vh!important}"
    # generic forms (custom study, filtered deck, preferences, notify, sync ...)
    "table{max-width:100%}"
    "textarea{max-width:100%;box-sizing:border-box}"
    "}"
    # night mode for the new bits
    "html.night-mode #add-chrome{background:#1e1e1e!important;border-color:#444!important;color:#e0e0e0}"
    "html.night-mode #ankiweb-answer{background:rgba(30,30,30,.96);border-color:#444}"
    "html.night-mode #rev-more,html.night-mode #rev-actions.open{background:#2b2b2b;border-color:#555;color:#e0e0e0}"
    "</style>"
)


def html_attrs(context: str) -> str:
    return f" data-aw-ctx={json.dumps(context)}"


def manifest(night: bool = False) -> dict:
    return {
        "name": APP_NAME,
        "short_name": APP_NAME,
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": "#f0f0f0",
        "icons": [
            {"src": "/ankiweb-icon.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {"src": "/apple-touch-icon.png", "sizes": "180x180", "type": "image/png"},
        ],
    }
