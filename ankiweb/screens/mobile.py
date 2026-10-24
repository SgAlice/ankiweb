"""Fork: viewport + "Add to Home Screen" (PWA) head tags and the web manifest.

Upstream rendered desktop-only pages with no viewport meta (iOS showed a zoomed-out 980px page).
The phone layout itself lives in screens/theme.py.

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
