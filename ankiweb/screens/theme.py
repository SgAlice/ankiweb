"""Fork: the modern UI theme for the server-rendered screens.

One stylesheet + the navigation bar. Upstream used bare browser-default HTML (gray bevel buttons,
Times, raw tables). This module defines:

- design tokens (CSS variables) for light and night mode (html.night-mode, see bootstrap.ts)
- base element styles wrapped in :where() so they have the lowest specificity: a note type's
  own card CSS (.card {...}) always wins inside the reviewer and previews
- components: nav bar, page header, cards, buttons, inputs, tables, deck list, overview, reviewer
  answer bar, browser, forms
- phone layout (<= 760px): bottom tab bar with a "More" sheet, the reviewer in focus mode
  (no tab bar, back button), stacked browser

The reused SvelteKit pages (graphs, deck options, ...) and the editor iframe keep Anki's own
styling.
"""
from __future__ import annotations

import html

from ankiweb.i18n import tr

# ----------------------------------------------------------------------------- icons
# 24x24 stroke icons (currentColor), drawn for this project.
_ICON_PATHS = {
    "decks": "<path d='M12 3 3 7.5l9 4.5 9-4.5L12 3Z'/><path d='m3 12 9 4.5 9-4.5'/>"
             "<path d='m3 16.5 9 4.5 9-4.5'/>",
    "add": "<circle cx='12' cy='12' r='9'/><path d='M12 8v8M8 12h8'/>",
    "browse": "<circle cx='11' cy='11' r='7'/><path d='m20 20-4-4'/>",
    "stats": "<path d='M4 20h16'/><path d='M7 16v-5'/><path d='M12 16V6'/><path d='M17 16v-8'/>",
    "settings": "<path d='M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1'/>"
                "<circle cx='15' cy='6' r='2'/><circle cx='9' cy='12' r='2'/><circle cx='17' cy='18' r='2'/>",
    "tools": "<rect x='3.5' y='3.5' width='7' height='7' rx='1.5'/><rect x='13.5' y='3.5' width='7' height='7' rx='1.5'/>"
             "<rect x='3.5' y='13.5' width='7' height='7' rx='1.5'/><rect x='13.5' y='13.5' width='7' height='7' rx='1.5'/>",
    "sync": "<path d='M20 11a8 8 0 0 0-14.6-4.4L4 8'/><path d='M4 4v4h4'/>"
            "<path d='M4 13a8 8 0 0 0 14.6 4.4L20 16'/><path d='M20 20v-4h-4'/>",
    "moon": "<path d='M20.5 13.5A8.5 8.5 0 1 1 10.5 3.5a6.5 6.5 0 0 0 10 10Z'/>",
    "more": "<circle cx='5' cy='12' r='1.6' fill='currentColor' stroke='none'/>"
            "<circle cx='12' cy='12' r='1.6' fill='currentColor' stroke='none'/>"
            "<circle cx='19' cy='12' r='1.6' fill='currentColor' stroke='none'/>",
    "back": "<path d='m15 18-6-6 6-6'/>",
    "info": "<circle cx='12' cy='12' r='9'/><path d='M12 16v-5M12 8h.01'/>",
    "bell": "<path d='M6 9a6 6 0 1 1 12 0c0 6 2.5 8 2.5 8h-17S6 15 6 9Z'/><path d='M10 20a2.2 2.2 0 0 0 4 0'/>",
    "logout": "<path d='M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3'/><path d='M10 16l-4-4 4-4'/><path d='M6 12h10'/>",
    "chevron": "<path d='m9 6 6 6-6 6'/>",
    "gear": "<circle cx='12' cy='12' r='3'/><path d='M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1"
            "a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3"
            "l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1"
            "a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9"
            "a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8"
            "l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z'/>",
}


def icon(name: str, cls: str = "aw-ic") -> str:
    return (f"<svg class='{cls}' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='1.8' "
            f"stroke-linecap='round' stroke-linejoin='round' aria-hidden='true'>{_ICON_PATHS[name]}</svg>")


# ----------------------------------------------------------------------------- nav
# Which nav entry is "current" for each page context.
_ACTIVE = {
    "deckbrowser": "decks", "overview": "decks", "reviewer": "decks", "customstudy": "decks",
    "filtereddeck": "decks", "congrats": "decks",
    "add": "add", "browser": "browse", "preferences": "settings",
    "tools": "tools", "notetypes": "tools", "fields": "tools", "cardlayout": "tools",
    "export": "decks", "sync": "sync", "notify": "more", "about": "more",
}


def _nav_link(key: str, href: str, label: str, active: str, extra_cls: str = "") -> str:
    cur = " aria-current='page'" if key == active else ""
    cls = f"aw-tab {extra_cls}".strip()
    return f"<a class='{cls}' href='{href}'{cur}>{icon(key)}<span class='aw-tab-l'>{label}</span></a>"


def nav_html(context: str, sync_button: str) -> str:
    active = _ACTIVE.get(context, "")
    decks, add, browse = tr.actions_decks(), tr.actions_add(), tr.qt_misc_browse()
    stats, prefs = tr.qt_misc_stats(), tr.preferences_preferences()
    tools = tr.qt_accel_tools().replace("&", "")
    more_items = (
        sync_button.replace("aw-sync-btn", "aw-sync-btn aw-sheet-item", 1)
        + f"<a class='aw-sheet-item' href='/preferences'>{icon('settings')}<span>{prefs}</span></a>"
        + f"<a class='aw-sheet-item' href='/tools'>{icon('tools')}<span>{tools}</span></a>"
        + f"<button type='button' class='aw-sheet-item' onclick='ankiwebToggleNight()'>{icon('moon')}"
          "<span>Night mode</span></button>"
        + f"<a class='aw-sheet-item' href='/notify'>{icon('bell')}<span>Push notifications</span></a>"
        + f"<a class='aw-sheet-item' href='/about'>{icon('info')}<span>Source (AGPL)</span></a>"
        + f"<a class='aw-sheet-item' href='/logout'>{icon('logout')}<span>Log out</span></a>"
    )
    return (
        "<nav id='ankiweb-toolbar'>"
        "<a class='aw-brand' href='/deckbrowser'><img src='/apple-touch-icon.png' alt=''>Anki</a>"
        "<div class='aw-tabs'>"
        + _nav_link("decks", "/deckbrowser", decks, active)
        + _nav_link("add", "/add", add, active)
        + _nav_link("browse", "/browse", browse, active)
        + _nav_link("stats", "/graphs", stats, active)
        + _nav_link("settings", "/preferences", prefs, active, "aw-wide")
        + _nav_link("tools", "/tools", tools, active, "aw-wide")
        + "<details class='aw-more'><summary class='aw-tab'>" + icon("more")
        + "<span class='aw-tab-l'>More</span></summary>"
        + f"<div class='aw-sheet'>{more_items}</div></details>"
        "</div>"
        "<div class='aw-right'>"
        + sync_button
        + "<div class='menu aw-wide'><span class='lbl' title='ankiweb extras'>Extras ▾</span>"
          "<div class='sub'><a href='/notify'>Push notifications</a>"
          "<a href='/about' title='Source code (AGPL)'>Source</a>"
          "<a href='/logout'>Log out</a></div></div>"
        + f"<button class='nm aw-icon-btn' onclick='ankiwebToggleNight()' title='Toggle night mode'>{icon('moon')}</button>"
        "</div></nav>"
    )


def page_head(title: str, actions: str = "") -> str:
    """A page title row; `actions` sits on the right (buttons/links)."""
    return (f"<div class='aw-page-head'><h1>{html.escape(title)}</h1>"
            f"<div class='aw-head-actions'>{actions}</div></div>")


# ----------------------------------------------------------------------------- css
_FONT = ('-apple-system,BlinkMacSystemFont,"SF Pro Text","PingFang SC","Hiragino Sans",'
         '"Noto Sans CJK SC","Microsoft YaHei","Segoe UI",Roboto,Helvetica,Arial,sans-serif')
_ST = "env(safe-area-inset-top,0px)"
_SB = "env(safe-area-inset-bottom,0px)"

CSS = (
    "<style>"
    # ---- tokens ----
    ":root{--aw-bg:#f4f5f7;--aw-surface:#fff;--aw-surface-2:#f1f2f5;--aw-text:#18191c;"
    "--aw-muted:#6b7079;--aw-border:#e4e6ea;--aw-border-2:#d3d6dc;--aw-accent:#2f6fec;"
    "--aw-accent-text:#fff;--aw-accent-weak:rgba(47,111,236,.10);--aw-new:#2f6fec;--aw-learn:#e5484d;"
    "--aw-review:#18a058;--aw-danger:#e5484d;--aw-warn-bg:#fff7e8;--aw-warn-border:#f3d29a;"
    "--aw-shadow:0 1px 2px rgba(16,24,40,.04),0 2px 8px rgba(16,24,40,.06);"
    "--aw-shadow-lg:0 12px 40px rgba(16,24,40,.18);--aw-nav-bg:rgba(255,255,255,.82);"
    "--aw-radius:14px;--aw-radius-sm:9px;--aw-nav-h:56px;--aw-tabbar-h:58px}"
    "html.night-mode{--aw-bg:#111214;--aw-surface:#1b1c1f;--aw-surface-2:#25262a;--aw-text:#ececef;"
    "--aw-muted:#9a9ea7;--aw-border:#2b2d32;--aw-border-2:#3a3d43;--aw-accent:#5b8ef1;"
    "--aw-accent-weak:rgba(91,142,241,.16);--aw-new:#6b9bff;--aw-learn:#ff6b6f;--aw-review:#3ccf7f;"
    "--aw-danger:#ff6b6f;--aw-warn-bg:#2d2414;--aw-warn-border:#6b5426;"
    "--aw-shadow:0 1px 2px rgba(0,0,0,.3),0 2px 10px rgba(0,0,0,.25);--aw-nav-bg:rgba(27,28,31,.82)}"
    "html.night-mode{color-scheme:dark}"
    # night: also beats a card template's `.card{background:white}` (like Anki's night mode)
    "html.night-mode body{background:var(--aw-bg);color:var(--aw-text)}"
    # ---- base (lowest specificity; card templates override) ----
    f":where(html[data-aw-ctx]) body{{margin:0;font-family:{_FONT};font-size:15px;line-height:1.5;"
    "color:var(--aw-text);background:var(--aw-bg);-webkit-font-smoothing:antialiased;"
    f"padding:calc(var(--aw-nav-h) + 20px) 24px 48px}}"
    ":where(html[data-aw-ctx]) a{color:var(--aw-accent);text-decoration:none}"
    ":where(html[data-aw-ctx]) a:hover{text-decoration:underline}"
    ":where(html[data-aw-ctx]) h1,:where(html[data-aw-ctx]) h2,:where(html[data-aw-ctx]) h3{"
    "font-weight:650;letter-spacing:-.01em;line-height:1.25}"
    ":where(html[data-aw-ctx]) h3{font-size:22px;margin:4px 0 16px}"
    ".aw-main>h3:first-child,.aw-main>div>h3:first-child{font-size:24px}"
    # buttons
    ":where(html[data-aw-ctx]) :where(button,input[type=button],input[type=submit]),.aw-btn{"
    "font:inherit;font-size:14px;font-weight:550;color:var(--aw-text);background:var(--aw-surface);"
    "border:1px solid var(--aw-border-2);border-radius:var(--aw-radius-sm);padding:7px 14px;"
    "min-height:36px;cursor:pointer;box-shadow:0 1px 1px rgba(16,24,40,.04);"
    "transition:background .15s,border-color .15s,transform .05s;display:inline-flex;align-items:center;"
    "justify-content:center;gap:6px;text-decoration:none!important;vertical-align:middle;line-height:1.2}"
    ":where(html[data-aw-ctx]) :where(button,input[type=button],input[type=submit]):hover,.aw-btn:hover{"
    "background:var(--aw-surface-2)}"
    ":where(html[data-aw-ctx]) :where(button):active{transform:scale(.98)}"
    ":where(html[data-aw-ctx]) :where(button:disabled){opacity:.5;cursor:default}"
    ".aw-primary,#study,#add-btn,#aw-sync-now,input[type=submit]{background:var(--aw-accent)!important;"
    "color:var(--aw-accent-text)!important;border-color:transparent!important}"
    ".aw-primary:hover,#study:hover,#add-btn:hover,#aw-sync-now:hover{filter:brightness(1.07)}"
    ".aw-danger{color:var(--aw-danger)!important;border-color:color-mix(in srgb,var(--aw-danger) 45%,transparent)!important}"
    ".aw-icon-btn{padding:0!important;width:38px;min-height:38px;border:0!important;background:transparent!important;"
    "box-shadow:none!important;color:var(--aw-muted)!important;border-radius:10px!important}"
    ".aw-icon-btn:hover{background:var(--aw-surface-2)!important;color:var(--aw-text)!important}"
    ".aw-ic{width:20px;height:20px;flex:none}"
    # inputs
    ":where(html[data-aw-ctx]) :where(input[type=text],input[type=number],input[type=search],input[type=password],"
    "input[type=url],input[type=email],input:not([type]),select,textarea){font:inherit;font-size:14px;"
    "color:var(--aw-text);background:var(--aw-surface);border:1px solid var(--aw-border-2);"
    "border-radius:var(--aw-radius-sm);padding:7px 10px;min-height:36px;box-sizing:border-box;"
    "transition:border-color .15s,box-shadow .15s;max-width:100%}"
    ":where(html[data-aw-ctx]) :where(select){padding-right:28px;appearance:none;-webkit-appearance:none;"
    "background-image:url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' "
    "fill='none' stroke='%238a8f98' stroke-width='2' stroke-linecap='round'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E\");"
    "background-repeat:no-repeat;background-position:right 8px center;background-size:16px}"
    ":where(html[data-aw-ctx]) :where(textarea){min-height:80px;line-height:1.5}"
    ":where(html[data-aw-ctx]) :where(input,select,textarea):focus{outline:none;border-color:var(--aw-accent);"
    "box-shadow:0 0 0 3px var(--aw-accent-weak)}"
    ":where(html[data-aw-ctx]) :where(input[type=checkbox],input[type=radio]){accent-color:var(--aw-accent);"
    "width:17px;height:17px;vertical-align:-3px;margin:0 6px 0 0}"
    ":where(html[data-aw-ctx]) :where(label){cursor:pointer}"
    # fieldsets become cards, legends become section titles
    ":where(html[data-aw-ctx]) :where(fieldset){background:var(--aw-surface);border:1px solid var(--aw-border);"
    "border-radius:var(--aw-radius);padding:14px 18px 16px;margin:0 0 16px;box-shadow:var(--aw-shadow);line-height:2.1}"
    ":where(html[data-aw-ctx]) :where(legend){float:left;width:100%;padding:0;margin:0 0 4px;font-size:13px;"
    "font-weight:650;color:var(--aw-muted);text-transform:uppercase;letter-spacing:.04em;line-height:1.6}"
    ":where(html[data-aw-ctx]) :where(fieldset>legend+*){clear:both}"
    # generic tables
    ":where(html[data-aw-ctx]) :where(table){border-collapse:collapse}"
    ":where(html[data-aw-ctx]) :where(th){font-size:12px;font-weight:600;color:var(--aw-muted);text-align:left}"
    ":where(html[data-aw-ctx]) :where(td,th){padding:7px 10px;border-bottom:1px solid var(--aw-border)}"
    ":where(html[data-aw-ctx]) :where(pre,code){font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:13px}"
    ":where(html[data-aw-ctx]) :where(pre){background:var(--aw-surface-2);border-radius:var(--aw-radius-sm);"
    "padding:12px 14px;overflow:auto}"
    ":where(html[data-aw-ctx]) :where(hr){border:0;border-top:1px solid var(--aw-border)}"
    # layout container
    ".aw-main{max-width:880px;margin:0 auto}"
    ".aw-main.aw-wide-main{max-width:none}"
    ".aw-card{background:var(--aw-surface);border:1px solid var(--aw-border);border-radius:var(--aw-radius);"
    "box-shadow:var(--aw-shadow);padding:18px 20px}"
    ".aw-page-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:0 0 16px}"
    ".aw-page-head h1{font-size:28px;margin:0}"
    ".aw-head-actions{display:flex;gap:8px;align-items:center}"
    ".aw-muted{color:var(--aw-muted)}"
    ".aw-phone-only{display:none!important}"
    # ---- nav bar ----
    "#ankiweb-toolbar{position:fixed;top:0;left:0;right:0;height:var(--aw-nav-h);z-index:2000;display:flex;"
    "align-items:center;gap:8px;padding:0 16px;box-sizing:border-box;background:var(--aw-nav-bg);"
    "-webkit-backdrop-filter:saturate(180%) blur(16px);backdrop-filter:saturate(180%) blur(16px);"
    f"border-bottom:1px solid var(--aw-border);font-family:{_FONT};font-size:14px}}"
    "#ankiweb-toolbar a{text-decoration:none!important}"
    ".aw-brand{display:flex;align-items:center;gap:8px;font-weight:700;font-size:16px;color:var(--aw-text)!important;"
    "margin-right:10px}"
    ".aw-brand img{width:26px;height:26px;border-radius:7px}"
    ".aw-tabs{display:flex;align-items:center;gap:2px;flex:1;min-width:0}"
    ".aw-tab{display:inline-flex;align-items:center;gap:6px;padding:7px 12px;border-radius:10px;"
    "color:var(--aw-muted)!important;font-weight:550;white-space:nowrap;cursor:pointer;list-style:none}"
    ".aw-tab::-webkit-details-marker{display:none}"
    ".aw-tab:hover{background:var(--aw-surface-2);color:var(--aw-text)!important}"
    ".aw-tab[aria-current=page]{background:var(--aw-accent-weak);color:var(--aw-accent)!important}"
    ".aw-tab .aw-ic{width:18px;height:18px}"
    ".aw-right{display:flex;align-items:center;gap:6px}"
    ".aw-sync-btn{display:inline-flex;align-items:center;gap:6px;padding:7px 12px;border-radius:10px;"
    "color:var(--aw-muted)!important;font-weight:550;cursor:pointer}"
    ".aw-sync-btn:hover{background:var(--aw-surface-2);color:var(--aw-text)!important}"
    ".aw-sync-btn.spinning .aw-ic{animation:aw-spin 1s linear infinite}"
    "@keyframes aw-spin{to{transform:rotate(360deg)}}"
    ".aw-sync-dot{width:7px;height:7px;border-radius:50%;background:transparent;flex:none}"
    ".aw-more{display:none;position:relative}"
    ".aw-sheet{position:absolute;right:0;top:calc(100% + 8px);min-width:220px;background:var(--aw-surface);"
    "border:1px solid var(--aw-border);border-radius:var(--aw-radius);box-shadow:var(--aw-shadow-lg);padding:6px;"
    "display:flex;flex-direction:column}"
    ".aw-sheet-item{display:flex!important;align-items:center;gap:12px;padding:11px 12px!important;border-radius:10px;"
    "color:var(--aw-text)!important;font-size:15px;font-weight:500;background:transparent!important;border:0!important;"
    "box-shadow:none!important;justify-content:flex-start!important;width:100%;min-height:0!important}"
    ".aw-sheet-item:hover{background:var(--aw-surface-2)!important}"
    ".aw-sheet-item .aw-ic{color:var(--aw-muted)}"
    "#ankiweb-toolbar .menu{position:relative}"
    "#ankiweb-toolbar .menu>.lbl{cursor:default;color:var(--aw-muted);padding:7px 10px;border-radius:10px;font-weight:550}"
    "#ankiweb-toolbar .menu .sub{display:none;position:absolute;top:100%;right:0;min-width:190px;flex-direction:column;"
    "background:var(--aw-surface);border:1px solid var(--aw-border);border-radius:12px;box-shadow:var(--aw-shadow-lg);padding:6px}"
    "#ankiweb-toolbar .menu:hover .sub{display:flex}"
    "#ankiweb-toolbar .menu .sub a{padding:8px 12px;border-radius:8px;color:var(--aw-text)}"
    "#ankiweb-toolbar .menu .sub a:hover{background:var(--aw-surface-2)}"
    # ---- deck list ----
    "table.decks .current td,table.decks tr:hover td{border-radius:0!important}"
    "table.decks{padding:0!important;width:100%;max-width:none;border-collapse:separate;border-spacing:0;background:var(--aw-surface);"
    "border:1px solid var(--aw-border);border-radius:var(--aw-radius);box-shadow:var(--aw-shadow);overflow:hidden;"
    "margin:0 auto}"
    "table.decks th{font-size:12px;font-weight:600;color:var(--aw-muted);padding:12px 10px!important;"
    "border-bottom:1px solid var(--aw-border);background:transparent;text-transform:none}"
    "table.decks th:first-child{padding-left:18px!important;text-align:left}"
    "table.decks th.count{text-align:center}"
    "table.decks td{padding:0 10px!important;height:52px;border-bottom:1px solid var(--aw-border)}"
    "table.decks tr:last-child td{border-bottom:0}"
    "table.decks tr.deck:hover td{background:var(--aw-surface-2)}"
    "table.decks tr.deck.current td{background:var(--aw-accent-weak)}"
    "table.decks td.decktd{padding-left:14px!important;min-width:0;max-width:none;font-size:15px}"
    "table.decks a.deck{color:var(--aw-text)!important;font-weight:550;text-decoration:none!important;"
    "display:inline!important;min-width:0!important}"
    "table.decks a.deck.filtered{color:var(--aw-accent)!important}"
    ".aw-indent{display:inline-block;width:calc(var(--lvl,0) * 20px)}"
    "table.decks .collapse{display:inline-flex;width:22px;height:22px;align-items:center;justify-content:center;"
    "color:var(--aw-muted)!important;text-decoration:none!important;border-radius:6px;margin-right:4px;"
    "font-weight:600;vertical-align:middle}"
    "table.decks a.collapse:hover{background:var(--aw-surface-2)}"
    "table.decks td.count{text-align:center;width:72px;min-width:0}"
    ".new-count,.learn-count,.review-count{display:inline-block;min-width:28px;padding:2px 8px;border-radius:999px;"
    "font-weight:650;font-size:13px;font-variant-numeric:tabular-nums;text-align:center;box-sizing:border-box}"
    ".new-count{color:var(--aw-new)!important;background:color-mix(in srgb,var(--aw-new) 12%,transparent)}"
    ".learn-count{color:var(--aw-learn)!important;background:color-mix(in srgb,var(--aw-learn) 12%,transparent)}"
    ".review-count{color:var(--aw-review)!important;background:color-mix(in srgb,var(--aw-review) 12%,transparent)}"
    ".zero-count{color:var(--aw-muted)!important;opacity:.55;font-variant-numeric:tabular-nums;font-size:13px}"
    "table.decks td.opts{width:44px;text-align:center}"
    "table.decks a.opts{display:inline-flex;width:32px;height:32px;align-items:center;justify-content:center;"
    "border-radius:8px;color:var(--aw-muted);opacity:.6}"
    "table.decks tr.deck:hover a.opts{opacity:1}"
    "table.decks a.opts:hover{background:var(--aw-border)}"
    "table.decks .gears{display:none}"
    "#studiedToday{margin:18px 0 14px;text-align:center;color:var(--aw-muted);font-size:14px}"
    ".dyn-buttons{display:flex;flex-wrap:wrap;gap:8px;justify-content:center;align-items:center}"
    # ---- overview / congrats ----
    ".aw-hero{text-align:center;padding:28px 24px 24px}"
    ".aw-hero h1{font-size:28px;margin:0 0 6px}"
    ".aw-hero .description{color:var(--aw-muted);margin:0 auto 8px;max-width:560px}"
    ".aw-stats{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:22px auto 24px;max-width:460px}"
    ".aw-stat{background:var(--aw-surface-2);border-radius:12px;padding:12px 6px}"
    ".aw-stat-n{font-size:30px;font-weight:700;font-variant-numeric:tabular-nums;line-height:1.1}"
    ".aw-stat-n.new-count,.aw-stat-n.learn-count,.aw-stat-n.review-count{background:none;padding:0;font-size:30px}"
    ".aw-stat-l{font-size:12px;color:var(--aw-muted);margin-top:4px}"
    "#study:focus{outline:none}#study:focus-visible{box-shadow:0 0 0 3px var(--aw-accent-weak)!important}"
    "#study{font-size:17px!important;padding:12px 40px!important;border-radius:12px!important;min-width:220px}"
    ".bottom-buttons{display:flex;flex-wrap:wrap;gap:8px;justify-content:center;align-items:center;margin-top:18px}"
    "#descedit{margin-top:16px;text-align:left}"
    "#descbox{width:100%}"
    ".congrats{text-align:center}"
    ".congrats h1{font-size:22px}"
    ".aw-emoji{font-size:46px;line-height:1;margin-bottom:8px}"
    # ---- reviewer ----
    "html[data-aw-ctx=reviewer] .aw-main{max-width:none}"
    "#ankiweb-answer{text-align:center;margin:22px 0 8px}"
    "#ankiweb-answer .ansbut{font-size:16px;padding:10px 36px;border-radius:12px;min-width:240px}"
    "#ankiweb-answer .ease-row{display:inline-flex;gap:10px}"
    "#ankiweb-answer .ease{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px;"
    "min-width:120px;padding:8px 16px;border-radius:12px;font-size:15px;border:0!important;box-shadow:none!important}"
    "#ankiweb-answer .ease-ivl{font-size:12px;opacity:.75;font-weight:500}"
    "#ankiweb-answer .ease[data-ease='1']{background:color-mix(in srgb,var(--aw-learn) 14%,transparent)!important;color:var(--aw-learn)!important}"
    "#ankiweb-answer .ease[data-ease='2']{background:var(--aw-surface-2)!important;color:var(--aw-muted)!important}"
    "#ankiweb-answer .ease[data-ease='3']{background:color-mix(in srgb,var(--aw-review) 14%,transparent)!important;color:var(--aw-review)!important}"
    "#ankiweb-answer .ease[data-ease='4']{background:color-mix(in srgb,var(--aw-new) 14%,transparent)!important;color:var(--aw-new)!important}"
    "#ankiweb-answer .ease .ease-label{color:inherit!important;font-weight:650}"
    "#rev-more,#rev-back{display:none}"
    "#rev-actions{display:flex;flex-wrap:wrap;gap:6px;justify-content:center;margin:24px auto 0;max-width:900px}"
    "#rev-actions .rev-act{font-size:13px;min-height:32px;padding:5px 10px;margin:0}"
    "#ankiweb-answer button{margin:0}"
    # ---- browser ----
    "html[data-aw-ctx=browser] .aw-main{max-width:none}"
    "#browser{font-family:inherit!important;font-size:14px!important}"
    "#browser-top{display:flex;flex-wrap:wrap;gap:8px;align-items:center;padding:0 0 12px!important;border:0!important}"
    "#search{flex:1;min-width:240px;width:auto!important;padding:9px 12px 9px 36px!important;"
    "background:var(--aw-surface) url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' "
    "fill='none' stroke='%238a8f98' stroke-width='2' stroke-linecap='round'%3E%3Ccircle cx='11' cy='11' r='7'/%3E"
    "%3Cpath d='m20 20-4-4'/%3E%3C/svg%3E\") no-repeat 11px center/17px!important}"
    "#browser-status{color:var(--aw-muted)!important;font-size:13px}"
    "#browser-actions{display:flex;flex-wrap:wrap;gap:6px;width:100%}"
    "#browser-actions button{font-size:13px;min-height:32px;padding:5px 11px}"
    "#browser-main{display:flex;gap:14px;align-items:flex-start}"
    "#sidebar{width:210px!important;flex:none;padding:8px!important;border:1px solid var(--aw-border)!important;"
    "border-radius:var(--aw-radius);background:var(--aw-surface);box-shadow:var(--aw-shadow);box-sizing:border-box}"
    "#sidebar .side-section{font-size:12px;color:var(--aw-muted);text-transform:uppercase;letter-spacing:.04em;"
    "margin:10px 8px 4px!important}"
    "#sidebar .side-item{padding:6px 8px!important;border-radius:8px;color:var(--aw-text)!important;font-size:14px}"
    "#sidebar .side-item:hover{background:var(--aw-surface-2)!important;text-decoration:none!important}"
    "#results-wrap{flex:1;min-width:0;background:var(--aw-surface);border:1px solid var(--aw-border);"
    "border-radius:var(--aw-radius);box-shadow:var(--aw-shadow);max-height:calc(100vh - 190px)!important}"
    "#results th{position:sticky;top:0;background:var(--aw-surface);z-index:1;padding:10px 12px!important}"
    "#results td{padding:9px 12px!important;border-bottom:1px solid var(--aw-border)!important}"
    "#results td,#results th{white-space:nowrap;max-width:420px;overflow:hidden;text-overflow:ellipsis}"
    ".browser-row:hover{background:var(--aw-surface-2)!important}"
    "#results tr.selected,#results tr.selected:hover{background:var(--aw-accent-weak)!important}"
    "#detail{flex:0 0 44%;padding:0!important;border:1px solid var(--aw-border)!important;border-radius:var(--aw-radius);"
    "background:var(--aw-surface);overflow:hidden;box-shadow:var(--aw-shadow)}"
    "#detail:empty{display:none}"
    ".editor-frame{display:block}"
    "#aw-side-toggle{display:none}"
    # ---- add ----
    "#add-chrome{position:static!important;height:auto!important;display:flex;flex-wrap:wrap;gap:10px;"
    "align-items:flex-end;padding:14px 16px!important;margin:0 0 12px;background:var(--aw-surface)!important;"
    "border:1px solid var(--aw-border)!important;border-radius:var(--aw-radius);box-shadow:var(--aw-shadow)}"
    "html[data-aw-ctx=add] body{padding-top:calc(var(--aw-nav-h) + 20px)!important}"
    "#add-chrome label{display:flex;flex-direction:column;gap:4px;font-size:12px;color:var(--aw-muted);font-weight:600}"
    "#add-chrome select{min-width:180px}"
    "#add-chrome>a{margin-left:auto;align-self:center}"
    "#add-toast{color:var(--aw-review)!important;font-weight:600;align-self:center}"
    # ---- sync page ----
    ".aw-sync{font-family:inherit!important;max-width:none!important;padding:0!important}"
    ".aw-sync table{background:var(--aw-surface);border:1px solid var(--aw-border);border-radius:var(--aw-radius);"
    "box-shadow:var(--aw-shadow);border-collapse:separate;overflow:hidden;width:100%}"
    ".aw-sync td{padding:10px 16px!important}"
    ".aw-sync td:first-child{color:var(--aw-muted);width:120px}"
    ".aw-sync .warn{background:var(--aw-warn-bg)!important;border-color:var(--aw-warn-border)!important;border-radius:12px!important}"
    ".aw-sync .err{color:var(--aw-danger)!important}"
    ".aw-sync button.danger{color:var(--aw-danger)}"
    # ---- misc screens ----
    ".custom-study,.filtered-deck{max-width:640px}"
    # note types: a card list
    "#nttbl{width:100%;background:var(--aw-surface);border:1px solid var(--aw-border);border-radius:var(--aw-radius);"
    "box-shadow:var(--aw-shadow);border-collapse:separate;border-spacing:0;overflow:hidden;margin-bottom:18px}"
    "#nttbl td{padding:10px 12px!important}"
    "#nttbl tr:last-child td{border-bottom:0}"
    "#nttbl .nt-name{font-weight:600;width:100%}"
    "#nttbl .nt-count{color:var(--aw-muted);white-space:nowrap;font-size:13px}"
    "#nttbl a{white-space:nowrap}"
    ":where(html[data-aw-ctx]) :where(button){white-space:nowrap}"
    # fields screen: one card per field, contents wrap
    "#fieldtbl,#fieldtbl tbody{display:block}"
    "#fieldtbl tr.field-row{display:flex;flex-wrap:wrap;align-items:center;gap:8px 18px;background:var(--aw-surface);"
    "border:1px solid var(--aw-border);border-radius:var(--aw-radius);box-shadow:var(--aw-shadow);padding:12px 14px;"
    "margin:0 0 10px}"
    "#fieldtbl td{display:block;border:0!important;padding:0!important}"
    "#fieldtbl label{display:inline-flex;align-items:center;gap:6px;font-size:13px;color:var(--aw-muted)}"
    "#fieldtbl td:last-child{margin-left:auto;display:flex;gap:6px}"
    "textarea.tmpl,#card-layout textarea{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:13px;width:100%}"
    # SvelteKit pages: back button when running as a home-screen app (no browser chrome)
    # ---- phones ----
    "@media (max-width:760px){"
    f":where(html[data-aw-ctx]) body{{padding:calc({_ST} + 14px) 14px calc(var(--aw-tabbar-h) + {_SB} + 24px)}}"
    "html[data-aw-ctx=add] body{padding-top:calc(" + _ST + " + 14px)!important}"
    ".aw-page-head h1{font-size:30px}"
    ".aw-phone-only{display:inline-flex!important}"
    ".aw-page-head .aw-sync-btn{padding:6px 12px}"
    # bottom tab bar
    f"#ankiweb-toolbar{{top:auto;bottom:0;height:calc(var(--aw-tabbar-h) + {_SB});padding:0 6px {_SB};"
    "border-bottom:0;border-top:1px solid var(--aw-border);gap:0}"
    ".aw-brand,.aw-right,.aw-wide{display:none!important}"
    ".aw-tabs{justify-content:space-around;gap:0;height:100%}"
    ".aw-tabs>.aw-tab,.aw-more>summary.aw-tab{flex-direction:column;gap:2px;padding:6px 4px;font-size:11px;"
    "border-radius:10px;min-width:62px;background:transparent!important}"
    ".aw-tabs>.aw-tab .aw-ic,.aw-more>summary .aw-ic{width:24px;height:24px}"
    ".aw-tab[aria-current=page]{color:var(--aw-accent)!important}"
    ".aw-more{display:block}"
    ".aw-more[open]>summary{color:var(--aw-accent)!important}"
    f".aw-sheet{{position:fixed;left:10px;right:10px;top:auto;bottom:calc(var(--aw-tabbar-h) + {_SB} + 8px);"
    "min-width:0;padding:8px}"
    ".aw-sheet-item{padding:13px 12px!important;font-size:16px}"
    # inputs: 16px stops iOS zooming on focus
    "input,select,textarea{font-size:16px!important}"
    "button{min-height:40px}"
    # deck list
    "table.decks{border-radius:var(--aw-radius)}"
    "table.decks td{height:56px}"
    "table.decks td.decktd{font-size:16px;white-space:normal;word-break:break-word;padding-left:12px!important}"
    "table.decks td.count{width:46px;padding:0 3px!important}"
    "table.decks th.count{font-size:11px;padding:10px 2px!important;white-space:nowrap}"
    "table.decks td.opts{width:36px;padding:0 4px 0 0!important}"
    "table.decks a.opts{opacity:.7}"
    ".new-count,.learn-count,.review-count{min-width:26px;padding:2px 6px}"
    ".dyn-buttons button,.dyn-buttons .aw-btn{flex:1 1 40%}"
    # overview
    ".aw-hero{padding:24px 16px}"
    "#study{width:100%;min-height:52px}"
    ".bottom-buttons button{flex:1 1 40%}"
    # reviewer focus mode: no tab bar, back button + actions button on top, answer bar at the bottom
    "html[data-aw-ctx=reviewer] #ankiweb-toolbar{display:none}"
    f"html[data-aw-ctx=reviewer] body{{padding:calc({_ST} + 60px) 16px calc(110px + {_SB})!important}}"
    f"#rev-back,#rev-more{{display:inline-flex!important;position:fixed;top:calc({_ST} + 10px);z-index:1600;"
    "width:40px;height:40px;min-height:0!important;padding:0!important;align-items:center;justify-content:center;"
    "border-radius:20px;background:var(--aw-nav-bg)!important;border:1px solid var(--aw-border)!important;"
    "color:var(--aw-text)!important;-webkit-backdrop-filter:blur(12px);backdrop-filter:blur(12px);box-shadow:var(--aw-shadow)}"
    "#rev-back{left:12px}#rev-more{right:12px;font-size:0}"
    f"#ankiweb-answer{{position:fixed;left:0;right:0;bottom:0;margin:0;z-index:1500;padding:10px 12px calc(10px + {_SB});"
    "background:var(--aw-nav-bg);border-top:1px solid var(--aw-border);-webkit-backdrop-filter:blur(16px);backdrop-filter:blur(16px)}"
    "#ankiweb-answer,#ankiweb-answer *{box-sizing:border-box}"
    "#ankiweb-answer .ansbut{width:100%;min-width:0;height:56px;font-size:18px;margin:0}"
    "#ankiweb-answer .ease-row{display:grid;grid-auto-flow:column;grid-auto-columns:1fr;gap:10px;width:100%}"
    "#ankiweb-answer .ease{min-width:0;width:100%;height:60px;margin:0;font-size:17px;padding:4px}"
    "#ankiweb-answer .ease-ivl{font-size:13px}"
    "#rev-actions{display:none;margin:0}"
    f"#rev-actions.open{{display:grid;grid-template-columns:1fr 1fr;gap:8px;position:fixed;left:10px;right:10px;"
    f"top:calc({_ST} + 58px);z-index:1600;padding:10px;background:var(--aw-surface);border:1px solid var(--aw-border);"
    "border-radius:var(--aw-radius);box-shadow:var(--aw-shadow-lg);max-height:65vh;overflow:auto}"
    "#rev-actions.open .rev-act{min-height:44px;font-size:14px}"
    # browser: stacked
    "#search{min-width:0;width:100%!important}"
    "#browser-actions{flex-wrap:nowrap;overflow-x:auto;padding-bottom:2px;-webkit-overflow-scrolling:touch}"
    "#browser-actions button{flex:none}"
    "#browser-main{flex-direction:column;gap:10px}"
    "#sidebar{display:none;width:100%!important;max-height:40vh;overflow:auto}"
    "#browser.aw-side #sidebar{display:block}"
    "#sidebar .side-item{padding:10px 8px!important;font-size:15px}"
    "#aw-side-toggle{display:inline-flex!important}"
    "#results-wrap{width:100%;max-height:45vh!important}"
    "#results td,#results th{padding:11px 10px!important}"
    "#detail{width:100%;flex:none}"
    ".editor-frame{height:70vh!important}"
    # add
    "#add-chrome{padding:12px!important}"
    "#add-chrome label{flex:1 1 40%}"
    "#add-chrome select{min-width:0;width:100%}"
    "#add-btn{flex:1 1 100%;order:5;min-height:46px;font-size:16px!important}"
    "#add-chrome>a{display:none}"
    "#add-toast{order:6}"
    # forms
    "fieldset{padding:12px 14px 14px}"
    # wide generic tables scroll sideways instead of zooming the whole page out
    ".aw-main table:not(.decks):not(#results):not(#nttbl){display:block;max-width:100%;overflow-x:auto}"
    # note types on phones: name on its own line, actions below
    "#nttbl,#nttbl tbody{display:block}"
    "#nttbl tr.nt-row{display:flex;flex-wrap:wrap;align-items:center;gap:6px 10px;padding:12px 14px;"
    "border-bottom:1px solid var(--aw-border)}"
    "#nttbl tr.nt-row:last-child{border-bottom:0}"
    "#nttbl td{display:block;padding:0!important;border:0!important}"
    "#nttbl .nt-name{width:auto;flex:1 1 100%}"
    "pre{white-space:pre-wrap;word-break:break-word}"
    "#fieldtbl td:last-child{margin-left:0}"
    "}"
    "</style>"
)
