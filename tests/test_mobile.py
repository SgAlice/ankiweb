"""Fork: phone layout + PWA bits."""
from pathlib import Path

from fastapi.testclient import TestClient

from ankiweb.app import create_app
from ankiweb.config import Settings
from ankiweb.screens.page import render_page


def test_pages_have_viewport_and_pwa_meta():
    html = render_page("deckbrowser", "<div>x</div>")
    assert "width=device-width" in html and "viewport-fit=cover" in html
    assert "apple-mobile-web-app-capable" in html and "/manifest.webmanifest" in html
    assert "data-aw-ctx=\"deckbrowser\"" in html
    assert "@media (max-width:760px)" in html


def test_embedded_pages_keep_viewport_only():
    html = render_page("editor", "<div>x</div>", toolbar=False)
    assert "width=device-width" in html and "@media (max-width:760px)" not in html


def test_manifest_and_icons_public_with_password(tmp_path: Path):
    app = create_app(Settings(collection_path=tmp_path / "c.anki2", password="pw"))
    with TestClient(app) as c:
        m = c.get("/manifest.webmanifest")
        assert m.status_code == 200 and m.json()["display"] == "standalone"
        for icon in ("/apple-touch-icon.png", "/ankiweb-icon.png"):
            r = c.get(icon)
            assert r.status_code == 200 and r.content[:4] == b"\x89PNG"
        login = c.get("/login").text
        assert "apple-touch-icon" in login and "width=device-width" in login
        assert c.get("/deckbrowser", follow_redirects=False).status_code == 303


def test_reviewer_has_more_button_and_browser_sidebar_toggle(tmp_path: Path):
    with TestClient(create_app(Settings(collection_path=tmp_path / "c.anki2"))) as c:
        assert "id='rev-more'" in c.get("/reviewer").text
        assert "aw-side-toggle" in c.get("/browse").text
