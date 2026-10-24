from __future__ import annotations
import html
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import HTMLResponse, PlainTextResponse, RedirectResponse

from ankiweb.config import Settings, host_allowed
from ankiweb.auth import (COOKIE, OPEN_PATHS, Authenticator, LoginLimiter, client_ip, is_https,
                          password_ok)


def _login_html(error: bool = False, blocked: bool = False) -> str:
    """Self-contained login page (no /_anki assets, so it works before authentication)."""
    err = ""
    if error:
        err = "<p class='err'>密码错误 / Wrong password</p>"
    if blocked:
        err = "<p class='err'>尝试次数过多，请稍后再试<br>Too many attempts, try again later</p>"
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        + mobile.HEAD +
        "<title>Anki</title><style>"
        ":root{--bg:#f4f5f7;--card:#fff;--text:#18191c;--muted:#6b7079;--border:#d3d6dc;--accent:#2f6fec}"
        "@media (prefers-color-scheme:dark){:root{--bg:#111214;--card:#1b1c1f;--text:#ececef;"
        "--muted:#9a9ea7;--border:#3a3d43;--accent:#5b8ef1}}"
        "*{box-sizing:border-box}"
        "body{margin:0;min-height:100vh;min-height:100dvh;display:flex;align-items:center;justify-content:center;"
        "font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Segoe UI',Roboto,sans-serif;"
        "background:var(--bg);color:var(--text);padding:24px}"
        "form{width:100%;max-width:340px;background:var(--card);padding:32px 28px 28px;border-radius:20px;"
        "text-align:center;box-shadow:0 1px 2px rgba(16,24,40,.05),0 12px 40px rgba(16,24,40,.10)}"
        "img{width:64px;height:64px;border-radius:16px;box-shadow:0 6px 18px rgba(47,111,236,.35)}"
        "h1{font-size:22px;margin:16px 0 4px;letter-spacing:-.01em}"
        "p.sub{margin:0 0 22px;color:var(--muted);font-size:14px}"
        "input{font:inherit;font-size:16px;width:100%;padding:12px 14px;border-radius:12px;"
        "border:1px solid var(--border);background:transparent;color:var(--text);outline:none}"
        "input:focus{border-color:var(--accent);box-shadow:0 0 0 3px color-mix(in srgb,var(--accent) 20%,transparent)}"
        "button{font:inherit;font-size:16px;font-weight:600;width:100%;padding:12px;margin-top:12px;"
        "border:0;border-radius:12px;background:var(--accent);color:#fff;cursor:pointer}"
        "button:hover{filter:brightness(1.07)}"
        ".err{color:#e5484d;margin:0 0 12px;font-size:14px}"
        "</style></head><body>"
        "<form method='post' action='/login'><img src='/apple-touch-icon.png' alt=''>"
        "<h1>Anki</h1><p class='sub'>输入密码继续 / Enter password</p>"
        f"{err}"
        "<input type='password' name='password' autofocus autocomplete='current-password' "
        "placeholder='密码 / Password'>"
        "<button type='submit'>进入 / Enter</button></form></body></html>"
    )


from ankiweb.collection_service import CollectionService
from ankiweb.bridge.hub import BridgeHub
from ankiweb.assets import build_router as build_assets_router, build_media_router, build_sveltekit_router
from ankiweb.anki_rpc import build_router as build_rpc_router
from ankiweb.bridge.ws import build_router as build_ws_router
from ankiweb.screens.routes import build_screen_router, register_screen_handlers
from ankiweb.notifier import NotifierState
from ankiweb.sync import SyncManager
from ankiweb.screens import mobile
from pathlib import Path
from starlette.responses import FileResponse, JSONResponse

_STATIC = Path(__file__).parent / "static"


def create_app(settings: Settings | None = None, service: CollectionService | None = None,
               hub: BridgeHub | None = None, notifier=None) -> FastAPI:
    settings = settings or Settings.from_env()
    owns = service is None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        svc = service
        if owns:
            svc = CollectionService(settings)
            await svc.open()
        h = hub if hub is not None else BridgeHub()
        svc.subscribe(lambda flags, initiator: h.broadcast_opchanges(flags, initiator))
        app.state.settings = settings
        app.state.service = svc
        app.state.hub = h
        app.state.notifier = notifier if notifier is not None else NotifierState(
            settings.collection_path.parent / "notify.json")
        register_screen_handlers(svc, h)
        # Fork: sync with the configured Anki sync server (no-op when not configured).
        sync_task = None
        owns_sync = svc.sync is None
        if owns_sync:
            svc.sync = SyncManager(svc, settings.sync, hub=h)
            svc.subscribe(lambda flags, initiator: svc.sync.note_local_change())
            if svc.sync.enabled:
                sync_task = asyncio.create_task(svc.sync.run_periodic())
        try:
            yield
        finally:
            if owns_sync:
                if sync_task is not None:
                    sync_task.cancel()
                    try:
                        await sync_task
                    except (asyncio.CancelledError, Exception):
                        pass
                await svc.sync.close()
            if owns:
                await svc.close()

    app = FastAPI(title="ankiweb", lifespan=lifespan)
    auth = Authenticator(settings.password, settings.collection_path.parent / "auth_secret",
                         settings.session_days)
    limiter = LoginLimiter()
    app.state.auth = auth

    async def host_guard(request, call_next):
        host = request.headers.get("host", "")
        if not host_allowed(host, settings.allowed_hosts):
            return PlainTextResponse("forbidden host", status_code=403)
        return await call_next(request)

    app.add_middleware(BaseHTTPMiddleware, dispatch=host_guard)

    async def auth_guard(request, call_next):
        # Open by default; only gates when ANKIWEB_PASSWORD is set. /login, /logout, /healthz
        # stay reachable so an unauthenticated user can reach the login form.
        if auth.enabled and request.url.path not in OPEN_PATHS:
            if not auth.verify(request.cookies.get(COOKIE)):
                # pages -> login form; assets / RPC / form posts -> a plain 401
                if request.method == "GET" and not request.url.path.startswith(
                        ("/_anki/", "/_app/", "/shell/")):
                    return RedirectResponse("/login", status_code=303)
                return PlainTextResponse("unauthorized", status_code=401)
        return await call_next(request)

    app.add_middleware(BaseHTTPMiddleware, dispatch=auth_guard)

    # --- specific routes FIRST, media catch-all LAST (Starlette matches in order) ---
    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    # fork: PWA manifest + icons (reachable before login so "Add to Home Screen" works)
    @app.get("/manifest.webmanifest")
    def webmanifest():
        return JSONResponse(mobile.manifest(), media_type="application/manifest+json")

    @app.get("/ankiweb-icon.png")
    def app_icon():
        return FileResponse(_STATIC / "ankiweb-icon.png", media_type="image/png",
                            headers={"Cache-Control": "max-age=86400"})

    @app.get("/apple-touch-icon.png")
    @app.get("/apple-touch-icon-precomposed.png")
    def apple_icon():
        return FileResponse(_STATIC / "apple-touch-icon.png", media_type="image/png",
                            headers={"Cache-Control": "max-age=86400"})

    @app.get("/login", response_class=HTMLResponse)
    def login_form():
        # already authenticated (or no gate) -> straight to the app
        return HTMLResponse(_login_html())

    @app.post("/login")
    async def login_submit(request: Request):
        ip = client_ip(request)
        if limiter.blocked(ip):
            return HTMLResponse(_login_html(blocked=True), status_code=429)
        form = await request.form()
        if auth.enabled and password_ok(form.get("password", ""), settings.password):
            limiter.success(ip)
            resp = RedirectResponse("/", status_code=303)
            resp.set_cookie(COOKIE, auth.issue(), httponly=True, samesite="lax",
                            secure=is_https(request), max_age=settings.session_days * 86400)
            return resp
        limiter.failure(ip)
        await asyncio.sleep(0.5)  # slow down guessing a little more
        return HTMLResponse(_login_html(error=True), status_code=401)

    @app.get("/logout")
    def logout(request: Request):
        resp = RedirectResponse("/login", status_code=303)
        resp.delete_cookie(COOKIE, httponly=True, samesite="lax", secure=is_https(request))
        return resp

    static_dir = settings.shell_dir / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/shell/static", StaticFiles(directory=str(static_dir), check_dir=False), name="shell")

    app.include_router(build_assets_router(settings.assets_dir))       # GET  /_anki/{path}
    app.include_router(build_rpc_router(lambda: app.state.service, lambda: app.state.hub))    # POST /_anki/{method}
    app.include_router(build_ws_router(lambda: app.state.hub, settings.allowed_hosts, auth))  # WS /ws
    app.include_router(build_screen_router(lambda: app.state.service, lambda: app.state.notifier))  # GET / + /notify
    app.include_router(build_sveltekit_router(settings.assets_dir))     # GET  /graphs, /_app/{path}, /favicon.ico
    app.include_router(build_media_router(lambda: app.state.service))  # GET  /{path} — LAST

    return app
