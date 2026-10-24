"""Fork: in night mode the card body carries nightMode/night_mode (like desktop Anki), so a note
type's own `.nightMode ...` CSS applies — on both sides, and it isn't wiped by reviewer.js."""
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from anki.collection import Collection

from ankiweb.app import create_app
from ankiweb.config import Settings

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright

PORT = 8131


@pytest.fixture
def live_server(tmp_path: Path):
    col_path = tmp_path / "night.anki2"
    col = Collection(str(col_path))
    m = col.models.by_name("Basic")
    m["css"] += ("\n.box{background-color:rgb(245,245,245)}"
                 "\n.nightMode .box{background-color:rgb(68,68,68)}")
    m["tmpls"][0]["qfmt"] = "<div class='box' id='qbox'>{{Front}}</div>"
    m["tmpls"][0]["afmt"] = "{{FrontSide}}<hr id=answer><div class='box' id='abox'>{{Back}}</div>"
    col.models.update_dict(m)
    n = col.new_note(m); n["Front"] = "Q"; n["Back"] = "A"
    col.add_note(n, col.decks.id("Default"))
    col.close()
    server = uvicorn.Server(uvicorn.Config(create_app(Settings(collection_path=col_path, port=PORT)),
                                           host="127.0.0.1", port=PORT, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True); t.start()
    deadline = time.monotonic() + 10
    while not server.started:
        assert time.monotonic() < deadline, "server did not start"
        time.sleep(0.05)
    yield f"http://127.0.0.1:{PORT}"
    server.should_exit = True; t.join(timeout=5)


def _bg(page, sel):
    return page.evaluate(f"getComputedStyle(document.querySelector('{sel}')).backgroundColor")


@pytest.mark.parametrize("night", [True, False])
def test_card_night_classes(live_server, night):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(color_scheme="light")
        ctx.add_init_script(f"localStorage.setItem('ankiweb-night','{1 if night else 0}')")
        page = ctx.new_page()
        page.goto(f"{live_server}/reviewer")
        page.wait_for_selector("#qbox", timeout=8000)
        page.wait_for_timeout(300)  # reviewer.js sets body.className after rendering
        want = "rgb(68, 68, 68)" if night else "rgb(245, 245, 245)"
        assert ("nightMode" in page.evaluate("document.body.className")) is night
        assert _bg(page, "#qbox") == want
        page.evaluate("window.ankiwebShowAnswer()")
        page.wait_for_selector("#abox", timeout=8000)
        page.wait_for_timeout(300)
        assert _bg(page, "#abox") == want
        assert ("nightMode" in page.evaluate("document.body.className")) is night
        browser.close()
