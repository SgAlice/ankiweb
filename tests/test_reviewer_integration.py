import threading
import time
import pytest


@pytest.fixture(autouse=True)
def _all_four_buttons(monkeypatch):
    # these flows rate Easy; the fork shows only Again/Good unless configured
    monkeypatch.setenv("ANKIWEB_ANSWER_BUTTONS", "1,2,3,4")
import uvicorn
from pathlib import Path
from anki.collection import Collection
from ankiweb.config import Settings
from ankiweb.app import create_app

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright


@pytest.fixture
def live_server(tmp_path: Path):
    col_path = tmp_path / "collection.anki2"
    col = Collection(str(col_path))
    try:
        n = col.new_note(col.models.by_name("Basic")); n["Front"] = "CapitalFrance"; n["Back"] = "Paris"
        col.add_note(n, col.decks.id("Default"))
        col.decks.set_current(col.decks.id("Default"))
    finally:
        col.close()
    settings = Settings(collection_path=col_path, port=8125)
    server = uvicorn.Server(uvicorn.Config(create_app(settings), host="127.0.0.1",
                                           port=8125, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True); t.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("server did not start")
        time.sleep(0.05)
    yield "http://127.0.0.1:8125"
    server.should_exit = True; t.join(timeout=5)


def test_study_one_card(live_server):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.on("pageerror", lambda e: print("PAGEERROR:", e))
        page.goto(f"{live_server}/reviewer")
        # real reviewer.js renders the question into #qa
        page.wait_for_function("document.getElementById('qa').textContent.includes('CapitalFrance')",
                               timeout=6000)
        # Show Answer
        page.click("#ansbut")
        page.wait_for_function("document.getElementById('qa').textContent.includes('Paris')",
                               timeout=6000)
        # four ease buttons appear with interval labels
        page.wait_for_selector(".ease[data-ease='4']")
        assert page.locator(".ease").count() == 4
        # rate Easy (ease4) → the lone new card graduates to review (multi-day) →
        # today's queue empties → reviewer navigates to /overview (Congrats).
        # (Good/ease3 would leave the card in the learning queue, re-fetched as the
        # same card → it would never finish.)
        page.click(".ease[data-ease='4']")
        page.wait_for_url("**/overview", timeout=6000)
        assert "Congratulations" in page.inner_text("body")
        browser.close()


@pytest.fixture
def live_server_audio(tmp_path: Path):
    import os
    col_path = tmp_path / "audio.anki2"
    col = Collection(str(col_path))
    try:
        m = col.models.new("AudioM")
        col.models.add_field(m, col.models.new_field("Front"))
        t = col.models.new_template("C"); t["qfmt"] = "{{Front}} [sound:hello.mp3]"; t["afmt"] = "{{Front}}"
        col.models.add_template(m, t); col.models.add_dict(m)
        did = col.decks.id("Default")
        n = col.new_note(col.models.by_name("AudioM")); n["Front"] = "Q"
        col.add_note(n, did); col.decks.set_current(did)
        with open(os.path.join(col.media.dir(), "hello.mp3"), "wb") as f:
            f.write(b"\x00")
    finally:
        col.close()
    settings = Settings(collection_path=col_path, port=8126)
    server = uvicorn.Server(uvicorn.Config(create_app(settings), host="127.0.0.1",
                                           port=8126, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True); t.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("server did not start")
        time.sleep(0.05)
    yield "http://127.0.0.1:8126"
    server.should_exit = True; t.join(timeout=5)


def test_audio_autoplays_on_question(live_server_audio):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.add_init_script(
            "window.__played=[];"
            "HTMLMediaElement.prototype.play=function(){window.__played.push(this.src);"
            "return Promise.resolve();};")
        page.goto(f"{live_server_audio}/reviewer")
        page.wait_for_function("document.getElementById('qa').textContent.length>0", timeout=6000)
        page.wait_for_function("window.__played.length>0", timeout=6000)
        # fork: played from the in-memory cache (a Blob URL), downloaded once from /hello.mp3
        assert any(s.startswith("blob:") for s in page.evaluate("window.__played"))
        assert page.evaluate("window.__ankiwebAudio.cache.has('hello.mp3')")
        browser.close()


def test_shortcut_space_shows_answer(live_server):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"{live_server}/reviewer")
        page.wait_for_function(
            "document.getElementById('qa').textContent.includes('CapitalFrance')", timeout=6000)
        page.keyboard.press("Space")      # question side -> show answer (ankiwebShowAnswer)
        page.wait_for_function(
            "document.getElementById('qa').textContent.includes('Paris')", timeout=6000)
        page.wait_for_selector(".ease[data-ease='4']")   # the ease bar appeared
        browser.close()


@pytest.fixture
def live_server_prefetch(tmp_path: Path):
    """8 cards, each with its own question + answer audio (like a vocab deck)."""
    import os
    col_path = tmp_path / "prefetch.anki2"
    col = Collection(str(col_path))
    try:
        m = col.models.new("AudioP")
        for f in ("Front", "Back"):
            col.models.add_field(m, col.models.new_field(f))
        t = col.models.new_template("C")
        t["qfmt"] = "{{Front}} [sound:q_{{Front}}.mp3]"
        t["afmt"] = "{{Front}}<hr id=answer>{{Back}} [sound:a_{{Front}}.mp3]"
        col.models.add_template(m, t); col.models.add_dict(m)
        did = col.decks.id("Default")
        for i in range(8):
            n = col.new_note(col.models.by_name("AudioP")); n["Front"] = f"w{i}"; n["Back"] = f"b{i}"
            col.add_note(n, did)
            for side in ("q", "a"):
                with open(os.path.join(col.media.dir(), f"{side}_w{i}.mp3"), "wb") as fh:
                    fh.write(b"\x00" * 64)
        col.decks.set_current(did)
    finally:
        col.close()
    server = uvicorn.Server(uvicorn.Config(create_app(Settings(collection_path=col_path, port=8132)),
                                           host="127.0.0.1", port=8132, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True); t.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("server did not start")
        time.sleep(0.05)
    yield "http://127.0.0.1:8132"
    server.should_exit = True; t.join(timeout=5)


def test_audio_prefetch_next_five_cards(live_server_prefetch):
    """Fork: after the first question, the current answer audio + q/a audio of the next 5 cards
    are downloaded in the background; the next card then plays from the cache (no request)."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.add_init_script("window.__played=[];HTMLMediaElement.prototype.play=function(){"
                             "window.__played.push(this.src);return Promise.resolve();};")
        fetched = []
        page.on("request", lambda r: fetched.append(r.url.rsplit("/", 1)[-1])
                if r.url.endswith(".mp3") else None)
        page.goto(f"{live_server_prefetch}/reviewer")
        page.wait_for_function("window.__played.length>0", timeout=8000)
        word = "document.getElementById('qa').innerText.match(/w\\d/)[0]"
        first = page.evaluate(word)  # e.g. "w0"
        # 1 current question + 1 current answer + 5 cards x 2 = 12 files cached
        page.wait_for_function("window.__ankiwebAudio.cache.size>=12", timeout=8000)
        page.wait_for_timeout(300)
        cached = page.evaluate("Array.from(window.__ankiwebAudio.cache.keys())")
        assert f"a_{first}.mp3" in cached
        others = {c[2:-4] for c in cached if c.startswith("q_")} - {first}
        assert len(others) == 5, cached          # exactly the next five cards
        assert all(f"a_{w}.mp3" in cached for w in others)
        # every file was requested exactly once
        assert len(fetched) == len(set(fetched)) == 12, fetched
        # answer + rate: the next card's question audio comes from the cache, not the network
        page.evaluate("window.ankiwebShowAnswer()")
        page.wait_for_selector(".ease[data-ease='1']", timeout=8000)
        n_before = len(fetched)
        played_before = len(page.evaluate("window.__played"))
        page.click(".ease[data-ease='3']")
        page.wait_for_function(f"window.__played.length>{played_before + 1}", timeout=8000)
        page.wait_for_timeout(300)
        nxt = page.evaluate(word)
        assert nxt != first and f"q_{nxt}.mp3" in cached
        assert f"q_{nxt}.mp3" not in fetched[n_before:]
        browser.close()
