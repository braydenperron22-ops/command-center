"""Apple-style dark glass CSS injected once at app start."""

CSS = """
<style>
/* Used to @import Bebas Neue/Oswald/JetBrains Mono here for the
   jumbotron's own separate arena font stack — removed once --label/
   --disp/--num all converged on the same system font (see --label's
   own comment in the JUMBOTRON section below): "make every single
   text in the sheet that font." Nothing in this file references any
   of those three families anymore, so one less Google Fonts request
   on every kiosk page load, not just dead CSS. */
#MainMenu, header, footer { visibility: hidden; }

/* Session report: "it's currently nighttime and I'm not seeing the
   night background, it's just a black screen." The animated sky
   canvas (app.py's own merged kiosk script, kiosk-sky-canvas) sits
   behind document.body at z-index:-1 -- but .streamlit/config.toml's
   own backgroundColor (#000000) paints Streamlit's root container
   fully opaque ON TOP of that in the normal stacking order. The canvas
   was never actually visible at all, any time of day, not something
   that broke specifically at night -- flat black just happens to look
   close enough to "working" during the day that nobody caught it
   until the moon/stars were the obvious thing missing. Making the
   root transparent is what actually lets the canvas show through;
   every real tile/card in this file already carries its own explicit
   background (the established convention throughout this stylesheet),
   so removing the root's solid color only reveals the sky in the
   empty space around and between content, not through it. */
.stApp, [data-testid="stAppViewContainer"] {
    background: transparent !important;
}

/* Kills Streamlit's own "stale element" dimming — every element
   container gets data-stale="true" and fades toward partial opacity for
   the ~1s a rerun is in flight, then fades back. Confirmed live
   (data-stale flips true on 8-10 of 14 containers every ~5s, exactly
   matching st_autorefresh's interval, with a real `transition: opacity
   1s ease-in 0.5s` driving it down). Harmless on a normal Streamlit app
   where reruns are rare and user-triggered, but this dashboard reruns
   on a hard 5s timer forever — that's a visible flicker every single
   cycle, all day, for a page nobody's even interacting with. Update the
   data in place instead. */
[data-stale="true"] {
    opacity: 1 !important;
    transition: none !important;
}

/* Global animation/transition kill switch. Session request: "remove
   quite literally all of the animations. I feel like it slows the
   boot up time, and it's making my dashboard really unstable." This
   file had ~35 separate @keyframes (toast pulses, headline swap-ins,
   jumbotron score flashes/transitions, weather-alert shakes, etc.) —
   rather than hunt down and delete every individual `animation:`/
   `transition:` declaration across a 5700+ line stylesheet (a real
   risk of a stray edit breaking a brace somewhere in there), one
   maximum-specificity-safe override kills every single one at once:
   `!important` on the universal selector beats any non-!important
   rule regardless of source order, and only loses to another
   `!important` rule with higher selector specificity — which is
   exactly how the two deliberate exceptions right below are re-
   enabled. This also reaches the few places (kiosk-wp-smoother/
   kiosk-jumbo-fade used to, before this session removed them outright
   — see app.py's own comment where they used to live) that set
   `el.style.transition` directly via JS: an inline style with no
   `!important` still loses to an external stylesheet rule that has
   one.

   Two exceptions, kept on purpose because they're the actual CONTENT
   of their page, not decorative chrome — killing them wouldn't make
   the dashboard calmer, it would make a whole feature stop working:
   .ticker-track's scroll (the bottom ticker's entire reason to exist
   is that it moves) and .weather-radar-frame-img's crossfade (the
   Radar page's whole point is showing recent motion; the frames are
   already-loaded static images cycled by app.py's kiosk-radar-anim
   script, so the "animation" here is genuinely the data, not polish).
   Everything else — every pulse, glow, fade-in, swap-in, shake, and
   page/jumbotron transition — is gone. (night_mode.py's own top bar
   briefly had a third exception here too, a scrolling ticker — traded
   for a static, centered bar instead, see .night-ticker's own comment,
   so nothing needed the carve-out for long.) */
* {
    animation: none !important;
    transition: none !important;
}
.ticker-track {
    animation: ticker-scroll 55s linear infinite !important;
}
.weather-radar-frame-img {
    transition: opacity 0.35s ease !important;
}
/* Design-pass fix, found live: app.py's kioskRevealOverlay (the real
   toast "wipe reveal" — covers a fresh toast, then clip-path-wipes
   away) used to toggle this transition via plain inline JS
   (overlay.style.transition = '...'), which the kill switch above
   silently killed the whole time regardless — a JS-set el.style.X =
   'value !important' string doesn't reliably register in real
   browsers either, so appending !important there wasn't a fix. Same
   real shape as .ticker-track/.weather-radar-frame-img just above
   (a real, deliberate exception, not a decorative extra) — moved to a
   class toggle instead of an inline style toggle, same pattern
   kiosk-headline-rotation-swap already uses for the identical reason. */
#kiosk-toast-overlay.wipe-active {
    transition: clip-path 0.55s cubic-bezier(.4,0,.2,1), opacity 0.25s ease-in 0.55s !important;
}

/* A resting-hidden band-aid used to live here, forcing `opacity: 0 !
   important; visibility: hidden !important` onto .jumbo-transition,
   .page-transition-curtain and .jumbo-play-overlay. It was written for
   TOGGLE-BY-CLASS elements — things permanently in the DOM that an
   animation was supposed to reveal — and the reasoning was sound for
   that shape: the kill switch above can't know what a keyframe's end
   state was, so a full-screen `position:fixed; inset:0` curtain frozen
   at the browser default (opacity:1) would hide the entire dashboard.

   All three were actually PRESENCE-GATED: Python only ever emits the
   element on the exact rerun it should be visible. So the band-aid
   didn't protect anything — it just made them never render at all. Net
   effect, live for weeks: the game-mode enter/exit announcement and the
   full-screen play-result announcement never appeared once, and two
   caption lines inside them ("GAME MODE · [TEAM]" / "Back to your day")
   were permanently invisible on top of that.

   Removed 2026-09-20 with the jumbotron rebuild. The two jumbotron
   elements were reshaped so they're correct with no animation at all
   (see .jumbo-transition / .jumbo-play-overlay in the JUMBOTRON section
   for the specifics, including why the enter/exit announcement is no
   longer a full-screen curtain). .page-transition-curtain went away
   entirely — it was an EMPTY opaque div whose only job was the fade, so
   with animations permanently off its only two possible states were
   "invisible" (pointless) or "black screen for a whole rerun cycle"
   (actively harmful); app.py no longer emits it.

   The rule for anything full-screen added here in future: if it's
   toggled by class, give it an explicit resting opacity/visibility; if
   it's presence-gated, give it NO resting-hidden style whatsoever. */

.block-container {
    padding-top: 1.8rem;
    padding-bottom: 4.6rem;
    /* Session request: "we have a bigger new display now... 1920 by
       1080... reformat every single element to fit into this frame."
       1450px was tuned for a smaller/narrower screen than this kiosk
       actually has now — confirmed live at a real 1920px viewport,
       every non-jumbotron page sat in a visibly narrow center column
       with ~235px of flatly empty margin on each side. 1800px keeps a
       small deliberate margin (60px each side at 1920px, matching
       .top-alert-bar's own inset) rather than corner-to-corner, same
       reasoning .block-container:has(.jumbo-root)'s own max-width:100%
       comment already established for the jumbotron ("right for
       tiles, wrong for a full-bleed scoreboard") — plain tiles
       shouldn't press against the bezel the way a broadcast board
       can. Individual pages still need their own pass to actually use
       the extra room (bigger cards/type, not just wider gaps) — this
       is the shared floor every one of them now has to work with. */
    max-width: 1800px;
    min-height: calc(100vh - 4.6rem) !important;
    display: flex !important;
    flex-direction: column !important;
    /* Session report: "in the mornings I cannot see time, I cannot see
       weather, the morning brief is cut off sometimes... make sure we
       anchor it to the highest point." This was `center` from day one —
       already diagnosed as the root cause of a related bug once before
       (see .leave-headline's own comment above: a long morning brief
       pushes total content past one viewport's height, and centering
       then pushes the excess out equally above AND below the fold,
       taking the clock/weather/hero row with it on the top side). That
       older fix routed the red-headline banners around the problem with
       position:fixed instead of ever touching the actual cause — this
       finally does. flex-start means any overflow now only ever falls
       off the BOTTOM (predictable, and the least-important content by
       page order), never the top. Mobile already runs flex-start (see
       its own media query below) for the same reason, just never
       ported back to desktop/kiosk until now. */
    justify-content: flex-start !important;
}

/* Same report, second half: "this new display is not technically as
   tall... make it so we scale everything down a little bit." Confirmed
   with the user first (still the real 1920x1080 TV, just less usable
   height in practice — browser chrome/taskbar eating into the real
   1080px, not a different panel) rather than guessing a screen size —
   see this session's own jumbotron saga for how expensive that guess
   was to get wrong. `zoom` (not `transform: scale`, which doesn't
   affect layout flow or reflow fixed-position descendants the same
   way) uniformly shrinks every px/rem measurement inside — fonts,
   padding, tile sizes — without a page-by-page rewrite, matching how a
   Chromium kiosk browser (Brave, confirmed) already behaves under real
   page zoom. Scoped to width > 640px so this never doubles up with the
   phone breakpoint above, which already has its own separate, unrelated
   sizing. Stepped rather than one cutoff since the actual deficit here
   is a browser-chrome/taskbar nibble, not a fixed known number — each
   step is deliberately modest.

   `:not(:has(.jumbo-root))` excludes the jumbotron at the SOURCE.
   Session report, new Ubuntu kiosk: "the lower third of the screen is
   just cut out black... every other page sizes properly, except for
   this one." Root cause: every normal page is flowing text/tiles that
   shrinks uniformly under zoom and still looks right, but the jumbotron
   computes its own height directly against the real viewport — that
   already-correct box then got shrunk AGAIN by this ancestor zoom,
   leaving a gap below it exactly the size of the shrink, reading as
   solid black against config.toml's own black base. It was patched for
   a while by a downstream `zoom: 1 !important` on
   .block-container:has(.jumbo), a specificity race that had to be
   re-won every time a new interaction surfaced; excluding the page here
   means there's no race left to have. A browser without :has() support
   simply falls back to the old (zoomed) behavior rather than breaking. */
@media (min-width: 641px) and (max-height: 1040px) {
    .block-container:not(:has(.jumbo-root)) { zoom: 0.94; }
}
@media (min-width: 641px) and (max-height: 950px) {
    .block-container:not(:has(.jumbo-root)) { zoom: 0.86; }
}
@media (min-width: 641px) and (max-height: 850px) {
    .block-container:not(:has(.jumbo-root)) { zoom: 0.78; }
}

.block-container > div {
    flex-shrink: 0;
}

/* The kiosk hotkey component (app.py) is a zero-height iframe that only
   exists to install a keydown listener — Streamlit still reserves a
   block for it, which on a page sized to exactly fill the screen is a
   real gap. Collapsed entirely rather than just made short. */
iframe[title="st.iframe"][height="0"] { display: none !important; }
.stElementContainer:has(> iframe[title="st.iframe"][height="0"]) { display: none !important; }

html, body, [class*="css"] {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Helvetica Neue", sans-serif;
}

.hero-row {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 0.4rem;
}

/* Morning briefing — see morning_briefing.py. A calm, readable card
   rather than an alert-style banner: this is routine information, not
   something urgent, so it deliberately doesn't borrow the red/orange
   "pay attention now" language the weather-statement/leave-headline
   banners use above it.

   Session redesign: five real candidate formats (a stats bar + bigger
   commentary, no bar with one full narrated paragraph, a loud hype
   headline + body, a multi-beat rundown, each generated from actual
   live data and compared side by side) — "I like loud hype headline
   plus body, but make it so that the headline doesn't have to be
   hype... can we do the same thing with different formatting for it,"
   settled on a small uppercase eyebrow-style headline above a large,
   prominent body. Replaces the old two-child split (a mechanical
   .morning-stats bullet list plus a short .morning-commentary add-on
   line) entirely — this app's own earlier "Quick Stats Bar + 1-2
   Sentence Commentary" redesign, itself now retired by this same
   session's follow-up request. The card still only owns the glass
   container (background/blur/border/padding); .morning-headline/
   .morning-body below own their own typography. */
/* Session report: "the morning brief... white on white as well." This
   card's own translucent tint used to be a light rgba(255,255,255,0.05)
   glass — a nice subtle sheen assuming it always sat on this app's own
   dark background, which was a safe assumption before the sky canvas
   could put a bright fog/snow/heat-wave sky directly behind it. Switched
   to a dark tint instead (same rgba(12,12,16,x) family .ai-status-bar's
   own corner badge already uses for exactly this "must stay legible
   regardless of what's behind it" reason) — the card's own light text
   colors (color/.morning-body/.morning-headline below) were always
   designed for a dark backing, so this is the fix that actually matches
   the text, not a shadow papering over a backwards assumption. */
.morning-briefing {
    color: #E5E5EA;
    background: rgba(12,12,16,0.6);
    backdrop-filter: blur(24px) saturate(160%);
    -webkit-backdrop-filter: blur(24px) saturate(160%);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 16px;
    padding: 0.9rem 1.4rem;
    margin-bottom: 0.8rem;
}

/* Session report: "the morning brief is still mentioning Tuesday...
   give it the day of the week every day so it doesn't mess up." A
   real, always-fresh dateline (morning_briefing.render's own
   now.strftime call, never cached or AI-written) sitting above the
   headline — a permanent, cache-independent anchor for which day this
   card is actually for, regardless of anything happening upstream in
   the AI/cache pipeline below it. Quiet and small on purpose: this is
   metadata confirming the card is current, not something competing
   with the headline/body for attention. */
.morning-date {
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.16em;
    color: #8E8E93;
    margin: 0 0 0.35rem;
}

/* Small uppercase tag rather than a big banner — the body below is the
   actual star of the card now (see its own comment); this is a label
   for it, not competing prose. Same accent red the old .morning-stats
   dot used, so the card's own color identity carries over even though
   the layout underneath it changed completely. */
.morning-headline {
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #FF453A;
    margin: 0 0 0.5rem;
}

/* The real written content — headline + body together are now the
   ONLY text on the card (no separate mechanical stats bar above it
   anymore), so this carries real weight: larger and brighter than the
   old .morning-commentary add-on line ever needed to be, since that
   used to sit below facts already shown elsewhere and this doesn't. */
.morning-body {
    font-size: 1.28rem;
    line-height: 1.48;
    font-weight: 500;
    color: #F5F5F7;
}

.hero-weather {
    text-align: right;
}

.weather-condition {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 0.6rem;
}

/* Session report: "it's a very foggy morning... the text isn't
   visible... white on white." Real consequence of the sky canvas
   sitting directly behind these specific elements (theme.py's own
   .stApp-transparency fix) — unlike most tiles/cards in this file,
   .hero-row's own children have no background of their own, so a
   bright sky state (fog, snow, heat-wave, extreme-cold, cloudy-day)
   can sit right behind light-colored text with nothing between them.
   A text-shadow (not a background swap or a color that depends on
   knowing which sky state is active) keeps every one of these legible
   against ANY sky brightness, including ones this app doesn't even
   have yet — the same technique the Sky Canvas design preview already
   used for exactly this reason. */
.clock, .date-sub, .weather-condition-label, .weather-hilo, .page-title {
    text-shadow: 0 1px 10px rgba(0,0,0,0.55), 0 1px 3px rgba(0,0,0,0.75);
}

.clock {
    font-size: 4.2rem;
    font-weight: 600;
    letter-spacing: -0.02em;
    color: #F5F5F7;
    line-height: 1.1;
}

.date-sub {
    font-size: 1.35rem;
    color: #8E8E93;
    font-weight: 400;
}

.weather-condition-label {
    font-size: 1.4rem;
    font-weight: 500;
    color: #C7C7CC;
    margin-top: 0.1rem;
}

.weather-hilo {
    color: #8E8E93;
    font-weight: 500;
}

.weather-extras {
    display: flex;
    flex-wrap: wrap;
    justify-content: flex-end;
    align-items: flex-start;
    gap: 0.8rem;
    margin-top: 0.6rem;
}

/* Big enough to read from across the room, same as the rest of this
   kiosk's hero text — these used to be smaller than the date line
   beneath them, which was backwards given they're time-sensitive
   conditions worth noticing. Color/background are set inline per
   render now (UV scales orange->vibrant red with magnitude, rain
   scales pale->deep blue with proximity), not fixed here.

   Softened from a 2px solid outline + wide glow (read as a neon sign
   sitting on top of an already-filled chip — each render already sets
   its own tinted `background` inline) to a plain filled pill with a
   faint hairline and a tight, low, mostly-for-depth shadow instead of
   a color-matched glow — the vibrant fill/text color alone is what
   should read as "this needs attention" from across the room, the
   way Apple's own tinted status chips (Health, Fitness, Weather) work,
   not an outline effect layered on top of it. */
.weather-extra {
    font-size: 1.8rem;
    font-weight: 800;
    padding: 0.5rem 1.2rem;
    border-radius: 999px;
    border: 1px solid rgba(255,255,255,0.1);
    box-shadow: 0 4px 14px rgba(0,0,0,0.28);
    /* A pill's own text should never wrap internally — on a morning
       with several badges active at once (record low + AQI + garbage
       + the always-on recovery badge, a real combination confirmed
       live, not hypothetical), the row used to run out of width and
       each flex item would shrink and wrap its own text to 2 lines
       instead. That made every pill's height match whichever one
       wrapped, tallest first — including single-line ones like "AQI 2"
       — so a still-round 999px radius made them balloon into ugly
       oversized blobs instead of the slim pills they're meant to be.
       Pairs with .weather-extras' flex-wrap: wrap below, which now
       lets the whole ROW wrap onto a second line instead. */
    white-space: nowrap;
}

.weather-icon svg {
    width: 3.2rem;
    height: 3.2rem;
    display: block;
    vertical-align: middle;
}

.flag-badge svg {
    width: 4.6rem;
    height: auto;
    display: inline-block;
    border-radius: 4px;
    transition: opacity 0.6s ease;
}

.market-pill {
    display: inline-flex;
    align-items: center;
    gap: 0.6rem;
    margin-top: 0.7rem;
    padding: 0.5rem 1.1rem;
    font-size: 1.05rem;
}

.market-pill-label { color: #8E8E93; }
.market-pill-value { font-weight: 600; }
.market-up { color: #32D74B; }
.market-down { color: #FF6961; }

.market-metric {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    padding: 0.55rem 0;
    border-top: 1px solid rgba(255,255,255,0.08);
}

.market-metric-label {
    font-size: 0.85rem;
    color: #8E8E93;
}

.market-metric-value {
    font-size: 1.3rem;
    font-weight: 600;
    color: #F5F5F7;
}

/* Markets page runs up to 7 tiles in one row (see pages_markets.render)
   — the narrowest lineup any tile grid in this app uses, and its labels
   range from a single unbreakable word ("BITCOIN") to a multi-word one
   ("CRUDE OIL"). A flat nowrap+ellipsis first pass fixed BITCOIN's
   mid-word garbling under width pressure but silently truncated
   multi-word labels too — same overflow-hidden height as the shared
   .tile-label
   (multi-line-capable elsewhere, e.g. "NORTH BAY GAS"), just with
   break-word so a single long word breaks instead of overflowing the
   tile, while multi-word labels still wrap at their spaces same as
   before. Scoped rather than touching .tile-label everywhere, same
   reasoning as .prediction-side-tile's own override above. */
.market-tile .tile-label {
    overflow-wrap: break-word;
}
/* The hero % is the one number on this page that must never visually
   clip — .tile-value's fixed 2.6rem assumes room a 7-column row at
   this width doesn't have. clamp() keeps it full-size wherever there's
   space and only shrinks it as far as the tile actually needs, rather
   than a single fixed size that's right for zero tile widths. */
.market-tile .tile-value {
    font-size: clamp(1.5rem, 5.5vw, 2.6rem);
}

/* Portfolio page's Recent Activity rows — a colored category tag
   (session feedback: plain text alone didn't make a dividend read any
   differently from a withdrawal at a glance) grouped with the label so
   .market-metric's own label/value space-between layout still only
   ever sees 2 children. */
.activity-row-left {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    min-width: 0;
}
.activity-tag {
    flex-shrink: 0;
    display: inline-block;
    padding: 0.15rem 0.55rem;
    border: 1px solid currentColor;
    border-radius: 8px;
    background: rgba(255,255,255,0.04);
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    white-space: nowrap;
}
.activity-row .market-metric-label {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
/* Session request: flag anything dated today so same-day activity in
   the automated-investing accounts is answerable at a glance. Small
   and separate from the category tag's own color on purpose — this is
   a "when," not a "what," and stacking it onto the tag itself would
   blur the two together. */
.activity-today-dot {
    flex-shrink: 0;
    width: 0.55rem;
    height: 0.55rem;
    border-radius: 50%;
    background: #FF453A;
    animation: activity-today-pulse 1.6s ease-in-out infinite;
}
@keyframes activity-today-pulse {
    0%, 100% { box-shadow: 0 0 3px 1px rgba(255,69,58,0.5); opacity: 1; }
    50% { box-shadow: 0 0 9px 4px rgba(255,69,58,0.9); opacity: 0.55; }
}

.country-name {
    font-size: 1.25rem;
    color: #8E8E93;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-top: 0.25rem;
}

/* Streamlit's column row is already a flexbox, but the columns and their
   inner blocks don't stretch to a common height by default — without
   this, tiles end up as tall as their own content (varying with label
   wrap and whether "significant move" text is present), which read as
   jankily mismatched. Force the whole chain to stretch uniformly. */
[data-testid="stHorizontalBlock"] {
    align-items: stretch;
}
[data-testid="stColumn"] {
    display: flex;
    height: auto;
}
[data-testid="stColumn"] > div,
[data-testid="stColumn"] [data-testid="stVerticalBlock"],
[data-testid="stColumn"] [data-testid="stLayoutWrapper"],
[data-testid="stColumn"] [data-testid="stElementContainer"],
[data-testid="stColumn"] [data-testid="stMarkdown"],
[data-testid="stColumn"] [data-testid="stMarkdown"] > div,
[data-testid="stColumn"] .stMarkdownContainer {
    width: 100%;
    height: 100%;
    display: flex;
    flex-direction: column;
}

/* Shared "premium glass" card treatment — every panel in the app (tiles,
   the market pill, the news feed list) uses this exact recipe so the
   whole dashboard reads as one consistent surface language rather than
   a set of ad hoc boxes. The shadow is static (a fixed value, not a
   keyframe) since this app reruns its whole script every second for the
   clock tick and an animated shadow here would fight that the same way
   the old background elements did — depth without motion.

   backdrop-filter (real frosted-glass blur + saturation boost of
   whatever's actually behind the card — scenery.py's own time-of-day
   sky gradient) is the one genuinely defining trait of Apple's own
   translucent materials (Control Center, widgets, sheets) that
   nothing here had at all before; a flat semi-transparent color reads
   as "dark and see-through" but not as glass. Backed off the fill's
   own opacity (0.86 -> 0.72) specifically so there's real background
   left for the blur to actually show — at 0.86 it was nearly opaque
   already and a blur behind it would have been invisible. */
.tile, .market-pill, .news-feed-list, .score-card {
    background: rgba(12,12,16,0.72);
    backdrop-filter: blur(24px) saturate(160%);
    -webkit-backdrop-filter: blur(24px) saturate(160%);
    border: 1px solid rgba(255,255,255,0.09);
    /* Bumped from 16px — a slightly more generous, contemporary
       "squircle" curve reads closer to current Apple card surfaces
       (widgets, Health/Fitness cards) than the tighter, more
       rectangular radius this started at. */
    border-radius: 20px;
    box-shadow: 0 10px 30px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.05);
}

.tile {
    position: relative;
    display: flex;
    flex-direction: column;
    padding: 1.7rem 1.5rem 1.5rem;
    height: 100%;
    box-sizing: border-box;
    overflow: hidden;
}

/* A quiet top accent strip always reflects this tile's tone (good/bad/
   neutral/in-line) so it reads at a glance from across the room without
   needing to find and read the badge text. A "significant move" widens
   and brightens it — a static, confident cue instead of the pulsing
   glow this used to be (which just added visual noise when several
   tiles were flashing on screen at once). */
.tile::before {
    content: "";
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    background: var(--tile-accent, rgba(255,255,255,0.14));
}
.tile-accent-good { --tile-accent: #32D74B; }
.tile-accent-bad { --tile-accent: #FF6961; }
.tile-accent-neutral { --tile-accent: #5AC8FA; }
.tile-significant::before {
    height: 5px;
    box-shadow: 0 0 14px 1px var(--tile-accent, transparent);
}

.tile-label, .severity-caption {
    height: 3.1em;
    overflow: hidden;
}

/* Today page only: tiles are stacked in a single column there, not
   laid out in a grid row like Home's macro tiles — so there's no
   cross-tile alignment reason to reserve 3.1em for a label that's
   always one short line ("NORTH BAY GAS", "NEARBY · 3/5"). That fixed
   reservation, repeated across every section on an already-tall page,
   was the single biggest reason NEARBY was getting pushed off screen. */
.tile-label.compact, .severity-caption.compact {
    height: auto;
    margin-bottom: 0.3rem;
}
.tile.compact {
    padding: 0.75rem 1.1rem 0.65rem;
}

.new-badge {
    position: absolute;
    top: 0.8rem;
    right: 0.9rem;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.05em;
    color: #FFD60A;
    background: rgba(255,214,10,0.16);
    border: 1px solid rgba(255,214,10,0.3);
    border-radius: 10px;
    padding: 0.15rem 0.5rem;
}

.tile-label {
    font-size: 1rem;
    color: #ECECF1;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 0.45rem;
}

.tile-value-row {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: 0.5rem;
}

.tile-value {
    font-size: 2.6rem;
    font-weight: 600;
    color: #F5F5F7;
    letter-spacing: -0.01em;
    white-space: nowrap;
}

/* Markets has 7 columns (vs. Home's 5) — narrower tiles need a smaller
   hero value so e.g. "-24.25%" doesn't wrap onto two lines. */
.market-hero-value {
    font-size: 1.9rem;
}

.sparkline {
    width: 4.5rem;
    height: 1.75rem;
    flex-shrink: 0;
    opacity: 0.75;
    margin-bottom: 0.4rem;
}

/* Markets' 1-year sparkline gets its own full-width slot near the
   bottom of the tile instead of squeezed in next to the hero value —
   a year of daily closes needs real width to read as a shape rather
   than a squished line, and it's a headline feature of that tile, not
   a small decoration beside the price. */
.market-sparkline-wrap {
    margin-top: 0.8rem;
}
.market-sparkline-wrap .sparkline {
    width: 100%;
    height: 3.4rem;
    opacity: 0.85;
    margin-bottom: 0;
}

/* BRDN's own price-history chart — same "shared .sparkline class is
   hard-capped at the small inline-tile size" override shape as
   .market-sparkline-wrap above, just sized as this page's real
   centerpiece rather than a secondary chart lower in a tile. Session
   request: "make the price history... fit into the slide a little bit
   better." margin-bottom:0 for the same reason .market-sparkline-wrap
   sets it — the base .sparkline's own small-tile spacing has no
   business here. */
.brdn-chart-wrap .sparkline {
    width: 100%;
    height: 12rem;
    opacity: 1;
    margin-bottom: 0;
}

/* Market Internals: the Confidence Index is the headline of that page,
   not a peer to the three ratio tiles below it — a much larger value
   (bigger than the clock, since this is the one thing that page exists
   to show) and centered layout set it apart. */
.confidence-hero {
    align-items: center;
    text-align: center;
    padding-top: 1.4rem;
    padding-bottom: 1.3rem;
}
.confidence-value {
    font-size: 6.4rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    color: #F5F5F7;
    line-height: 1.1;
    margin: 0.1rem 0 0.35rem;
}
/* Session report: "reformat this page to look a lot cleaner" — this
   page is only 4 tiles total, and the 3 ratio tiles' old cramped
   1.1rem padding (deliberately more compact than the shared .tile
   padding, back when this page was still finding its own proportions)
   left a large flat dead zone below them with nothing to balance it,
   confirmed live via getBoundingClientRect: real content ended
   ~792px into a 1080px-tall viewport, meaning nearly 300px of
   unbalanced empty space at the bottom. Roomier padding plus bigger
   value/verdict type gives the row real visual weight of its own
   instead of reading like an afterthought under the hero, closing
   most of that gap as a side effect of the tiles actually filling
   their own presence rather than by fighting Streamlit's own
   block-container layout to force it. */
.internals-ratio-tile {
    padding-top: 1.9rem;
    padding-bottom: 1.9rem;
}
/* Verdict-first Internals typography — session feedback: the meaning
   has to be readable from across the room, not fine print ("super tiny
   little context bars that I cannot read unless I'm an inch away").
   The verdict word is nearly value-sized and tone-colored; the context
   line is a real sentence at readable size, replacing the old
   severity-caption small print entirely on this page. */
.internals-ratio-tile .tile-label {
    height: auto;
    font-size: 1.1rem;
}
.internals-ratio-tile .tile-value {
    font-size: 3.6rem;
}
.internals-verdict {
    font-size: 2rem;
    font-weight: 800;
    letter-spacing: 0.01em;
    line-height: 1.15;
    text-transform: uppercase;
    margin-top: 0.3rem;
}
.confidence-hero .internals-verdict {
    font-size: 2.3rem;
}
.internals-verdict-good { color: #32D74B; }
.internals-verdict-bad { color: #FF6961; }
.internals-verdict-neutral { color: #5AC8FA; }
/* Separator between the Fear & Greed hero's own band word and its
   weekly-change reading — session request: "every context label should
   have different colours attached to it," which now colors each of
   those two pieces independently (see pages_internals._render_gauge_
   hero), so the dot between them needs its own quiet, uncolored
   styling rather than inheriting either side's tone. */
.internals-verdict-sep { color: rgba(236,236,241,0.45); margin: 0 0.4rem; font-weight: 400; }
.internals-context {
    font-size: 1.25rem;
    color: #ECECF1;
    line-height: 1.45;
    margin-top: 0.6rem;
}
.confidence-hero .internals-context {
    max-width: 46rem;
}
/* Clearer separation between the hero and the supporting row than the
   old bare 0.4rem inline spacer (see pages_internals.render) gave —
   the two now read as distinct, deliberately composed sections rather
   than a hero with an afterthought crammed underneath it. */
.internals-section-gap {
    height: 1.6rem;
}

/* Predictions page — session request: "make it its own page for just
   prediction market things." Session follow-up: "don't make the BoC,
   Fed, and the other one big, make them fit into the same row...
   nice, clean format, like a list almost" — every bank, Fed/BoC/BoJ
   included, is one compact row here; there's no separate hero-tile
   treatment anymore. */
.prediction-source-note {
    font-size: 1.15rem;
    color: #8E8E93;
    margin: -0.4rem 0 0.9rem;
}
/* Scoped rather than touching the shared .tile-label everywhere else
   in the app — session request: "those small ass little titles" was
   specifically about this page's own ("ALL CENTRAL BANKS", "NEXT
   PRINT"). */
.prediction-side-tile .tile-label,
.prediction-macro-tile .tile-label {
    font-size: 1.4rem;
}

/* Session request: "CUT in ice blue, hold just normal, hike is fire
   red" — colors the DIRECTION (cut vs. hold vs. hike), not the
   specific bucket, so a -25bps and a -50bps row read as the same
   "cut" color (see prediction_markets_client.bucket_direction).
   Same fire/ice values already tuned elsewhere in this app
   (.jumbo-live-matchup-stat-hot/-cold, pages_jumbotron's batter/
   pitcher matchup card) for exactly this look, minus the pulse
   animation — a rate outlook is a stable read, not a live streak.
   "hold" gets no override at all, matching this app's own plain-white
   default everywhere else a number isn't inherently good or bad. */
.prediction-direction-cut { color: #3DD9FF; }
.prediction-direction-hike { color: #FF5A1F; }

/* Session follow-up: "I want all of the rate odds as many as you can
   find... I want them all on the side with the country name and then
   the most likely outcome and the percentage." A compact roster
   covering every bank BANKS knows about.
   Found live: the old single-column `max-height: 22rem;
   overflow-y: auto` clipped the list on the kiosk's real viewport —
   Canada and the Fed (sorted well down the list by meeting date) fell
   below the fold of a scrollbar nobody can actually operate on a
   non-interactive kiosk display, so they looked like they'd vanished.
   A 2-column grid roughly halves the row count that needs to fit
   vertically, and there's no scroll cap left to hide anything below
   the fold — every bank is always on-screen. */
.prediction-side-tile {
    max-height: 100%;
}
.prediction-side-list {
    margin-top: 0.6rem;
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    column-gap: 1.6rem;
}
/* Session request: "tighten up the rate cut prediction model thing
   because now that we're not using full central bank names, we don't
   need to have them so spaced out... make the numbers a little bigger
   too and the outcome a little bigger... make everything legible from
   a distance." The flag column used to be `1fr` (the widest slot) back
   when it held a full country name — now it's a small fixed-width icon,
   so the freed-up space goes to `outcome` (the longest real content,
   "No change") instead, and every column's own font grew along with
   the row. */
.prediction-row {
    display: grid;
    grid-template-columns: 2.6rem 4.4rem 1fr 3.2rem;
    align-items: center;
    gap: 0.6rem;
    padding: 0.5rem 0.2rem;
    font-size: 1.35rem;
    border-bottom: 1px solid rgba(255,255,255,0.06);
}
.prediction-row:last-child {
    border-bottom: none;
}
/* Session request: "instead of central banks, I just want the flags."
   Same sizing convention as .ticker-flag — a plain inline SVG has no
   intrinsic size otherwise. Sized up alongside the rest of the row
   ("make everything legible from a distance"). */
.prediction-row-country {
    display: inline-flex;
    align-items: center;
}
.prediction-row-country svg {
    width: 2.3rem;
    height: auto;
    border-radius: 2px;
}
.prediction-row-outcome {
    color: #8E8E93;
    white-space: nowrap;
    font-weight: 700;
    font-size: 1.35rem;
}
/* Compound selector, not just .prediction-direction-cut/-hike alone:
   those are the same specificity as .prediction-row-outcome above and
   lose to it on source order alone (found live — every side-list row
   was rendering gray regardless of direction until this was added). */
.prediction-row-outcome.prediction-direction-cut { color: #3DD9FF; }
.prediction-row-outcome.prediction-direction-hike { color: #FF5A1F; }
.prediction-row-pct {
    color: #F5F5F7;
    font-weight: 700;
    font-size: 1.4rem;
    text-align: right;
    font-variant-numeric: tabular-nums;
}
/* Session request: "make it known when a contract is almost up or when
   that decision is due... a number... or have it dynamically colored."
   Both: the plain day count is always shown, and its own color
   escalates as the real decision date approaches (prediction_markets_
   client.days_until_urgency) — neutral gray far out, amber within a
   week, red within a day, so the ones actually worth a glance stand
   out from the rest of the list without needing to read every number. */
.prediction-row-days {
    text-align: right;
    font-weight: 700;
    font-size: 1rem;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
}
.prediction-row-days-neutral { color: #8E8E93; }
.prediction-row-days-soon { color: #FFD60A; }
.prediction-row-days-imminent { color: #FF6961; }

/* Session follow-up: "what other markets are there... pull the
   consensus... build a forecast... estimate if it's gonna be coming in
   cooler or hotter than expected" -> "make it a big number... put it in
   a box, make it all fancy... instead of having two of them that are
   kinda random... find data for Canada as well... have the next
   closest event show up automatically... across Canada and the US."
   One hero box for whichever tracked series is soonest, not a fixed
   pair (see prediction_markets_client.next_data_series()). Reuses the
   same good/bad/neutral verdict coloring pages_internals.py already
   established (green=good, red=bad, blue=neutral) rather than the
   cut/hike fire-ice palette — this is "higher/lower than last time,"
   not a rate direction, and it matches config.py's own
   good_direction: "down" for both CPI and unemployment (cooler is the
   good outcome for both). */
.prediction-macro-tile {
    display: flex;
    flex-direction: column;
    gap: 0.7rem;
}
/* Session request: "make everything legible from a distance because
   everything is not legible from a distance, especially those small
   ass little titles." */
.prediction-macro-heading {
    font-size: 1.3rem;
    color: #8E8E93;
    text-transform: uppercase;
    letter-spacing: 0.02em;
}
.prediction-macro-box {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-top: 0.4rem;
    padding: 1.2rem 1.5rem;
    border-radius: 16px;
    border: 1px solid rgba(255,255,255,0.08);
}
.prediction-macro-number {
    font-size: 3.8rem;
    font-weight: 800;
    line-height: 1;
    font-variant-numeric: tabular-nums;
    color: #F5F5F7;
}
.prediction-macro-unit {
    font-size: 1.9rem;
    font-weight: 700;
    margin-left: 0.2rem;
    opacity: 0.75;
}
.prediction-macro-tag {
    font-size: 1.3rem;
    font-weight: 800;
    letter-spacing: 0.03em;
    text-transform: uppercase;
    padding: 0.45rem 1rem;
    border-radius: 999px;
    white-space: nowrap;
}
.prediction-macro-box-good { background: rgba(50,215,75,0.12); border-color: rgba(50,215,75,0.35); }
.prediction-macro-box-bad { background: rgba(255,105,97,0.12); border-color: rgba(255,105,97,0.35); }
.prediction-macro-box-neutral { background: rgba(90,200,250,0.12); border-color: rgba(90,200,250,0.35); }
.prediction-macro-tag-good { background: #32D74B; color: #04270c; }
.prediction-macro-tag-bad { background: #FF6961; color: #330806; }
.prediction-macro-tag-neutral { background: #5AC8FA; color: #04202c; }

/* Global Central Bank consensus (pages_predictions._global_consensus_
   html) — session request: "take the implied odds of every single
   outcome of every single central bank and make a single number...
   the central bank of the world." Reuses the same big-number-box shape
   as the NEXT PRINT hero right above these rules, but toned by rate
   direction (same #3DD9FF/#FF5A1F ice/fire values as .prediction-
   direction-cut/-hike) instead of good/bad/neutral — a rate outlook
   isn't "good or bad news" the way a hotter/cooler CPI surprise is
   (see that box's own comment for the identical reasoning). "hold" gets
   a plain neutral-gray treatment, matching this app's own "not
   inherently good or bad" default used everywhere else a hold/no-
   change reads as neither ice nor fire. */
.prediction-macro-box-cut { background: rgba(61,217,255,0.12); border-color: rgba(61,217,255,0.35); }
.prediction-macro-box-hike { background: rgba(255,90,31,0.12); border-color: rgba(255,90,31,0.35); }
.prediction-macro-box-hold { background: rgba(171,178,196,0.10); border-color: rgba(171,178,196,0.3); }
.prediction-macro-tag-cut { background: #3DD9FF; color: #032a33; }
.prediction-macro-tag-hike { background: #FF5A1F; color: #330d02; }
.prediction-macro-tag-hold { background: #ABB2C4; color: #1c1c1e; }
.prediction-global-tile { margin-top: 1.1rem; }

.tile-extra {
    margin-top: 0.5rem;
    padding-top: 0.5rem;
    height: 1.2em;
    font-size: 0.8rem;
    color: #8E8E93;
    box-sizing: content-box;
}

.tile-extra:not(:empty) {
    border-top: 1px solid rgba(255,255,255,0.08);
}

.tile-prev {
    font-size: 0.95rem;
    color: #D6D6DC;
    margin-top: 0.25rem;
}

.tile-prev.market-up { color: #32D74B; }
.tile-prev.market-down { color: #FF6961; }
.tile-value.market-up { color: #32D74B; }
.tile-value.market-down { color: #FF6961; }

.badge {
    display: inline-block;
    margin-top: 0.65rem;
    padding: 0.18rem 0.7rem;
    border-radius: 10px;
    font-size: 0.85rem;
    font-weight: 600;
    letter-spacing: 0.03em;
    text-transform: uppercase;
}

/* Audit fix: .badge-bad/.badge-neutral's own background tint used to
   be derived from a DIFFERENT hex than their text color (bad: tint
   from #FF453A, text #FF6961; neutral: tint from #0A84FF, text
   #5AC8FA) — only .badge-good actually derived its tint from its own
   text color. Now all three do, same self-consistent pattern. */
.badge-bad { background: rgba(255,105,97,0.18); color: #FF6961; }
.badge-good { background: rgba(50,215,75,0.18); color: #32D74B; }
.badge-neutral { background: rgba(90,200,250,0.14); color: #5AC8FA; }
.badge-inline { background: rgba(255,255,255,0.08); color: #D6D6DC; }

/* Rotation countdown (app.py) — deliberately quiet: a slim track at the
   very top, not another thing competing for attention with the hero
   row right below it. z-index below the night-dim overlay (20) so it
   dims along with everything else overnight, same as the ticker. */
.rotation-timer-track {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    height: 3px;
    background: rgba(255,255,255,0.08);
    z-index: 12;
}
.rotation-timer-fill {
    height: 100%;
    width: 100%;
    background: rgba(255,255,255,0.35);
    transform-origin: left;
}
/* Confirmed live (see app.py) that Streamlit patches this element's
   style attribute in place across reruns rather than replacing the
   node — so a fresh animation-delay value alone was a no-op: per the
   CSS Animations spec, mutating animation-delay on an ALREADY-RUNNING
   animation does not reposition it, only a genuinely new animation
   instance respects a new delay. That's exactly why the bar used to
   drift off the real rotation clock and stop lining up with the actual
   page flip. Fixed by alternating between two functionally identical
   keyframe animations every rerun (see _rotation_bar_class in app.py)
   — changing animation-name always forces a real restart even on the
   same node, so the freshly computed delay actually takes effect each
   time, while the browser still tweens smoothly in between reruns.
   300s in both must match config.PAGE_ROTATION_SECONDS. */
.rotation-timer-fill-a {
    animation: rotation-timer-progress-a 300s linear infinite;
}
.rotation-timer-fill-b {
    animation: rotation-timer-progress-b 300s linear infinite;
}
@keyframes rotation-timer-progress-a {
    from { transform: scaleX(0); }
    to { transform: scaleX(1); }
}
@keyframes rotation-timer-progress-b {
    from { transform: scaleX(0); }
    to { transform: scaleX(1); }
}

.ticker-bar {
    position: fixed;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 10;
    background: rgba(8,8,11,0.92);
    border-top: 1px solid rgba(255,255,255,0.08);
    padding: 0.75rem 0;
    overflow: hidden;
}

.ticker-track {
    display: flex;
    width: max-content;
    animation: ticker-scroll 55s linear infinite;
}

.ticker-content {
    display: flex;
    align-items: center;
    white-space: nowrap;
    padding-right: 2rem;
}

.ticker-item {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    font-size: 1.05rem;
    color: #C7C7CC;
    padding: 0 0.7rem;
}

.ticker-flag svg {
    width: 1.3rem;
    height: auto;
    vertical-align: middle;
    border-radius: 2px;
}

.ticker-sep {
    color: #48484A;
}

/* Live "stat" ticker items (ticker.build_market_stat_items etc.) —
   same green/up, red/down, plain/neutral language this app already
   uses everywhere else for a live value. */
.ticker-item-good {
    color: #32D74B;
    font-weight: 600;
}
.ticker-item-bad {
    color: #FF6961;
    font-weight: 600;
}
.ticker-item-neutral {
    color: #F5F5F7;
    font-weight: 600;
}
/* Session request: "color the bottom bar the same way it's colored on
   the [Predictions] page" — same fire/ice values as
   .prediction-direction-cut/-hike, not the green/red good/bad
   language above (a rate direction isn't "good or bad news" the way a
   market move is). Hold uses .ticker-item-neutral (plain white)
   already, no separate class needed. */
.ticker-item-cut { color: #3DD9FF; font-weight: 600; }
.ticker-item-hike { color: #FF5A1F; font-weight: 600; }
/* Session request: "the stock market portion should be, like,
   slashing or something" when it's trading outside its VIX-derived
   priced-in range (ticker.build_market_stat_items). A slow pulsing
   glow rather than a flat color — this fires rarely (once per
   trading day at most, see market_volatility_alert.py's own gate), so
   unlike the "too many things flashing at once" problem .tile-
   significant deliberately moved away from (see that class's own
   comment), a single animated item here has no competition. */
.ticker-item-alert {
    color: #FF453A;
    font-weight: 700;
    animation: ticker-alert-pulse 1.6s ease-in-out infinite;
}
@keyframes ticker-alert-pulse {
    0%, 100% { text-shadow: 0 0 6px rgba(255,69,58,0.55); }
    50% { text-shadow: 0 0 16px rgba(255,69,58,0.95); }
}
/* Compact "(Nd)" companion to the Predictions page's own .prediction-
   row-days badge (see its own comment) — same neutral/soon/imminent
   escalation, sized for the ticker's own smaller type instead. */
.ticker-days {
    font-weight: 700;
    font-variant-numeric: tabular-nums;
}
.ticker-days-neutral { color: #8E8E93; }
.ticker-days-soon { color: #FFD60A; }
.ticker-days-imminent { color: #FF6961; }

@keyframes ticker-scroll {
    from { transform: translateX(0); }
    to { transform: translateX(-50%); }
}

/* Breaking-news bar: takes over the same bottom strip as the release
   ticker whenever a strictly-filtered alert is active. Solid red, with
   "BREAKING NEWS" stretching into view then sliding aside to reveal the
   category tag + headline underneath. Positions are set inline per-render
   as a function of elapsed time (see news.render_alert_bar) rather than
   via CSS keyframes, since the whole app reruns every second for the
   clock tick and a keyframe would restart on every one of those reruns. */
.news-alert-bar, .news-alert-bar-market {
    position: fixed;
    left: 0;
    right: 0;
    bottom: 0;
    /* Session report: a Red Sox sac fly scored and "their alert did not
       fire" — it had, but z-index 15 sat well below the jumbotron's own
       full-screen overlays (out-of-town scoreboard 9997, play-result
       9998, transition curtain 9999, all inset:0 and effectively
       opaque). A sac fly very often ends the half-inning too, so the
       between-innings overlay was covering the whole screen right as
       the toast tried to show. This (and .commute-alert-bar/
       .sports-alert-bar-mlb/-nhl below, which share this same bottom
       strip) now sits above all of them — a real alert should never be
       able to render invisibly. */
    z-index: 10000;
    display: flex;
    align-items: center;
    gap: 1.1rem;
    padding: 0.9rem 1.5rem;
    border-top: 2px solid rgba(255,255,255,0.25);
    overflow: hidden;
}
.news-alert-bar {
    background: linear-gradient(90deg, #7a0f10 0%, #b3181a 50%, #7a0f10 100%);
    box-shadow: 0 -4px 24px rgba(179,20,20,0.35);
    /* Design-pass fix, found live: missing !important — dead against
       the global kill switch since it went in, silently undoing the
       explicit "make it so that animation happens every single time
       we have a toast alert... for every single toaster in the entire
       system" request this whole toast-pulse-* family exists for (see
       that request's own fuller comment a few rules below). Same fix
       applied to every other toast-pulse-* declaration in this file
       that was missing it. */
    animation: toast-pulse-red 1.6s ease-in-out infinite !important;
}
/* Generic market-news items aren't a surprise worth a red alert, but
   should still visibly take over the strip like breaking news does —
   solid black instead signals "new headline" without false urgency. */
.news-alert-bar-market {
    background: linear-gradient(90deg, #0a0a0c 0%, #1c1c20 50%, #0a0a0c 100%);
    box-shadow: 0 -4px 24px rgba(0,0,0,0.45);
    animation: toast-pulse-neutral 1.6s ease-in-out infinite !important;
}

/* Session request: "there is an animation for leave in alerts, but for
   some reason it's only applied in the jumbotron... I really like how
   it looks... make it so that that animation happens every single time
   we have a toast alert... for every single toaster in the entire
   system." The look in question is .jumbo-leave-ticker/.leave-headline's
   own intensity-tier glow pulse (see leave-headline-pulse* below) —
   deliberately NOT the old stretch-then-slide ENTRANCE animation
   already removed from every toast bar in this file (see
   commute_reminder.render_bar's own docstring: "get rid of the
   animation... shorten up that animation window a lot" — a real,
   live-confirmed bug where a one-shot intro tied to a freshly-appeared
   node could get killed mid-transition by Streamlit's own 5s rerun
   cycle patching content in place, making a toast intermittently
   invisible). This is a genuinely different category: a continuous,
   infinite `animation` declared directly on each bar's own static rule
   — exactly like leave-headline-pulse/jumbo-blink/weather-warning-pulse
   already are, rendered through this exact same rerun mechanism with
   no reported issue. Nothing here depends on catching a single
   "just appeared" moment; a rerun patching the node in place mid-cycle
   just means the pulse keeps looping (or at worst restarts from 0%,
   visually indistinguishable from any other frame of a symmetric
   ease-in-out pulse) — not the failure mode the old intro had at all.
   Each bar pulses its OWN existing box-shadow color, brighter and
   wider at the peak — same shape as leave-headline-pulse, just on
   box-shadow instead of text-shadow since these are solid bars, not
   bare text. One keyframe per distinct accent color already in use
   below, reused across every bar that already shares that same color
   rather than one per module. */
@keyframes toast-pulse-red {
    0%, 100% { box-shadow: 0 -4px 24px rgba(179,20,20,0.35); }
    50% { box-shadow: 0 -6px 40px rgba(179,20,20,0.65), 0 -2px 70px rgba(179,20,20,0.25); }
}
@keyframes toast-pulse-red-extreme {
    0%, 100% { box-shadow: 0 -4px 24px rgba(212,24,26,0.5); }
    50% { box-shadow: 0 -6px 44px rgba(212,24,26,0.85), 0 -2px 80px rgba(212,24,26,0.35); }
}
@keyframes toast-pulse-amber {
    0%, 100% { box-shadow: 0 -4px 24px rgba(179,142,20,0.35); }
    50% { box-shadow: 0 -6px 40px rgba(179,142,20,0.65), 0 -2px 70px rgba(179,142,20,0.25); }
}
@keyframes toast-pulse-orange {
    0%, 100% { box-shadow: 0 -4px 24px rgba(179,100,20,0.3); }
    50% { box-shadow: 0 -6px 40px rgba(179,100,20,0.6), 0 -2px 70px rgba(179,100,20,0.22); }
}
@keyframes toast-pulse-indigo {
    0%, 100% { box-shadow: 0 -4px 24px rgba(74,50,168,0.4); }
    50% { box-shadow: 0 -6px 40px rgba(74,50,168,0.7), 0 -2px 70px rgba(74,50,168,0.3); }
}
@keyframes toast-pulse-blue {
    0%, 100% { box-shadow: 0 -4px 24px rgba(26,90,179,0.4); }
    50% { box-shadow: 0 -6px 40px rgba(26,90,179,0.7), 0 -2px 70px rgba(26,90,179,0.3); }
}
@keyframes toast-pulse-gold {
    0%, 100% { box-shadow: 0 -4px 24px rgba(179,153,63,0.35); }
    50% { box-shadow: 0 -6px 40px rgba(179,153,63,0.65), 0 -2px 70px rgba(179,153,63,0.25); }
}
/* Black bg gets a neutral white/gray glow instead of a black-on-black
   pulse of its own color, which wouldn't read as anything at all. */
@keyframes toast-pulse-neutral {
    0%, 100% { box-shadow: 0 -4px 24px rgba(0,0,0,0.45); }
    50% { box-shadow: 0 -6px 40px rgba(255,255,255,0.18), 0 -2px 70px rgba(255,255,255,0.08); }
}

/* Commute reminder — same bottom-strip takeover and stretch/slide intro
   as the breaking-news bar (see commute_reminder.render_bar), but amber
   rather than red: a reminder to leave for work isn't the same kind of
   urgent as a market-moving headline, and shouldn't read as one. */
.commute-alert-bar {
    position: fixed;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 10000;  /* see .news-alert-bar's own comment above */
    display: flex;
    align-items: center;
    gap: 1.1rem;
    padding: 0.9rem 1.5rem;
    border-top: 2px solid rgba(255,255,255,0.25);
    overflow: hidden;
    background: linear-gradient(90deg, #7a4a0f 0%, #b3811a 50%, #7a4a0f 100%);
    box-shadow: 0 -4px 24px rgba(179,142,20,0.35);
    animation: toast-pulse-amber 1.6s ease-in-out infinite !important;
}

/* Important-email toasts (email_client.py) — same bottom-strip
   takeover/intro as the bars above, its own indigo so it reads as its
   own category (not urgent-red, not the commute reminder's amber, not
   any tracked team's color) at a glance. */
.email-alert-bar {
    position: fixed;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 10000;  /* see .news-alert-bar's own comment above */
    display: flex;
    align-items: center;
    gap: 1.1rem;
    padding: 0.9rem 1.5rem;
    border-top: 2px solid rgba(255,255,255,0.25);
    overflow: hidden;
    background: linear-gradient(90deg, #2f1f6e 0%, #4a32a8 50%, #2f1f6e 100%);
    box-shadow: 0 -4px 24px rgba(74,50,168,0.4);
    animation: toast-pulse-indigo 1.6s ease-in-out infinite !important;
}
/* Design-pass fix, found live: real, genuinely unbounded data (an
   email "From" display name — sports_alerts/news' own equivalent
   nowrap spans are always short fixed strings, never real variable
   text) with no overflow guard next to a sibling that DOES wrap
   normally — an unusually long sender name could crowd the subject
   text with nothing to stop it. Capped and ellipsized rather than
   left to grow unbounded in a fixed-position bottom strip. */
.email-alert-from {
    font-weight: 600;
    color: #E8E3FF;
    white-space: nowrap;
    max-width: 32%;
    overflow: hidden;
    text-overflow: ellipsis;
    flex-shrink: 0;
}

/* Jays/Habs scoring-play alerts (sports_alerts.py) — same bottom-strip
   takeover/intro as the bars above, own team color instead: Jays blue,
   Habs red (session request: "make it red i guess," same red the
   breaking-news bar already uses since that's genuinely the Canadiens'
   own color too). */
.sports-alert-bar-mlb, .sports-alert-bar-nhl, .sports-alert-bar-nfl, .sports-alert-bar-goalline, .sports-alert-bar-ufc {
    position: fixed;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 10000;  /* see .news-alert-bar's own comment in theme.py */
    display: flex;
    align-items: center;
    gap: 1.1rem;
    padding: 0.9rem 1.5rem;
    border-top: 2px solid rgba(255,255,255,0.25);
    overflow: hidden;
}
/* Goal-to-go toast (sports_alerts.py, NFL only) — session request:
   "fire off a toast and make it red... that'd be so fucking sick."
   Deliberately its own hotter red than .sports-alert-bar-nhl's own
   Habs red just below (a genuinely urgent moment should read as more
   alarmed than a routine team-color bar), and a faster pulse to match
   — same "urgency reads as both color AND motion" language the storm-
   phase Govee lighting already established elsewhere in this app. */
.sports-alert-bar-goalline {
    background: linear-gradient(90deg, #7a0000 0%, #e6180f 50%, #7a0000 100%);
    box-shadow: 0 -4px 28px rgba(230,24,15,0.55);
    animation: toast-pulse-red 1s ease-in-out infinite !important;
}
.sports-alert-bar-mlb {
    background: linear-gradient(90deg, #0f2a7a 0%, #1a5ab3 50%, #0f2a7a 100%);
    box-shadow: 0 -4px 24px rgba(26,90,179,0.4);
    animation: toast-pulse-blue 1.6s ease-in-out infinite !important;
}
.sports-alert-bar-nhl {
    background: linear-gradient(90deg, #7a0f10 0%, #b3181a 50%, #7a0f10 100%);
    box-shadow: 0 -4px 24px rgba(179,20,20,0.35);
    animation: toast-pulse-red 1.6s ease-in-out infinite !important;
}
/* Saints' own gold — real team color (ESPN's #d3bc8d), not the fixed
   FLASH_BLUE/FLASH_RED shared by every other team's non-opponent
   scoring play, since this one already IS a genuine team color. */
.sports-alert-bar-nfl {
    background: linear-gradient(90deg, #7a6a3f 0%, #b3993f 50%, #7a6a3f 100%);
    box-shadow: 0 -4px 24px rgba(179,153,63,0.35);
    animation: toast-pulse-gold 1.6s ease-in-out infinite !important;
}
/* UFC knockdown toast (ufc_client.get_new_alerts) — session follow-up:
   "I genuinely want to enjoy watching this... but I don't know how" —
   a knockdown is the one UFC moment that deserves the same "impossible
   to miss" treatment the goal-line toast above gets, not a routine
   team-color bar. Same hot corner-red the jumbotron's own fighter-a
   accent already uses (#FF3B30, see .jumbo-ufc-photo-a's own comment),
   not UFC's real black/red brand identity — this app has no license
   to reproduce that, just the same red already established elsewhere
   on this board for this exact fighter side. */
.sports-alert-bar-ufc {
    background: linear-gradient(90deg, #7a1108 0%, #cc2c1a 50%, #7a1108 100%);
    box-shadow: 0 -4px 26px rgba(204,44,26,0.45);
    animation: toast-pulse-red 1.1s ease-in-out infinite !important;
}
.sports-alert-score {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 1.5rem;
    font-weight: 800;
    color: #FFFFFF;
    flex-shrink: 0;
}
.sports-alert-score img {
    width: 2rem;
    height: 2rem;
    object-fit: contain;
}

/* Weather alert toast (weather_alerts_bar.render_alert_bar) — session
   request: "a recent special weather statement just came in but it
   didnt show as a toast alert, make sure they show up." Same bottom-
   strip takeover/intro as every other toast family above, colored per
   severity to match the persistent .weather-statement-* banner's own
   palette (see that block's own comments for the full reasoning behind
   each tier) so the toast and the banner never disagree about how
   urgent a given alert looks. */
.weather-alert-bar-extreme, .weather-alert-bar-warning, .weather-alert-bar-warning-moderate,
.weather-alert-bar-watch, .weather-alert-bar-statement {
    position: fixed;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 10000;  /* see .news-alert-bar's own comment above */
    display: flex;
    align-items: center;
    gap: 1.1rem;
    padding: 0.9rem 1.5rem;
    border-top: 2px solid rgba(255,255,255,0.25);
    overflow: hidden;
}
/* Session request: "how can we make the severe weather alerts a
   little bit more menacing... they're just on and then talking" —
   extreme/warning tiers used to share the exact same 1.6s pulse and
   plain headline size every other toast type in this app uses (a
   score update, a news headline). A faster, harder pulse plus a
   subtle shake — and bigger text — for just these two genuinely
   severe tiers, distinct from watch/statement/warning-moderate below,
   which stay at the calmer shared pace; a routine advisory shouldn't
   read as urgently as a real warning. */
/* Design-pass fix, found live: both animation lists below were
   missing !important, so the global kill switch at the top of this
   file silently beat them the entire time — the "more menacing"
   session request's own visual half (a faster/harder pulse plus a
   shake, distinct from the calmer shared toast pace) has been dead
   since that kill switch went in, even though the request's own
   comment is still right here describing it as active. */
.weather-alert-bar-extreme {
    background: linear-gradient(90deg, #5c0a0b 0%, #d4181a 50%, #5c0a0b 100%);
    box-shadow: 0 -4px 24px rgba(212,24,26,0.5);
    animation: toast-pulse-red-extreme 0.7s ease-in-out infinite, weather-menace-shake 0.35s ease-in-out infinite !important;
}
.weather-alert-bar-warning {
    background: linear-gradient(90deg, #7a0f10 0%, #b3181a 50%, #7a0f10 100%);
    box-shadow: 0 -4px 24px rgba(179,20,20,0.35);
    animation: toast-pulse-red 0.8s ease-in-out infinite, weather-menace-shake 0.4s ease-in-out infinite !important;
}
.weather-alert-bar-extreme .news-alert-headline, .weather-alert-bar-warning .news-alert-headline,
.weather-alert-bar-extreme .news-breaking-label, .weather-alert-bar-warning .news-breaking-label {
    font-size: 1.15em;
}
@keyframes weather-menace-shake {
    0%, 100% { transform: translateX(0); }
    25% { transform: translateX(-2px); }
    75% { transform: translateX(2px); }
}
/* Full-screen red pulse behind whatever page is showing — session
   request: "make it more obvious... not just a bottom strip." Created/
   removed by app.py's kioskShowMenaceOverlay, alongside the toast
   above (not instead of it) whenever a genuinely severe alert fires.
   Sits just under the toast bar's own z-index so the toast text stays
   readable on top of it; a radial gradient (transparent center, red
   edges) rather than a flat tint so it reads as an alarmed vignette
   around whatever's on screen instead of a flat color wash that would
   fight with the page's own content for contrast. pointer-events:none
   so it can never trap a touch/click on this non-interactive kiosk. */
.weather-menace-overlay {
    position: fixed;
    inset: 0;
    z-index: 9998;
    pointer-events: none;
    background: radial-gradient(ellipse at center, rgba(212,24,26,0) 45%, rgba(212,24,26,0.5) 100%);
    /* Design-pass fix, found live: missing !important, same as the
       toast bar's own weather-menace-shake right above — silently
       dead against the global kill switch this whole time despite
       app.py's kioskShowMenaceOverlay genuinely still creating/
       removing this element on every severe alert. */
    animation: weather-menace-pulse 0.9s ease-in-out infinite !important;
}
@keyframes weather-menace-pulse {
    0%, 100% { opacity: 0.55; }
    50% { opacity: 1; }
}
.weather-alert-bar-warning-moderate {
    background: linear-gradient(90deg, #7a3d10 0%, #b3641a 50%, #7a3d10 100%);
    box-shadow: 0 -4px 24px rgba(179,100,20,0.3);
    animation: toast-pulse-orange 1.6s ease-in-out infinite !important;
}
.weather-alert-bar-watch, .weather-alert-bar-statement {
    background: linear-gradient(90deg, #7a4a0f 0%, #b3811a 50%, #7a4a0f 100%);
    box-shadow: 0 -4px 24px rgba(179,142,20,0.35);
    animation: toast-pulse-amber 1.6s ease-in-out infinite !important;
}

/* Session follow-up: "make it so that the clearing [time] number sits
   where the leave in section is in the jumbotron" — used to be plain
   text tacked onto the end of .news-alert-headline's own sentence
   ("...Mattawa — clearing by 4:09 PM"), easy to miss. This is a real
   live countdown (.live-countdown, same mechanism as
   .jumbo-leave-ticker's own "Leave in") pushed to the far right of
   this bar's flex row via margin-left: auto and given its own
   pill treatment (echoing .news-alert-tag's pattern) so it reads as
   its own distinct section — same spot in the layout "Leave in"
   occupies during a takeover — rather than trailing sentence text. */
.weather-alert-countdown {
    flex-shrink: 0;
    margin-left: auto;
    font-size: 1.3rem;
    font-weight: 800;
    color: #FFFFFF;
    background: rgba(0,0,0,0.35);
    border-radius: 10px;
    padding: 0.3rem 0.9rem;
    white-space: nowrap;
}
/* Session report: "there's also a div error on it" — render_alert_bar
   (weather_alerts_bar.py) now always renders this span, even with
   nothing to show, so its real markup structure never changes shape
   between a countdown-bearing render and a plain one (that variable
   structure, not this rule, was the actual bug — see that function's
   own comment). Collapsed to nothing visible/no layout footprint when
   empty, same practical effect the old fully-omitted version had. */
.weather-alert-countdown-empty {
    padding: 0;
    margin: 0;
    background: transparent;
    min-width: 0;
}

/* Persistent top banner: holds the latest red (important) headline for
   up to TOP_ALERT_HOLD_SECONDS, or until the next one replaces it.

   position: fixed — session report: "i just got a really valuable red
   headline about the us and iran and it didnt pin to the top like it
   was supposed to." Same root cause as .leave-headline/.game-
   countdown-headline (see those own comments): this used to sit in
   normal document flow, at the very top of the page even before those
   two, so it was just as exposed — more, since it renders first — to
   .block-container's vertical-centering overflow pushing tall content
   off both the top and bottom of the viewport. Now pinned above both
   of those (it was already the topmost element in flow, so keeps that
   priority), with its own solid background already providing the
   legibility a backdrop-filter gives the other two. */
.top-alert-bar {
    position: fixed;
    top: 18px;
    left: 50%;
    transform: translateX(-50%);
    z-index: 501;
    width: min(1200px, calc(100vw - 48px));
    display: flex;
    align-items: center;
    gap: 0.9rem;
    padding: 0.7rem 1.5rem;
    border-radius: 16px;
    background: linear-gradient(90deg, #7a0f10 0%, #b3181a 50%, #7a0f10 100%);
    box-shadow: 0 2px 16px rgba(179,20,20,0.3);
}
.top-alert-dot, .weather-statement-dot {
    flex-shrink: 0;
    width: 9px;
    height: 9px;
    border-radius: 50%;
}
.top-alert-dot {
    background: #FFFFFF;
    box-shadow: 0 0 10px 2px rgba(255,255,255,0.65);
}
.top-alert-label {
    flex-shrink: 0;
    font-size: 0.95rem;
    font-weight: 800;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #FFFFFF;
}
.top-alert-headline {
    font-size: 1.05rem;
    font-weight: 600;
    color: #FFFFFF;
}

/* Weather-statement banner: an active Environment Canada alert (any
   severity — special weather statement up to warning) takes priority;
   our own extreme-heat/extreme-cold fallback only ever shows when EC has
   nothing active, so the two never appear at once.

   position: fixed — session report: "our heat warning just popped up
   and its kinda colliding with the leave in timer." Root cause: this
   was still plain in-flow content (just a margin-bottom), the one
   banner in this trio that never got the same fix .top-alert-bar/
   .leave-headline already needed for the identical problem (see their
   own comments) — it only LOOKED positioned correctly by coincidence
   of wherever it happened to fall in document flow, which put it close
   enough below the fixed .leave-headline to read as touching/colliding
   even on a rerun where they weren't truly overlapping yet (confirmed
   live: a 26px gap that reads as a collision once you add each bar's
   own blur/glow). Pinned below .leave-headline (fixed at top:88px,
   height ~85px) with the same ~21px gap already used between
   .top-alert-bar and .leave-headline themselves, so all three stack
   deterministically regardless of which combination is actually
   showing — including a breaking-news headline arriving at the same
   time as this, which is exactly the scenario being guarded against. */
.weather-statement-bar {
    position: fixed;
    top: 194px;
    left: 50%;
    transform: translateX(-50%);
    z-index: 499;
    width: min(1200px, calc(100vw - 48px));
    display: flex;
    align-items: center;
    gap: 0.9rem;
    padding: 0.5rem 1.3rem;
    border-radius: 16px;
    background: rgba(255,159,10,0.16);
    backdrop-filter: blur(24px) saturate(160%);
    -webkit-backdrop-filter: blur(24px) saturate(160%);
    border: 1px solid rgba(255,159,10,0.4);
}
.weather-statement-dot {
    background: #FF9F0A;
    box-shadow: 0 0 10px 2px rgba(255,159,10,0.55);
}
.weather-statement-label {
    flex-shrink: 0;
    font-size: 0.85rem;
    font-weight: 800;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: #FF9F0A;
}
.weather-statement-text {
    font-size: 1rem;
    font-weight: 500;
    color: #F5D6A8;
}

/* A real EC alert (extreme/warning/warning-moderate/watch/statement,
   see weather_alerts_bar._severity) overrides the muted default above
   with graduated urgency — a warning needs to actually command
   attention from across the room, not blend in at the same weight as a
   routine statement, and hazard type (not just tier) shapes how
   intense that gets: Tornado > Thunderstorm > Heat, even when two
   alerts are nominally the same tier. The manual heat/cold fallback
   bar never gets one of these classes, so it's untouched by this. */

/* Tornado/hurricane/tsunami — the single most dangerous hazard class
   EC issues, so it gets the most intense treatment on this dashboard,
   standing out even above a routine Warning for a less extreme
   hazard. Fastest pulse of the three warning-family tiers. */
.weather-statement-extreme {
    padding: 0.7rem 1.5rem;
    background: linear-gradient(90deg, #5c0a0b 0%, #d4181a 50%, #5c0a0b 100%);
    border: 1px solid rgba(255,59,48,0.9);
    box-shadow: 0 2px 20px rgba(212,24,26,0.55);
    animation: weather-warning-pulse 1.3s ease-in-out infinite;
}
.weather-statement-extreme .weather-statement-dot {
    background: #FFFFFF;
    box-shadow: 0 0 12px 3px rgba(255,255,255,0.9);
}
.weather-statement-extreme .weather-statement-label,
.weather-statement-extreme .weather-statement-text {
    color: #FFFFFF;
    font-weight: 700;
}

.weather-statement-warning {
    padding: 0.7rem 1.5rem;
    background: linear-gradient(90deg, #7a0f10 0%, #b3181a 50%, #7a0f10 100%);
    border: 1px solid rgba(255,105,97,0.6);
    box-shadow: 0 2px 16px rgba(179,20,20,0.35);
    animation: weather-warning-pulse 2.4s ease-in-out infinite;
}
.weather-statement-warning .weather-statement-dot {
    background: #FFFFFF;
    box-shadow: 0 0 10px 2px rgba(255,255,255,0.75);
}
.weather-statement-warning .weather-statement-label,
.weather-statement-warning .weather-statement-text {
    color: #FFFFFF;
}
.weather-statement-warning .weather-statement-text {
    font-weight: 600;
}
@keyframes weather-warning-pulse {
    0%, 100% { box-shadow: 0 2px 16px rgba(179,20,20,0.35); }
    50% { box-shadow: 0 2px 26px rgba(255,69,58,0.65); }
}

/* A Warning-tier heat/cold/fog-family hazard — still a real warning,
   just visually subordinate to a storm/wind/flood-type Warning at the
   same tier (see weather_alerts_bar._severity). Slowest pulse of the
   three warning-family tiers. */
.weather-statement-warning-moderate {
    padding: 0.7rem 1.5rem;
    background: linear-gradient(90deg, #7a3d10 0%, #b3641a 50%, #7a3d10 100%);
    border: 1px solid rgba(255,159,10,0.6);
    box-shadow: 0 2px 14px rgba(179,100,20,0.3);
    animation: weather-warning-pulse 3.2s ease-in-out infinite;
}
.weather-statement-warning-moderate .weather-statement-dot {
    background: #FFFFFF;
    box-shadow: 0 0 10px 2px rgba(255,255,255,0.6);
}
.weather-statement-warning-moderate .weather-statement-label,
.weather-statement-warning-moderate .weather-statement-text {
    color: #FFFFFF;
}
.weather-statement-warning-moderate .weather-statement-text {
    font-weight: 600;
}

.weather-statement-watch {
    background: rgba(255,159,10,0.3);
    border: 1px solid rgba(255,159,10,0.75);
    box-shadow: 0 0 16px rgba(255,159,10,0.3);
}
/* Audit fix: was #FFB340, a lighter amber that didn't match this
   tier's own background/border/glow (all #FF9F0A, the app's one
   established "medium/warning" amber) — the only tier in this block
   whose label color departed from its own tier's hue. */
.weather-statement-watch .weather-statement-label { color: #FF9F0A; }
.weather-statement-watch .weather-statement-text {
    color: #FFFFFF;
    font-weight: 600;
}

/* Storm-proximity countdown headline (weather_alerts_bar.
   render_storm_headline) — session request: "can we make an
   APPROACHING: and CLEARING: timer using these values pulled from the
   EC alert for ultimate transparency." Modeled directly on
   .leave-headline (the commute countdown) below — same fixed pill
   shape, same font-size/weight. Session follow-up: "make that
   'clearing in' timer and the approaching timer: red with a black
   background" — a distinct look from the white-on-red-gradient
   .weather-statement-extreme/warning banner it sits under, deliberately
   higher-contrast/starker for a countdown meant to be read at a glance.
   No graduated urgency tiers here (unlike leave-headline's calm→
   overdue) — only ever "approaching" or "leaving"/"here" (both show as
   "CLEARING IN"), severity alone sets the shade of red. Stacked below
   .weather-statement-bar (fixed at top:194, tall enough for a 2-line
   title) using the same ~106px increment already used between
   .leave-headline and .weather-statement-bar themselves — see that
   block's own comment on why this stack uses fixed offsets rather
   than dynamically reflowing around whichever subset of these is
   actually showing. */
.storm-headline {
    position: fixed;
    top: 300px;
    left: 50%;
    transform: translateX(-50%);
    z-index: 498;
    text-align: center;
    font-size: 2.6rem;
    font-weight: 800;
    letter-spacing: -0.01em;
    background: #0a0a0a;
    border-radius: 20px;
    padding: 0.5rem 1.6rem;
    color: #FF3B30;
}
.storm-headline-extreme {
    border: 1px solid rgba(255,59,48,0.9);
    box-shadow: 0 2px 24px rgba(255,59,48,0.55);
    color: #FF3B30;
    animation: weather-warning-pulse 1.3s ease-in-out infinite;
}
.storm-headline-warning {
    border: 1px solid rgba(255,105,97,0.6);
    box-shadow: 0 2px 18px rgba(255,105,97,0.35);
    color: #FF6961;
    animation: weather-warning-pulse 2.4s ease-in-out infinite;
}

/* Persistent macro-regime banner — see regime.py/regime_bar.py. Same
   dot+label+text shape as the weather-statement bar above, tone-colored
   like everything else in the app (good/bad/neutral) rather than a
   fixed color, since what this says can genuinely be favorable,
   unfavorable, or a growth/inflation-vs-risk-appetite mismatch.
   Audit finding: this sits on pages_home.py, the same page as the sky
   canvas and .morning-briefing, and had the identical light-glass-on-
   dark-assumption bug 8d8c662 fixed there — a light rgba(255,255,255,x)
   tint under real light .regime-text (#F5F5F7) only reads correctly
   assuming a dark app background, which stopped being guaranteed once
   the sky canvas could paint bright fog/snow/heat-wave behind it.
   Switched to the same dark rgba(12,12,16,x) family for the same
   "must stay legible regardless of backdrop" reason. */
.regime-bar {
    display: flex;
    align-items: center;
    gap: 0.9rem;
    padding: 0.7rem 1.5rem;
    margin-bottom: 0.9rem;
    border-radius: 16px;
    background: rgba(12,12,16,0.6);
    backdrop-filter: blur(24px) saturate(160%);
    -webkit-backdrop-filter: blur(24px) saturate(160%);
    border: 1px solid rgba(255,255,255,0.12);
}
.regime-dot {
    flex-shrink: 0;
    width: 9px;
    height: 9px;
    border-radius: 50%;
}
.regime-bar-good .regime-dot { background: #32D74B; box-shadow: 0 0 10px 2px rgba(50,215,75,0.55); }
.regime-bar-bad .regime-dot { background: #FF6961; box-shadow: 0 0 10px 2px rgba(255,105,97,0.55); }
.regime-bar-neutral .regime-dot { background: #5AC8FA; box-shadow: 0 0 10px 2px rgba(90,200,250,0.55); }
.regime-label {
    flex-shrink: 0;
    font-size: 0.85rem;
    font-weight: 800;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: #8E8E93;
}
.regime-text {
    font-size: 1.05rem;
    font-weight: 500;
    color: #F5F5F7;
}

/* Session report: "I'm still not getting any Toast alerts... it might
   be running in a refresh window... causing it to instantly die...
   get rid of the animation... shorten up that animation window a
   lot... do what you gotta do." This used to be position:absolute,
   centered over the whole bar, opacity:0 until a CSS animation
   (below, now removed) stretched it into view and slid it aside — a
   whole intro sequence whose own timing was recomputed from `elapsed`
   on every 5-second autorefresh rerun. Now it's just a normal flex
   row item next to the category tag and headline, fully visible from
   the first render — nothing to animate, nothing tied to rerun timing
   that could get stuck mid-transition or silently fail to appear. */
.news-breaking-label {
    flex-shrink: 0;
    font-size: 1.3rem;
    font-weight: 800;
    color: #FFFFFF;
    text-transform: uppercase;
    letter-spacing: 0.02em;
}

.news-alert-tag {
    flex-shrink: 0;
    font-size: 0.95rem;
    font-weight: 800;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    background: rgba(0,0,0,0.35);
    border-radius: 10px;
    padding: 0.3rem 0.75rem;
}

.news-alert-headline {
    font-size: 1.3rem;
    font-weight: 600;
    color: #FFFFFF;
}

/* Scoped to .news-alert-tag specifically — these category classes are
   reused on .news-feed-row (below) for just a left-border accent color,
   and that row must NOT pick up this solid pill background too. */
/* news.decide's AI catch-all — something genuinely breaking that
   doesn't fit any of the eight named categories below. */
.news-alert-tag.news-cat-breaking-news { background: rgba(255,105,97,0.9); color: #4d0f0d; }
.news-alert-tag.news-cat-fed-boc { background: rgba(191,90,242,0.9); color: #2b0f3d; }
.news-alert-tag.news-cat-data-surprise { background: rgba(90,200,250,0.9); color: #0a2c3d; }
.news-alert-tag.news-cat-earnings { background: rgba(50,215,75,0.9); color: #0b2b12; }
.news-alert-tag.news-cat-macro-shock { background: rgba(255,255,255,0.9); color: #7a0f10; }
.news-alert-tag.news-cat-market-news { background: rgba(255,214,10,0.9); color: #4d3c00; }
.news-alert-tag.news-cat-mergers { background: rgba(255,159,10,0.9); color: #4d2c00; }
.news-alert-tag.news-cat-milestone { background: rgba(100,210,255,0.9); color: #0a2c3d; }
.news-alert-tag.news-cat-tariffs { background: rgba(88,86,214,0.9); color: #17153d; }
/* Same blue as the Predictions page's own beacon (page-title-
   predictions) — a rate-odds swing toast and the page it came from
   should read as visually related. */
.news-alert-tag.news-cat-rate-odds { background: rgba(10,132,255,0.9); color: #002447; }
/* Deliberately a deeper, more saturated red than breaking-news/severe-
   weather's shared coral (rgba(255,105,97,...)) — session request
   added this category specifically because a real war/military-strike
   headline reads as more severe than an ordinary breaking story, and
   sharing the exact same color would erase that distinction at a
   glance. */
.news-alert-tag.news-cat-conflict { background: rgba(215,0,21,0.9); color: #ffd6d2; }
.news-alert-tag.news-cat-severe-weather { background: rgba(255,105,97,0.9); color: #4d0f0d; }
.news-alert-tag.news-cat-weather-tracking { background: rgba(100,210,255,0.9); color: #0a2c3d; }

.severity-track {
    position: relative;
    margin-top: 0.55rem;
    height: 6px;
    width: 100%;
    background: rgba(255,255,255,0.14);
    border-radius: 3px;
    overflow: hidden;
}

.severity-fill {
    position: absolute;
    top: 0;
    bottom: 0;
    border-radius: 3px;
}

.severity-fill-bad { background: #FF6961; }
.severity-fill-good { background: #32D74B; }
.severity-fill-neutral { background: #5AC8FA; }
.severity-fill-inline { background: #AEAEB2; }
/* Amber middle tier — added for pages_maintenance's Groq token-budget
   bars (good/medium/low, matching ai-status-dot's own three-tone
   language), a distinction the original bad/good/neutral set never
   needed before. */
.severity-fill-medium { background: #FF9F0A; }

.severity-caption {
    margin-top: 0.4rem;
    font-size: 0.85rem;
    color: #D6D6DC;
}

.page-title {
    text-align: center;
    font-size: 1.4rem;
    font-weight: 600;
    color: #F5F5F7;
    letter-spacing: -0.01em;
    margin: 0.2rem 0 0.5rem;
}

/* A small colored beacon per page — same "quiet color cue" language as
   the tile accent strips and the alert-bar dots, here used for
   wayfinding: a glance tells you which page you're on even mid-blink,
   without reading the title text. Home has no page-title (it shows the
   country flag/name instead), so it doesn't need one. */
.page-title::before {
    content: "";
    display: inline-block;
    width: 9px;
    height: 9px;
    border-radius: 3px;
    margin-right: 0.6rem;
    vertical-align: middle;
    margin-bottom: 0.15em;
}
.page-title-conflicts::before {
    background: #FF6961;
    box-shadow: 0 0 8px 1px rgba(255,105,97,0.5);
}
.page-title-news::before {
    background: #FFD60A;
    box-shadow: 0 0 8px 1px rgba(255,214,10,0.5);
}
.page-title-email::before {
    background: #9F7AEA;
    box-shadow: 0 0 8px 1px rgba(159,122,234,0.5);
}
.page-title-markets::before {
    background: #32D74B;
    box-shadow: 0 0 8px 1px rgba(50,215,75,0.5);
}
.page-title-internals::before {
    background: #BF5AF2;
    box-shadow: 0 0 8px 1px rgba(191,90,242,0.5);
}
.page-title-today::before {
    background: #FF9F0A;
    box-shadow: 0 0 8px 1px rgba(255,159,10,0.5);
}
.page-title-household::before {
    background: #A2845E;
    box-shadow: 0 0 8px 1px rgba(162,132,94,0.5);
}
.page-title-weather::before {
    background: #64D2FF;
    box-shadow: 0 0 8px 1px rgba(100,210,255,0.5);
}
/* Was #32D74B, same green as Markets' beacon and as this app's
   general "good/market-up" green everywhere else — the whole point of
   a page beacon is telling pages apart at a glance, which doesn't
   work when two share a color. Indigo isn't used as a beacon or a
   semantic color anywhere else in the app. */
.page-title-sports::before {
    background: #5E5CE6;
    box-shadow: 0 0 8px 1px rgba(94,92,230,0.5);
}
.page-title-hourly::before {
    background: #FF375F;
    box-shadow: 0 0 8px 1px rgba(255,55,95,0.5);
}
/* Reinstated page (see pages_radar.py) — needs its own color distinct
   from every page already using one, Hourly (#FF375F) included, which
   inherited this exact slot when it replaced the old Radar page; the
   whole point of a page beacon is telling pages apart at a glance,
   which breaks the moment two share a color. */
.page-title-radar::before {
    background: #32ADE6;
    box-shadow: 0 0 8px 1px rgba(50,173,230,0.5);
}
.page-title-scores::before {
    background: #30D5C8;
    box-shadow: 0 0 8px 1px rgba(48,213,200,0.5);
}
.page-title-portfolio::before {
    background: #A78BFA;
    box-shadow: 0 0 8px 1px rgba(167,139,250,0.5);
}
.page-title-predictions::before {
    background: #0A84FF;
    box-shadow: 0 0 8px 1px rgba(10,132,255,0.5);
}
/* Deliberately muted grey rather than another vibrant page color —
   this page isn't part of the normal rotation (see pages_maintenance's
   own docstring), so its beacon reads as "utility/diagnostic," not
   "just another content page." */
.page-title-maintenance::before {
    background: #8E8E93;
    box-shadow: 0 0 8px 1px rgba(142,142,147,0.5);
}
/* Session request: "make the today page a page that actually cycles
   through" — pages_timeline.py joined config.PAGES for real, so it
   needs the same wayfinding beacon every other rotation page has.
   Design-pass fix, found live: originally #FF2D55 (rose), claimed
   "distinct from every beacon already claimed above" — it wasn't.
   Euclidean RGB distance to Hourly's #FF375F was ~14, the closest
   pair of all 15 rotation beacons, closer than the Sports/Markets
   green collision a different comment above says was deliberately
   fixed for this exact reason. #00C7BE (mint) instead — checked
   against the full existing palette this time, ~51 to its nearest
   neighbor (Scores), genuinely distinguishable at a glance. */
.page-title-timeline::before {
    background: #00C7BE;
    box-shadow: 0 0 8px 1px rgba(0,199,190,0.5);
}
/* pages_system_health.py — session request: "a page that rotates
   through... derives one score on how the dashboard is doing." Lime
   rather than another blue/teal (already crowded: Weather, Radar,
   Scores, Timeline) or Maintenance's own muted grey (this page IS part
   of the normal rotation, unlike that one — it should read as "alive,"
   not "utility"). Checked against the full existing palette the same
   way Timeline's own fix above was: ~79 to its nearest neighbor (News),
   comfortably clear of the ~14-unit near-collision that was a real bug. */
.page-title-system-health::before {
    background: #B4E61D;
    box-shadow: 0 0 8px 1px rgba(180,230,29,0.5);
}

/* pages_maintenance.py — session request: "add a maintenance tab...
   that shows stats on how everything is updating... all colour coded
   to show how the board is performing." Rows reuse the tile/tile-label
   shape the rest of the app already uses (see .tile above) rather than
   inventing a new card style, just with a compact label+pill+meta row
   layout inside. */
.maint-tile {
    padding: 0.9rem 1rem;
}
.maint-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
    padding: 0.35rem 0;
    border-bottom: 1px solid rgba(255,255,255,0.06);
}
.maint-row:last-child {
    border-bottom: none;
}
.maint-row-label {
    font-size: 0.85rem;
    color: #D6D6DC;
    flex-shrink: 0;
}
.maint-row-meta {
    font-size: 0.78rem;
    color: #8E8E93;
    text-align: right;
    white-space: nowrap;
}
.maint-pill {
    font-size: 0.72rem;
    font-weight: 600;
    padding: 0.15rem 0.55rem;
    border-radius: 8px;
    white-space: nowrap;
}
/* Same four-tone language as the AI status badge's own dots
   (ai-status-dot-good/medium/low/neutral) — one shared color
   vocabulary for "how healthy is this" everywhere in the app rather
   than a page-specific palette. */
.maint-pill-good { background: rgba(50,215,75,0.18); color: #32D74B; }
.maint-pill-medium { background: rgba(255,159,10,0.18); color: #FF9F0A; }
.maint-pill-low { background: rgba(255,105,97,0.18); color: #FF6961; }
.maint-pill-neutral { background: rgba(90,200,250,0.14); color: #5AC8FA; }

/* Dashboard Pulse tile's own rerun-duration history — session
   request: "like an actual heart rate monitor." Plain height/color
   bars, deliberately no animation (the blanket kill-switch above
   already covers this; not carving out a third exception here since
   the color + exact-seconds tooltip already say everything the motion
   would, per this session's own "no decorative chrome" precedent). */
.maint-pulse-sparkline {
    display: flex;
    align-items: flex-end;
    gap: 3px;
    height: 36px;
    margin-top: 0.4rem;
}
.maint-pulse-bar {
    flex: 1 1 0;
    min-width: 3px;
    border-radius: 2px 2px 0 0;
}
.maint-pulse-bar-good { background: #32D74B; }
.maint-pulse-bar-medium { background: #FF9F0A; }
.maint-pulse-bar-low { background: #FF6961; }

/* pages_system_health.py's own hero tile — the composite score plus
   its history sparkline, deliberately the widest/tallest single tile
   on the page (same "hero" weight the score gets in the layout, not
   just visually) since it's the one number the whole page exists to
   answer. Everything below it (kiosk/pulse/data-source vitals, the
   issues list) reuses the plain .tile/.maint-row/.maint-pill language
   already established rather than inventing a second visual system.
   Padding is deliberately its own value, not .tile's default 1.7rem
   1.5rem 1.5rem or .maint-tile's tighter 0.9rem 1rem — the hero holds
   more distinct content (a huge number, a meta column, a full-width
   sparkline) than either of those two shapes were sized for, and this
   splits the difference so the sparkline gets real width without the
   tile reading as tall as a full .tile padding would make it. */
.system-health-hero {
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
    padding: 1.1rem 1.4rem;
}
.system-health-score-row {
    display: flex;
    align-items: center;
    gap: 1.1rem;
}
.system-health-score-number {
    font-size: 3.4rem;
    font-weight: 800;
    line-height: 1;
    font-variant-numeric: tabular-nums;
}
.system-health-score-good { color: #32D74B; }
.system-health-score-medium { color: #FF9F0A; }
.system-health-score-low { color: #FF6961; }
/* Audit fix: a real bug, not just polish — flex-direction:column's
   default align-items is stretch, so the grade .maint-pill inside
   (an inline-shaped tag everywhere else it's used, always sitting in a
   ROW-flex parent) was stretching to the full width of this column
   instead of shrink-wrapping to its own text, the only place in the
   app .maint-pill sits inside a column instead of a row. */
.system-health-score-meta {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 0.3rem;
}
.system-health-history {
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
}
.system-health-history .sparkline {
    width: 100%;
    height: 54px;
    opacity: 1;
    margin-bottom: 0;
}
.system-health-history-caption {
    font-size: 0.78rem;
    color: #8E8E93;
}

/* Session request, after the vitals row's original small maint-row
   text (label + a small colored pill, same dense style pages_
   maintenance.py's own diagnostics grid uses): "make it visible and
   digestible from a distance... I don't have to read." A pill you have
   to read the text of isn't glanceable across a room the way a big
   number and a one-word label under it is — same "big value, small
   caption" shape this app already uses everywhere something's meant
   to be read at a glance (.tile-value, .market-hero-value, the score
   hero just above), just applied to the kiosk/network/dashboard vitals
   too now. Color alone (not a status word) carries good/low, so the
   glance doesn't need to parse text to know something's wrong. */
.system-health-stat-row {
    display: flex;
    justify-content: space-around;
    align-items: flex-end;
    gap: 0.4rem;
    padding-top: 0.2rem;
}
.system-health-stat {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.2rem;
}
.system-health-stat-value {
    font-size: 2.3rem;
    font-weight: 800;
    line-height: 1;
    font-variant-numeric: tabular-nums;
    color: #F5F5F7;
}
.system-health-stat-good { color: #32D74B; }
.system-health-stat-medium { color: #FF9F0A; }
.system-health-stat-low { color: #FF6961; }
.system-health-stat-neutral { color: #8E8E93; }
/* Audit fix: matches .form-strip-label/.sports-blurb-label/.weather-
   day-period-label exactly (same "small uppercase caption under a
   value" role, already established in 3 other places) — this one had
   drifted to its own one-off size/weight/color on all 3 axes at once. */
.system-health-stat-label {
    font-size: 0.75rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: #8E8E93;
}

/* Team + opponent logos (sports_client.py — MLB's static logo CDN and
   NHL's, both free, no key, keyed by team id/abbrev with no API call
   needed to look one up). object-fit:contain since these come in a mix
   of aspect ratios (MLB's are roughly square, NHL's vary team to team)
   and a stretched logo would look broken immediately. */
.sports-team-header {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    margin-bottom: 0.45rem;
}
.sports-team-header .tile-label {
    margin-bottom: 0;
}
.sports-team-logo {
    width: 2.2rem;
    height: 2.2rem;
    object-fit: contain;
    flex-shrink: 0;
}
.sports-opponent-logo {
    width: 1.5rem;
    height: 1.5rem;
    object-fit: contain;
    vertical-align: middle;
    margin-right: 0.4rem;
}

/* Recent-form strip — last 10 completed games' W/L, one glance instead
   of reading the standings' win/loss totals. Same green/red language
   badge-good/badge-bad already use elsewhere on this kiosk. */
.form-strip {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 0.3rem;
    margin-top: 0.7rem;
    padding-top: 0.6rem;
    border-top: 1px solid rgba(255,255,255,0.08);
}
.form-strip-label {
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: #8E8E93;
    margin-right: 0.4rem;
}
.form-dot {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 1.3rem;
    height: 1.3rem;
    border-radius: 4px;
    font-size: 0.7rem;
    font-weight: 800;
}
.form-dot-win { background: rgba(50,215,75,0.18); color: #32D74B; }
.form-dot-loss { background: rgba(255,69,58,0.18); color: #FF6961; }

/* Sports page's per-team division standings — a plain aligned table,
   own team's row picked out rather than colored (rank order already
   says everything a color would), matching the "quiet color cue,
   readable text does the rest" language the rest of this app uses. */
.sports-standings {
    margin-top: 0.9rem;
    padding-top: 0.7rem;
    border-top: 1px solid rgba(255,255,255,0.08);
}
.sports-standings-row {
    display: flex;
    align-items: baseline;
    gap: 0.7rem;
    padding: 0.3rem 0;
    font-size: 0.95rem;
    color: #8E8E93;
}
.sports-standings-row-team {
    color: #F5F5F7;
    font-weight: 700;
}
.sports-standings-rank {
    width: 1.6rem;
    flex-shrink: 0;
}
.sports-standings-team {
    flex: 1;
}
.sports-standings-record {
    flex-shrink: 0;
}
.sports-standings-extra {
    flex-shrink: 0;
    width: 3rem;
    text-align: right;
    color: #8E8E93;
}
/* Session request: "playoff odds for each of my teams... where's the
   playoff odds on both pages" — only ever present on our own team's
   row (see _standings_table's own comment), never competing with
   .sports-standings-extra on every other row in the division. */
.sports-standings-odds { flex-shrink: 0; text-align: right; color: #64D2FF; font-weight: 700; }
/* Compact suffix on the team header line (division / vs opponent) —
   same idea as the standings row above, just for the tile header. */
.sports-odds-badge { color: #64D2FF; font-weight: 700; }

/* Session request: "make a pre and postgame ai overview... use gemini"
   then "where's... the ai blurb on the main page" — same feature as
   the jumbotron's own .jumbo-blurb, restyled for this page's plain
   tile look instead of the jumbotron's bordered-panel one. */
.sports-blurb {
    margin-top: 0.7rem;
    padding-top: 0.6rem;
    border-top: 1px solid rgba(255,255,255,0.08);
}
.sports-blurb-label {
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: #8E8E93;
    margin-bottom: 0.3rem;
}
.sports-blurb-text { font-size: 0.95rem; line-height: 1.5; color: #F5F5F7; }

/* Scores page — a whole league's slate can run to 15 games (MLB), too
   many for st.columns to lay out sensibly at kiosk width, so this is a
   plain CSS grid instead: as many cards per row as comfortably fit,
   wrapping on its own rather than a fixed column count. */
.scores-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
    gap: 0.9rem;
}
.score-card {
    padding: 0.9rem 1.1rem;
}
.score-card-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.3rem 0;
}
.score-card-team {
    display: flex;
    align-items: center;
    gap: 0.55rem;
    min-width: 0;
}
.score-card-logo {
    width: 1.9rem;
    height: 1.9rem;
    object-fit: contain;
    flex-shrink: 0;
}
.score-card-abbr {
    font-weight: 700;
    font-size: 1.05rem;
    color: #F5F5F7;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.score-card-record {
    font-size: 0.75rem;
    font-weight: 500;
    color: #8E8E93;
    margin-left: 0.35rem;
}
.score-card-value {
    font-weight: 800;
    font-size: 1.3rem;
    color: #F5F5F7;
    flex-shrink: 0;
    margin-left: 0.6rem;
}
.score-card-winner .score-card-abbr,
.score-card-winner .score-card-value {
    color: #32D74B;
}
/* That game's standout performer (see scores_client.game_leader) —
   real box-score color, not just the bare score. Single line, clipped
   rather than wrapped: a long stat line ("3-4, 2 HR, 2B, 3 RBI, 2 R")
   shouldn't be able to stretch or break this grid's compact card. */
.score-card-leader {
    margin-top: 0.4rem;
    padding-top: 0.4rem;
    border-top: 1px solid rgba(255,255,255,0.06);
    font-size: 0.78rem;
    color: #8E8E93;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.score-card-status {
    margin-top: 0.5rem;
    padding-top: 0.5rem;
    border-top: 1px solid rgba(255,255,255,0.08);
    font-size: 0.85rem;
    color: #8E8E93;
    text-align: center;
}
.score-card-status-live {
    color: #FF6961;
    font-weight: 700;
}

/* Sports page's live scoreboard — session request: "during a game the
   sports page turns into a full comprehensive scoreboard." A live
   team's tile stretches full width (see pages_sports.py's live_entries
   split) for a big score with both logos plus situational detail,
   rather than staying boxed into the normal 2-column half. */
.live-scoreboard-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.8rem;
}
.live-scoreboard-badge {
    color: #FF6961;
    font-weight: 800;
    font-size: 0.85rem;
    letter-spacing: 0.04em;
}
/* The headline element of a live tile — session feedback: "a big score
   with both team logos" in place of the small inning-by-inning table
   this used to lead with, same "readable from across the room"
   priority as this kiosk's other hero numbers. */
.live-score-hero {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 1.5rem;
    margin: 1rem 0 0.6rem;
}
.live-score-hero img {
    width: 4.5rem;
    height: 4.5rem;
    object-fit: contain;
    flex-shrink: 0;
}
.live-score-hero-value {
    font-size: 3.4rem;
    font-weight: 800;
    color: #F5F5F7;
    line-height: 1;
}
.live-score-hero-sep {
    margin: 0 0.5rem;
    color: #8E8E93;
}
/* Situation panel — current count/outs/baserunners (MLB) or
   period-clock (NHL), directly below the score hero. */
.game-situation {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.5rem 1.4rem;
    margin-top: 0.8rem;
    padding-top: 0.7rem;
    border-top: 1px solid rgba(255,255,255,0.08);
    font-size: 0.95rem;
    color: #8E8E93;
}
.game-situation strong {
    color: #F5F5F7;
}
/* 2nd top-center, 3rd/1st bottom corners — same orientation as a
   broadcast center-field camera, the view anyone already knows. */
.base-diamond {
    display: inline-grid;
    grid-template-columns: repeat(3, 0.7rem);
    grid-template-rows: repeat(2, 0.7rem);
    gap: 0.15rem;
    vertical-align: middle;
}
.base-diamond span {
    width: 0.65rem;
    height: 0.65rem;
    border: 1.5px solid #8E8E93;
    transform: rotate(45deg);
}
.base-diamond span.base-on {
    background: #FFD60A;
    border-color: #FFD60A;
}
.base-second { grid-column: 2; grid-row: 1; }
.base-third { grid-column: 1; grid-row: 2; }
.base-first { grid-column: 3; grid-row: 2; }

/* Weather page's 7 day columns — icon + high/low is the headline (same
   glance-from-across-the-room priority as everything else here), the
   short condition text a secondary caption underneath. */
.weather-day-tile {
    align-items: center;
    text-align: center;
}
.weather-day-icon svg {
    width: 3rem;
    height: 3rem;
    display: block;
    margin: 0.3rem 0;
    color: #8E8E93;
}
.weather-day-temps {
    display: flex;
    gap: 0.6rem;
    align-items: baseline;
    margin: 0.2rem 0 0.5rem;
}
.weather-day-high {
    font-size: 1.9rem;
    font-weight: 700;
    color: #F5F5F7;
}
.weather-day-low {
    font-size: 1.3rem;
    font-weight: 500;
    color: #8E8E93;
}
.weather-day-summary {
    text-align: center;
    font-size: 0.85rem;
}

/* Day/Night sub-rows within each day column — precip chance and UV
   only render at all when EC's forecast actually has one (see
   ec_forecast._period_html), so a quiet dry day doesn't carry empty
   badges just to keep row heights matching. */
.weather-day-period {
    width: 100%;
    margin-top: 0.6rem;
    padding-top: 0.5rem;
    border-top: 1px solid rgba(255,255,255,0.08);
}
.weather-day-period-label {
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    color: #8E8E93;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.4rem;
}
.weather-day-chance {
    color: #64D2FF;
    font-weight: 700;
}
.weather-day-uv {
    color: #FFB340;
    font-weight: 700;
}
.weather-day-wind {
    font-size: 0.78rem;
    color: #8E8E93;
    margin-top: 0.25rem;
}

/* EC's own live station reading, distinct from the hero row's
   Open-Meteo one — a wide single-row strip rather than another
   grid tile, since it's one reading, not a set of comparable columns. */
.weather-current-tile {
    padding: 1rem 1.5rem;
}
.weather-current-row {
    display: flex;
    align-items: center;
    gap: 1.2rem;
    flex-wrap: wrap;
}
.weather-current-icon svg {
    width: 2.6rem;
    height: 2.6rem;
    color: #8E8E93;
    flex-shrink: 0;
}
.weather-current-temp {
    font-size: 2.2rem;
    font-weight: 700;
    color: #F5F5F7;
    flex-shrink: 0;
}
.weather-current-condition {
    font-size: 1.1rem;
    color: #D6D6DC;
    flex-shrink: 0;
}
.weather-current-metrics {
    display: flex;
    gap: 1.4rem;
    flex-wrap: wrap;
    margin-left: auto;
    font-size: 0.9rem;
    color: #8E8E93;
}

/* Radar page (pages_radar.py, radar_client.py) — reinstated at the
   user's own later request ("reinstate the radar page... make the
   radar nice and big so it's scannable from a distance") once
   RainViewer gave a source they actually like the animation/look of.
   RainViewer's own tile is a fixed square (unlike the old EC WMS
   fetch, which could ask for any custom aspect ratio) — a plain
   square frame here, not the old 2.5:1 wide one, since the image
   itself is square this time. */
/* Session report: "it's just a little box inside of a bigger box...
   the box is also huge, so I can't see the clock, and I can't see the
   weather." this tile used to be a plain flex child, which stretches
   to its parent COLUMN's full width by default (Streamlit's own
   layout, not this app's choice) — with the frame itself capped
   narrower than that by the vh budget below, the dark .tile background
   (border, radius, the works) ended up visibly bigger than the actual
   radar square floating centered inside it. width: fit-content makes
   the tile itself shrink-wrap to whatever size the frame actually
   resolves to, so the visible dark card IS the radar, edge to edge,
   not a bigger frame around a smaller one. (display: flex, not the
   default inline-flex a bare width: fit-content would fall back to,
   so align-items/text-align keep behaving as expected; margin: 0 auto
   keeps the now-narrower tile centered in its column.) */
.weather-radar-tile-large {
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    width: fit-content;
    max-width: 100%;
    margin: 0 auto;
    padding: 0.7rem 0.8rem 0.6rem;
}
.weather-radar-frame {
    position: relative;
    width: 100%;
    aspect-ratio: 1 / 1;
    border-radius: 12px;
    overflow: hidden;
    background: #0a1420;
}
/* Sizing technique (constrain *width* via min() against a vh budget,
   let aspect-ratio derive a matching height) is the old radar page's
   own hard-won fix — see git history around 100fddd^ for the full
   story: fighting max-height directly stretched the image instead of
   shrinking it proportionally, and a single fixed vh value doesn't
   survive every real screen (a shorter kiosk vs. a taller one, an
   active alert banner growing the header above this tile on a given
   day and not another). min(90vw, ...) — 90vw is just a safety
   ceiling for a genuinely narrow/portrait screen; the vh term is what
   actually decides the size almost everywhere real. Deliberately
   AFTER the plain .weather-radar-frame rule above — same-specificity
   classes on one element, so source order decides the winner, and
   this needs to win.

   58vh short-tier / 88vh tall-tier — session request: "makes the
   radar much, much, much bigger... you should be able to see it all
   on the radar page." A minute-by-minute rain nowcast briefly lived
   on this page too, as its own tile beside the map (see git history)
   — pulled back out to a hero badge (app.py) at the same request,
   specifically freeing this page to spend its whole budget on the map
   alone rather than sharing it with anything else. RainViewer's own
   tile tops out at 512 real pixels regardless of how large this
   renders it (see radar_client.TILE_SIZE) — a ~1.5-1.7x upscale at
   these sizes on a real kiosk screen, soft but not unreasonably so at
   actual kiosk viewing distance, and the honest ceiling of what their
   free tier can provide at any size. */
.weather-radar-frame-large {
    width: min(90vw, 40vh);
}
@media (min-height: 850px) {
    .weather-radar-frame-large {
        width: min(90vw, 60vh);
    }
}
/* Every frame is stacked full-bleed on top of the others (see pages_
   radar.py) — app.py's own kioskRadarAnim script (persistent, same
   inject-into-the-parent-document pattern as every other kiosk-*
   script there) cycles which one is opacity:1 on a timer, so animating
   is just a client-side toggle between already-loaded real <img> tags,
   never a re-fetch. First frame visible by default (before that script
   has run its first tick yet) so there's a real image on screen
   immediately rather than a blank frame for one animation interval. */
.weather-radar-frame-img {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    object-fit: cover;
    opacity: 0;
    transition: opacity 0.35s ease;
}
.weather-radar-frame-img:first-child { opacity: 1; }
/* Blue dot for "this is you," fixed at the frame's own dead center —
   RainViewer's lat/lon tile endpoint always centers the requested
   point exactly, so (unlike a raw x/y/z slippy tile) this never needs
   per-frame pixel math, same "symmetric request = always 50%/50%"
   principle the old EC radar page's own bbox already established.
   Sized up and given a real white ring (was a plain 10px dot with no
   border) — "nice and big... scannable from a distance" applies to
   the marker too, not just the map itself, and a bare dot the same
   size as before would get lost against RainViewer's own busier,
   more colorful default palette. */
.weather-radar-marker {
    position: absolute;
    top: 50%;
    left: 50%;
    width: 16px;
    height: 16px;
    margin: -8px 0 0 -8px;
    border-radius: 50%;
    background: #64D2FF;
    border: 2px solid rgba(255,255,255,0.9);
    box-shadow: 0 0 12px 3px rgba(100,210,255,0.75);
    z-index: 2;
}
/* Session request: "does RainViewer offer timestamps for their
   radar? it's cool, but it's hard to tell when each frame is." A
   small pill in the frame's own top-left corner (same dark-glass badge
   language as .weather-extra/.news-alert-tag elsewhere), updated by
   app.py's kioskRadarAnim script every tick to name whichever frame is
   actually on screen right now — never a separately-ticking clock. */
.weather-radar-timestamp {
    position: absolute;
    top: 10px;
    left: 10px;
    z-index: 2;
    font-size: 0.85rem;
    font-weight: 700;
    color: #F5F5F7;
    background: rgba(0,0,0,0.55);
    backdrop-filter: blur(6px);
    -webkit-backdrop-filter: blur(6px);
    border: 1px solid rgba(255,255,255,0.15);
    border-radius: 8px;
    padding: 0.25rem 0.55rem;
    letter-spacing: 0.01em;
}

/* RainViewer's own free-tier terms require visible attribution —
   small and quiet on purpose (this is a credit, not content), same
   weight/treatment as .prediction-source-note elsewhere. */
.weather-radar-credit {
    font-size: 0.75rem;
    color: #8E8E93;
    margin-top: 0.6rem;
}

/* Hourly Forecast page (see pages_hourly.py) — replaces the live radar
   map at the user's own request ("get rid of radar and replace it with
   hourly weather data"). Same "one tile per period" column shape
   pages_weather.py's own 7-day row already uses, just sized for a
   HOURS_SHOWN-wide row instead of a week-wide one. */
.hourly-tile {
    align-items: center;
    text-align: center;
}
.hourly-icon svg {
    width: 2.4rem;
    height: 2.4rem;
    display: block;
    margin: 0.3rem 0;
    color: #8E8E93;
}
.hourly-temp {
    font-size: 1.6rem;
    font-weight: 700;
    color: #F5F5F7;
    margin: 0.1rem 0 0.2rem;
}
/* EC's own real hourly condition wording ("Mainly cloudy," "A mix of
   sun and cloud") — session follow-up: "make it look better and a
   little more complete." Same "trust the real sentence over a
   synthesized label" preference this app already applies elsewhere
   (jumbotron scoring-play text, pitcher line summaries). Fixed height
   at this small size comfortably fits EC's longer real phrases across
   two lines without pushing the wind/precip rows below it out of
   alignment between columns. */
.hourly-condition {
    font-size: 0.78rem;
    color: #8E8E93;
    line-height: 1.25;
    min-height: 2em;
    margin-bottom: 0.3rem;
}
/* Only rendered at all when EC's own hourly likelihood-of-precipitation
   reading is a real, non-zero chance (see pages_hourly.render's own
   comment on why this needs an explicit ">0" check rather than the
   daily forecast's "is not None" one). */
.hourly-chance {
    color: #64D2FF;
    font-weight: 700;
    font-size: 0.85rem;
}
.hourly-wind {
    font-size: 0.78rem;
    color: #8E8E93;
    margin-top: 0.25rem;
}
/* The soonest real hourly reading — this page's own version of "the one
   that matters right now" other live boards in this app already
   highlight (the jumbotron's current-batter row, the Fear & Greed
   gauge's own accent). box-sizing: border-box on just this one tile
   (not the whole .hourly-tile rule) so its border eats into the tile's
   own content space instead of adding to its outer width — a plain
   negative-margin bleed was tried elsewhere this session for a similar
   highlight and measured live to actually overflow past its real
   container edge; this avoids that same mistake outright rather than
   repeating it. */
.hourly-tile-now {
    box-sizing: border-box;
    border: 2px solid #FFB300;
    background: rgba(255,179,0,0.08);
}
.hourly-tile-now .tile-label {
    color: #FFB300;
}

/* .conflict-headlines/.conflict-headline (the raw sourced-headline list
   under each tile) were removed along with their markup in
   pages_conflicts.render() — session request: "hide the rss feed but
   let the ai see them for the conflict recap." .conflict-headline-
   recent below was already unused before that (references a since-
   removed _ai_summary function), left alone as pre-existing, unrelated
   debt rather than folded into this change. */
/* Same red as badge-bad/tile-accent-bad/the News page's breaking rows —
   consistent "this is fresh/urgent" language app-wide, not a one-off. */
.conflict-headline-recent {
    color: #FF6961;
    font-weight: 600;
}

.conflict-flags {
    margin-bottom: 0.6rem;
}

.conflict-flag svg {
    width: 2.2rem;
    height: auto;
    border-radius: 3px;
    margin-right: 0.4rem;
    vertical-align: middle;
}

/* AI-synthesized one-liner (pages_conflicts._ai_summary) — brighter and
   a touch bigger than the plain .conflict-headline rows below it, with
   a left accent bar, so it reads as the tile's own synthesized take
   rather than just another raw headline in the list. Absent entirely
   (no gap left behind) whenever the AI call didn't return anything. */
.conflict-ai-summary {
    font-size: 0.92rem;
    line-height: 1.45;
    color: #EDEDF2;
    font-weight: 500;
    margin-top: 0.6rem;
    padding-left: 0.6rem;
    border-left: 2px solid rgba(255,255,255,0.25);
}

.news-feed-list {
    padding: 0.4rem 1.5rem;
}

.news-feed-row {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 1.5rem;
    padding: 0.85rem 0 0.85rem 0.9rem;
    border-bottom: 1px solid rgba(255,255,255,0.07);
    border-left: 3px solid rgba(255,255,255,0.18);
}

/* Today's NEARBY section only ever shows one row at a time (see
   pages_today._render_local_news), unlike the agenda or News page's
   real lists — no scannability reason to keep the full row padding
   there, so it gets the same tightening treatment as the .tile.compact
   cards around it. */
.news-feed-row.compact {
    padding: 0.55rem 0 0.55rem 0.9rem;
}

/* Same category → color mapping as the breaking-news tag above, so a
   glance at the left edge of a row tells you what kind of story it is
   without reading the headline — consistent language across the whole
   News feed and the alert bars instead of every row looking the same.
   Rows that actually triggered (or would trigger) the breaking-news bar
   use this red instead of their category color — same red as
   badge-bad/tile-accent-bad elsewhere, so "this was breaking" reads as
   the same kind of signal everywhere in the app, not a one-off color. */
.news-feed-row.news-feed-row-breaking { border-left-color: #FF6961; }
.news-feed-row.news-cat-fed-boc { border-left-color: #BF5AF2; }
.news-feed-row.news-cat-data-surprise { border-left-color: #5AC8FA; }
.news-feed-row.news-cat-earnings { border-left-color: #32D74B; }
.news-feed-row.news-cat-macro-shock { border-left-color: #FFFFFF; }
.news-feed-row.news-cat-market-news { border-left-color: #FFD60A; }
.news-feed-row.news-cat-mergers { border-left-color: #FF9F0A; }
.news-feed-row.news-cat-milestone { border-left-color: #64D2FF; }
.news-feed-row.news-cat-tariffs { border-left-color: #5856D6; }
.news-feed-row.news-cat-conflict { border-left-color: #D70015; }
/* Today page's local-incidents section (local_news_client) — amber,
   distinct from every news.py category above since it's a completely
   separate, non-financial feed. */
.news-feed-row.news-cat-local { border-left-color: #FFB340; }

.news-feed-row:last-child {
    border-bottom: none;
}

/* Today page's agenda reuses this same row/list shape — same green as
   the rest of the app's "good/active" language for what's happening
   right now, faded out once an event's already ended today. The next
   not-yet-started event gets a quieter blue wash rather than green —
   green already means "happening now" everywhere else in the app, and
   reusing it here would blur that distinction — just enough of a tint
   to catch your eye scanning down the list without competing with the
   red leave-headline above it for attention. */
.news-feed-row.agenda-row-now { border-left-color: #32D74B; }
.news-feed-row.agenda-row-past { opacity: 0.5; }
.news-feed-row.agenda-row-next { border-left-color: #5AC8FA; background: rgba(90,200,250,0.08); }

/* Email page (pages_email.py) reuses this same row/list shape too —
   importance reuses news-feed-row-breaking's own red border-left
   above (same "this needed your attention" signal everywhere in the
   app), unread is its own separate dimension layered on top: a dot
   plus bold subject, the same read/unread language real mail clients
   already use, so a row can show either, both, or neither at a
   glance. */
.email-unread-dot {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #5AC8FA;
    margin-right: 0.5rem;
    vertical-align: middle;
    box-shadow: 0 0 6px 1px rgba(90,200,250,0.5);
}
.email-subject-unread {
    font-weight: 700;
}
.email-important-badge {
    flex-shrink: 0;
    font-size: 0.78rem;
    font-weight: 800;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: #FF6961;
    border: 1px solid rgba(255,105,97,0.5);
    border-radius: 8px;
    padding: 0.15rem 0.5rem;
    margin-left: 0.6rem;
}

/* Unified rotating slot for every "red headline" source — the leave-in
   countdown, storm proximity, the weather-statement banner, and
   breaking news (headline_rotation.py) — replacing the old arrangement
   where each of those pinned itself at its own fixed vertical offset
   (top-alert-bar at 18px, leave-headline at 88px, weather-statement-bar
   at 194px, storm-headline at 300px), stacking deterministically but
   taking up to 4 slots of permanent vertical space whenever more than
   one happened to be active at once. Session request: "make it so all
   the red headlines within the last 2 hours cycle at the top of the
   screen with a cool animation when it swaps." One slot now, at the
   topmost of those old positions — whichever single source is
   currently its turn, animated in on a swap (see the keyframe below)
   rather than everything sitting there permanently reserved. Same
   dark-blur-pill look as .leave-headline/.storm-headline below (the
   look 3 of the 4 sources already shared) rather than .top-alert-bar's
   old solid-gradient style, so the shared slot reads as one consistent
   thing regardless of which source is currently showing. */
/* Session request: "every single bar at the top should look like the
   toaster" — restyled from the centered dark-blur pill above to the
   same full-width solid-gradient bar this app's actual toasts
   (.news-alert-bar and family) already use, white text included (same
   convention those use for contrast against a saturated gradient,
   rather than tinting the text itself). top:0/left:0/right:0 instead
   of a centered pill with its own max-width — genuinely full-width,
   matching a toast's own shape, not just its color language. */
.headline-rotation {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    z-index: 502;
    text-align: center;
    font-size: 2rem;
    font-weight: 800;
    letter-spacing: -0.01em;
    line-height: 1.25;
    padding: 0.9rem 1.6rem;
    border-bottom: 2px solid rgba(255,255,255,0.25);
    color: #FFFFFF;
    text-shadow: 0 1px 3px rgba(0,0,0,0.35);
}
/* Design-pass fix, found live: this bar is position:fixed (doesn't
   push page content down) and real text sources here — breaking news
   headlines especially — have no length cap. An unusually long real
   headline would wrap to 2-3 lines, growing this bar taller and
   overlapping the clock/weather row underneath it rather than clipping
   cleanly. Scoped to .live-countdown specifically (not the outer
   .headline-rotation div) so the sports mini-jumbotron's own "html"-
   carrying candidate — a flex row of logos/text, never routed through
   this span — is untouched; every plain-text source (news, storm,
   weather statement, road closure, bedtime, leave) already fits
   comfortably on one line in practice, so this is a safety net for the
   one genuinely unbounded source, not a visible change for the rest. */
.headline-rotation .live-countdown {
    display: inline-block;
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    vertical-align: middle;
}
/* Same 4-tier severity scale .leave-headline's own intensity-* tiers
   already use — one shared scale across every source rather than each
   keeping its own bespoke severity naming, so the swap between
   sources reads as one consistent system. The leave candidate itself
   never carries one of these for its own ON-SCREEN color (see
   headline_rotation._render_candidate's own comment) — that stays the
   pre-existing, live-ticking .leave-headline.intensity-* rules below —
   but headline_rotation.py's own server-side copy of the SAME tier
   still drives this element's ordering/hold-time priority even for
   "leave," so the two systems agree on how urgent it is even though
   only one of them paints it.

   Each tier's own accent color (from the pre-toast-redesign palette —
   #5AC8FA/#FF9F0A/#FF6961/#FF453A) is now the GRADIENT, not the text
   color, dark-to-bright-to-dark left-to-right, same shape as
   .news-alert-bar's own gradient just adapted per tier instead of one
   fixed red. Font-size/padding still scale WITH severity too (session
   request: "get a clearer hierarchy going between what's more
   important") — calm reads smaller, warning and critical read larger
   — so the hierarchy stays visible in a single glance on top of the
   color difference. */
.headline-rotation.rotation-calm {
    background: linear-gradient(90deg, #0d2f3d 0%, #1c6684 50%, #0d2f3d 100%);
    box-shadow: 0 4px 24px rgba(28,102,132,0.32);
    font-size: 1.6rem;
    padding: 0.7rem 1.5rem;
}
.headline-rotation.rotation-notice {
    background: linear-gradient(90deg, #4a3005 0%, #b3720a 50%, #4a3005 100%);
    box-shadow: 0 4px 24px rgba(179,114,10,0.32);
}
/* Session request: the live-score bar (sports_alerts.
   live_score_headline_candidates) — "don't make it yellow, make it
   black... make the little top part... cool... make it look like a
   tiny little jumbotron." Its own class (not rotation-notice, which
   every other "real, not urgent" source still uses unchanged) so it
   can go black instead of that tier's gold, with a scoreboard-black
   gradient rather than a flat fill — same visual language as every
   other tier here (dark-to-bright-to-dark), just built from near-black
   instead of a hue. padding tightened from the other tiers' — this bar
   holds real logo images (.mini-jumbo-logo below), which already carry
   their own visual weight the other tiers' plain text doesn't. */
.headline-rotation.rotation-score {
    background: linear-gradient(90deg, #050505 0%, #1c1c1c 50%, #050505 100%);
    box-shadow: 0 4px 24px rgba(0,0,0,0.55);
    /* Design pass: "make it bigger and more scannable from a distance"
       — the mini-jumbo content (logos/score/status below) just grew
       noticeably; the bar's own padding grows with it so the enlarged
       content still gets real breathing room instead of pressing
       against the bar's edges. */
    padding: 1.05rem 2.1rem;
}
/* The mini-jumbotron itself — away team left, home team right, real
   logos, real abbreviations, the live score, and a status line
   (inning/period/quarter — see sports_alerts._mini_status), all in one
   row. --mini-jumbo-accent (sports_alerts._mini_jumbotron_html's own
   inline style) is this game's real, hand-tuned flash color
   (FLASH_BLUE/FLASH_RED/FLASH_GOLD — the same color that team's Govee
   flash already uses), read back the identical rgba(var(--x,
   fallback), a) way pages_jumbotron._side_html's --side-rgb already
   established (see theme.py's own --side-rgb rules) — one real,
   already-existing per-sport identity color, not a new one invented
   for this bar. */
.mini-jumbo {
    display: inline-flex;
    align-items: center;
    gap: 0.75rem;
    font-weight: 800;
    vertical-align: middle;
}
.mini-jumbo-logo {
    /* Design pass: "make it bigger and more scannable from a distance"
       — the previous 2.3rem bump still read smaller than the plain-
       text headlines sharing this same bar (2rem, 800 weight), which
       is backwards for a kiosk read across a room. Team identity is
       the first thing a glance should register. */
    height: 3.1rem;
    width: 3.1rem;
    object-fit: contain;
    filter: drop-shadow(0 1px 4px rgba(0,0,0,0.6));
}
.mini-jumbo-abbr {
    font-size: 1.6rem;
    letter-spacing: 0.04em;
    color: rgb(var(--mini-jumbo-accent, 160,170,200));
}
/* Session report: "how do i know who has the ball for NFL" — same 🏈
   glyph pages_jumbotron._side_html's own possession icon already uses
   (sports_alerts._nfl_possession_home), planted right next to
   whichever team abbreviation currently has it. */
.mini-jumbo-ball {
    font-size: 1.3rem;
    margin-right: 0.15rem;
    filter: drop-shadow(0 1px 2px rgba(0,0,0,0.6));
}
.mini-jumbo-score {
    font-size: 2.9rem;
    font-variant-numeric: tabular-nums;
    color: #FFFFFF;
}
.mini-jumbo-dash {
    font-size: 2rem;
    color: rgba(255,255,255,0.4);
}
.mini-jumbo-status {
    font-size: 1.4rem;
    font-weight: 700;
    letter-spacing: 0.03em;
    margin-left: 0.5rem;
    padding-left: 0.75rem;
    border-left: 2px solid rgba(255,255,255,0.22);
    color: rgb(var(--mini-jumbo-accent, 160,170,200));
}
/* Session request, after "we kind of got rid of the Jumbotron screen":
   "add some of the features where they already exist... the top bar
   with the scores" — win probability (sports_alerts.
   _win_probability_text) and MLB base occupancy (sports_alerts.
   _mlb_bases_html), both real data the full jumbotron board already
   computes, now also on this ambient bar. NFL down/distance/red zone
   needed no new CSS — it's folded directly into the existing
   .mini-jumbo-status text above. */
.mini-jumbo-wp {
    font-size: 1.15rem;
    font-weight: 800;
    letter-spacing: 0.02em;
    margin-left: 0.6rem;
    padding: 0.15rem 0.6rem;
    border-radius: 8px;
    background: rgba(var(--mini-jumbo-accent, 160,170,200), 0.18);
    color: rgb(var(--mini-jumbo-accent, 160,170,200));
}
.mini-jumbo-bases {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    margin-left: 0.6rem;
    /* Same visual language as pages_jumbotron.py's own base diamond —
       rotated squares, not circles — just 3 in a row instead of a
       real diamond layout; this bar has room for a glance, not a
       diagram. */
    transform: rotate(45deg);
}
/* Design pass: "make it bigger and more scannable from a distance" —
   these had already been bumped once (from 7px) but still lagged
   behind everything else on the bar after this same pass enlarged the
   score/logos/status around them. Kept the resting ring even when
   empty so the 3-dot cluster still reads as "the bases" at a glance
   before (and unless) one lights up. */
.mini-jumbo-base {
    width: 13px;
    height: 13px;
    background: rgba(255,255,255,0.12);
    border: 1px solid rgba(255,255,255,0.4);
}
.mini-jumbo-base.on {
    background: rgb(var(--mini-jumbo-accent, 160,170,200));
    border-color: rgb(var(--mini-jumbo-accent, 160,170,200));
    box-shadow: 0 0 9px 3px rgba(var(--mini-jumbo-accent, 160,170,200), 0.75);
}
.headline-rotation.rotation-warning {
    background: linear-gradient(90deg, #4a1512 0%, #a83a30 50%, #4a1512 100%);
    box-shadow: 0 4px 24px rgba(168,58,48,0.35);
    font-size: 2.15rem;
    padding: 1rem 1.7rem;
}
.headline-rotation.rotation-critical {
    background: linear-gradient(90deg, #5c0d0d 0%, #c41e1e 50%, #5c0d0d 100%);
    box-shadow: 0 4px 24px rgba(196,30,30,0.4);
    font-size: 2.3rem;
    padding: 1.05rem 1.8rem;
    animation: leave-headline-pulse 1.2s ease-in-out infinite, headline-rotation-toast-pulse 1.6s ease-in-out infinite;
}
/* box-shadow pulse for the top bar specifically — toast-pulse-red(-
   extreme) exist already but glow UPWARD (negative y-offset), tuned
   for a bar pinned to the BOTTOM of the screen; this is the same
   shape/intensity as toast-pulse-red-extreme, offset flipped positive
   so the glow reads correctly for a bar pinned to the TOP instead. */
@keyframes headline-rotation-toast-pulse {
    0%, 100% { box-shadow: 0 4px 24px rgba(196,30,30,0.4); }
    50% { box-shadow: 0 6px 44px rgba(196,30,30,0.75), 0 2px 80px rgba(196,30,30,0.3); }
}
/* Session request: "reformat the bedtime timer... doesn't look that
   good. Also make those timer a little bigger so they're... visible."
   Used to just be whichever plain rotation-calm/notice/critical/
   warning class its own tier happened to map to (sleep_tracker.
   _TIER_TO_ROTATION_CLASS) — the identical look a random road closure
   or weather statement gets, no identity of its own (see headline_
   rotation._render_candidate's own comment on the bedtime special
   case, same shape as the pre-existing "leave" one). Same "one warm
   family throughout" philosophy night_mode.py's own .night-bedtime
   already established for this exact feature, not a severity-tiered
   blue/amber/red swap — this is a personal daily thing, not a hazard
   alert. Structurally still a normal .headline-rotation tier rule
   (background/box-shadow/font-size/padding only, same as rotation-
   critical above) — no position/layout override, so it still lives in
   the same shared rotating slot as every other source, just sized up
   (2.4rem vs. the old rotation-calm tier's 1.6rem) and warm-branded
   instead of generic. */
.headline-rotation.bedtime-headline {
    background: linear-gradient(90deg, #3d0f0c 0%, #8f2a20 50%, #3d0f0c 100%);
    box-shadow: 0 4px 24px rgba(143,42,32,0.4);
    font-size: 2.4rem;
    padding: 1.05rem 1.9rem;
}
/* The one-shot "swap" animation itself — a JS-toggled class
   (app.py's kiosk-headline-rotation-swap script), not a plain
   `animation` on the base rule: Streamlit patches this element's
   content in place on an ordinary rerun rather than replacing the
   node outright, so a CSS animation declared directly on .headline-
   rotation would either never re-trigger after its first paint, or
   (if Streamlit's diffing ever DID replace the node) replay on every
   5s rerun regardless of whether the headline actually changed —
   same reflow-then-add-class trick as kiosk-jumbo-fade, just a slide+
   fade instead of a plain fade. Written as its own combined rule for
   .rotation-critical specifically (rather than relying on the
   cascade) since `animation` is a single property — without an
   explicit combined value here, adding .rotation-swap-in would
   replace the critical tier's own continuous pulse instead of
   layering on top of it for the swap's brief duration.

   Session request: "it just feels boring lately, kind of flat."
   Real, confirmed cause for THIS specific animation: the "remove
   quite literally all of the animations" pass (this file's own global
   kill switch, `* { animation: none !important; }` near the top) went
   in at the SAME time kiosk-headline-rotation-swap itself was deleted
   from app.py outright — but this rule was left behind without the
   `!important` every other surviving exception (.ticker-track/
   .weather-radar-frame-img) already needed to beat that kill switch,
   so even after the JS trigger comes back (see app.py), the animation
   itself would have stayed silently inert. `!important` added below,
   same pattern as those two exceptions — this is now genuinely back,
   not still dead code with an out-of-date comment pointing at a
   script that no longer existed. */
.headline-rotation.rotation-swap-in { animation: headline-rotation-swap-in 0.5s cubic-bezier(.2,.8,.2,1) !important; }
.headline-rotation.rotation-critical.rotation-swap-in {
    animation: headline-rotation-swap-in 0.5s cubic-bezier(.2,.8,.2,1), leave-headline-pulse 1.2s ease-in-out infinite,
        headline-rotation-toast-pulse 1.6s ease-in-out infinite !important;
}
@keyframes headline-rotation-swap-in {
    from { opacity: 0; transform: translateY(-16px); }
    to { opacity: 1; transform: translateY(0); }
}
/* Audit fix — a real bug, not just a precaution: when the leave
   candidate is showing (headline_rotation._render_candidate carries
   both .headline-rotation AND .leave-headline on the same div, see
   its own comment on why), .leave-headline's OWN base rule below sets
   top/font-size/z-index too, at the exact same specificity as
   .headline-rotation's base rule — and since .leave-headline is
   defined LATER in this file, its top:88px/2.6rem/z-index:500 silently
   won over .headline-rotation's top:18px/2rem/502 for every property
   both rules happen to set, dropping the leave candidate 70px below
   the shared slot (and out of size/stacking sync with the other 3
   sources) every time it took its turn in the rotation — confirmed by
   direct property comparison, not just suspected. Only the properties
   that actually differ between the two base rules are reasserted here
   (a combined selector, 0,2,0, beats either base rule's 0,1,0
   regardless of source order) — color/border-color/animation
   deliberately left out so the live intensity-* tier rules (see
   .leave-headline.intensity-* below, same 0,2,0 specificity as this
   but no property overlap with it) remain the only source of truth
   for those. */
.headline-rotation.leave-headline {
    top: 0;
    left: 0;
    right: 0;
    transform: none;
    font-size: 2rem;
    z-index: 502;
}

/* Standalone headline at the top of the Today page — promoted out of
   the agenda card entirely (see pages_today._render_leave_headline) so
   it's the first thing on screen, not nested inside another tile.
   Plain bold text with a soft glow rather than a boxed card — reads as
   a headline/statement, not another chip competing with the agenda
   for attention right below it. Distinct from the transient bottom-bar
   toast (commute_reminder.render_bar), which still owns the "Leave
   now" moment once this stops rendering.

   position: fixed rather than normal document flow — session report:
   "the red headline at the top has been lost since the morning brief
   has gotten significantly longer and bigger." Root cause: .block-
   container centers its content vertically (justify-content: center,
   for a nicer look on the many days everything comfortably fits one
   screen) — once the AI-written morning brief runs long enough to push
   total content past one viewport's height, that same centering pushes
   the excess out equally above AND below the fold, so the very first
   thing on the page silently loses the top-of-viewport tug of war along
   with whatever falls off the bottom. Pinning this specific element to
   the viewport itself (with its own semi-opaque backdrop so it stays
   legible over whatever's rendered beneath it) makes it immune to that
   regardless of how tall the rest of the page's content ever gets. */
.leave-headline {
    position: fixed;
    /* Below .top-alert-bar (fixed at top:18px, z-index 501) — that one
       renders first in flow and keeps that same priority now that both
       are pinned. */
    top: 88px;
    left: 50%;
    transform: translateX(-50%);
    z-index: 500;
    text-align: center;
    font-size: 2.6rem;
    font-weight: 800;
    letter-spacing: -0.01em;
    background: rgba(12,12,16,0.72);
    backdrop-filter: blur(24px) saturate(160%);
    -webkit-backdrop-filter: blur(24px) saturate(160%);
    border: 1px solid rgba(255,69,58,0.25);
    border-radius: 20px;
    padding: 0.5rem 1.6rem;
    /* Color/glow/pulse are all set per intensity-* tier below, not
       here — this is just the structural fallback in case JS hasn't
       applied a tier class yet (Python always sets one server-side on
       first paint, see commute_reminder.leave_headline_candidate, so
       this should only ever be visible for a flash). */
    color: #FF453A;
}

/* Escalating urgency as leave-by approaches — session request: "make
   the leave in timer chill and it progressively gets more intense and
   alerting the closer we are to the leave time." Used to be the same
   red pulse for the whole HEADLINE_WINDOW_MINUTES window regardless of
   how far out it was, which read as maximally urgent the instant it
   appeared — two hours out is advance notice, not a deadline. Tier
   thresholds live in commute_reminder.py's _intensity_tier (first
   frame) and are mirrored in app.py's live-countdown ticker (every
   second after); see that ticker's own comment for why this only
   touches the leave headline and not the jumbotron/sports countdowns
   sharing the same script. */
.leave-headline.intensity-calm {
    color: #5AC8FA;
    text-shadow: 0 0 14px rgba(90,200,250,0.3);
    border-color: rgba(90,200,250,0.2);
    animation: none;
}
.leave-headline.intensity-aware {
    color: #FF9F0A;
    border-color: rgba(255,159,10,0.22);
    animation: leave-headline-pulse-amber 3s ease-in-out infinite;
}
.leave-headline.intensity-urgent {
    color: #FF6961;
    border-color: rgba(255,105,97,0.25);
    animation: leave-headline-pulse-red 2s ease-in-out infinite;
}
.leave-headline.intensity-critical {
    color: #FF453A;
    border-color: rgba(255,69,58,0.3);
    /* The original always-on pulse, now correctly reserved for the
       final INTENSITY_CRITICAL_SECONDS (10 min) instead of the whole
       2-hour window. */
    animation: leave-headline-pulse 1.2s ease-in-out infinite;
}
.leave-headline.intensity-overdue {
    color: #FF453A;
    border-color: rgba(255,69,58,0.35);
    animation: leave-headline-pulse-overdue 0.7s ease-in-out infinite;
}
/* Same real fix the mobile breakpoint's own leave-headline-pulse-
   overdue-mobile already established, needed here too now that the
   rotation redesign made .headline-rotation.leave-headline full-width
   (no more left:50%/transform:translateX(-50%) to stay centered
   around) — leave-headline-pulse-overdue's own translateX(-50%),
   baked into every frame, only makes sense for the STANDALONE Today-
   page .leave-headline (still centered that way, untouched). Without
   this override the rotation-embedded leave candidate would shift
   sideways by half its own width on every overdue pulse. More
   specific (0,3,0) than .leave-headline.intensity-overdue's own
   0,2,0, so this correctly wins for the combined case regardless of
   source order. */
@keyframes leave-headline-pulse-overdue-rotation {
    0%, 100% { text-shadow: 0 0 22px rgba(255,69,58,0.5); transform: scale(1); }
    50% { text-shadow: 0 0 40px rgba(255,69,58,0.9), 0 0 70px rgba(255,69,58,0.4); transform: scale(1.03); }
}
.headline-rotation.leave-headline.intensity-overdue {
    animation: leave-headline-pulse-overdue-rotation 0.7s ease-in-out infinite;
}

/* Session request: "make the leave-in alert softer and less jarring
   between the hours of like ten PM and eight AM." Toggled by
   app.py's kiosk-countdown-ticker (see its own comment — same 22/8
   boundary as commute_reminder.py's LEAVE_QUIET_HOURS_START_HOUR/_END_
   HOUR). Opacity alone, not a color remap: the tier's own color still
   shows through (dimmed), so the countdown stays honestly informative
   — if you genuinely need to leave at 3am, it should still read as
   urgent, just not at full brightness. animation:none is defensive
   documentation, not a working fix — every leave-headline-pulse-*
   keyframe above is already inert against this file's own global kill
   switch (`* { animation: none !important; }`, no `!important` on any
   of those declarations) — quiet hours should never be the moment
   that changes, so this makes the intent explicit rather than relying
   on an unrelated bug staying unfixed. */
.leave-headline.quiet-hours {
    opacity: 0.7;
    animation: none;
}

/* commute_reminder.render_ticker_leave_bar — same slot as .ticker-bar
   (position/left/right/bottom/z-index all match exactly) so a real
   toast still covers it the instant one fires, same as it already
   covers the market ticker. Same intensity-tier colors as
   .leave-headline above, just laid out as a slim full-width bar
   instead of a floating pill — this needs to fit where the ticker
   normally sits, not compete with the jumbotron board above it.

   Session request: "make the leave in timer in the bottom bar...
   visible from across the room... without losing its boundaries" —
   sized up from the ticker-matching 1.35rem to something actually
   readable at kiosk viewing distance, closer to .leave-headline's own
   2.6rem. overflow:hidden + nowrap keep it clipped to this exact bar
   (the "boundaries" — same fixed footprint as before, just bigger
   text inside it) rather than ever spilling into the board above. */
.jumbo-leave-ticker {
    position: fixed;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 10;
    background: rgba(8,8,11,0.92);
    border-top: 1px solid rgba(255,255,255,0.08);
    padding: 1.1rem 0;
    text-align: center;
    font-size: 2.6rem;
    font-weight: 800;
    letter-spacing: 0.01em;
    color: #5AC8FA;
    overflow: hidden;
    white-space: nowrap;
}
.jumbo-leave-ticker.intensity-calm { color: #5AC8FA; }
.jumbo-leave-ticker.intensity-aware {
    color: #FF9F0A;
    animation: leave-headline-pulse-amber 3s ease-in-out infinite;
}
.jumbo-leave-ticker.intensity-urgent {
    color: #FF6961;
    animation: leave-headline-pulse-red 2s ease-in-out infinite;
}
.jumbo-leave-ticker.intensity-critical {
    color: #FF453A;
    animation: leave-headline-pulse 1.2s ease-in-out infinite;
}
.jumbo-leave-ticker.intensity-overdue {
    color: #FF453A;
    animation: leave-headline-pulse-overdue 0.7s ease-in-out infinite;
}
/* Same quiet-hours treatment as .leave-headline.quiet-hours above —
   set server-side directly by commute_reminder.render_ticker_leave_bar
   (this surface only shows during a jumbotron takeover, which re-
   renders every ~5s via its own fast fragment, plenty precise for a
   day/night-style boolean, so no JS mirroring needed here). */
.jumbo-leave-ticker.quiet-hours {
    opacity: 0.7;
    animation: none;
}
@keyframes leave-headline-pulse-amber {
    0%, 100% { text-shadow: 0 0 18px rgba(255,159,10,0.4); }
    50% { text-shadow: 0 0 28px rgba(255,159,10,0.7); }
}
@keyframes leave-headline-pulse-red {
    0%, 100% { text-shadow: 0 0 20px rgba(255,105,97,0.45); }
    50% { text-shadow: 0 0 32px rgba(255,105,97,0.8); }
}
@keyframes leave-headline-pulse {
    0%, 100% { text-shadow: 0 0 22px rgba(255,69,58,0.45); }
    50% { text-shadow: 0 0 36px rgba(255,69,58,0.85), 0 0 60px rgba(255,69,58,0.35); }
}
@keyframes leave-headline-pulse-overdue {
    /* Only tier that also scales — the translateX(-50%) has to be
       repeated in every keyframe step since this element is centered
       via that same transform property (see .leave-headline above);
       dropping it here would snap the headline off-center mid-pulse. */
    0%, 100% { text-shadow: 0 0 22px rgba(255,69,58,0.5); transform: translateX(-50%) scale(1); }
    50% { text-shadow: 0 0 40px rgba(255,69,58,0.9), 0 0 70px rgba(255,69,58,0.4); transform: translateX(-50%) scale(1.03); }
}

/* Same page-independent headline treatment for the final hour before a
   Jays/Habs game (sports_alerts.render_game_countdown) — deliberately
   smaller and calmer than the leave headline (no pulse): a game
   starting is anticipation, not a deadline, and if both ever render at
   once the commute one must clearly be the urgent one. Team-colored,
   matching each team's own alert bar (see .sports-alert-bar-*).

   Same position: fixed fix as .leave-headline above and for the same
   reason — stacked directly beneath it (a fixed top offset rather than
   flowing after it, since the two are independent st.markdown calls
   with nothing to naturally stack them once both are pulled out of
   document flow; .leave-headline's own height is stable enough — one
   line, "Leave in H:MM:SS" — that a hardcoded gap here doesn't drift). */
.game-countdown-headline {
    position: fixed;
    top: 184px;
    left: 50%;
    transform: translateX(-50%);
    z-index: 499;
    text-align: center;
    font-size: 1.9rem;
    font-weight: 800;
    letter-spacing: -0.01em;
    background: rgba(12,12,16,0.72);
    backdrop-filter: blur(24px) saturate(160%);
    -webkit-backdrop-filter: blur(24px) saturate(160%);
    border-radius: 20px;
    padding: 0.4rem 1.4rem;
}
.game-countdown-mlb {
    color: #4AA8FF;
    text-shadow: 0 0 22px rgba(74,168,255,0.4);
}
.game-countdown-nhl {
    color: #FF5A5F;
    text-shadow: 0 0 22px rgba(255,90,95,0.4);
}
.game-countdown-nfl {
    color: #D3BC8D;
    text-shadow: 0 0 22px rgba(211,188,141,0.4);
}

/* Small, deliberately unobtrusive — session request: "a little ai
   usage bar... in a small space on the dashboard probs like bottom
   right." Page-independent like the pinned headlines above, but tucked
   in a corner rather than pinned to attention: this is a system-health
   glance, not something that needs to compete for focus the way a
   breaking headline does. Lower z-index than the pinned headlines
   (which sit at 499-501) since it never needs to sit above anything —
   nothing else lives in this corner other than Streamlit Community
   Cloud's own "Hosted with Streamlit" badge, which the app itself
   doesn't control (session report: "the red streamlit logo is covering
   the ai bar" — same corner Streamlit's badge already claimed once
   before, see .st-key-jumbotron_controls's own comment on being moved
   off bottom-right for the identical reason). Bumped up to clear it
   rather than trying to out-z-index or hide it — that badge isn't part
   of this app's own DOM (survives the #MainMenu/header/footer hiding
   rule above), so there's nothing here to hide it with anyway.

   Was a percentage bar; replaced with a plain status dot + label —
   session request, after the percentage's own blind spots caused real
   confusion (a fresh-process estimate reading "100%" right after a
   real rate limit had just been hit): "can you just change the badge
   to say AI: Active or AI: Rate Limited or any an all other statuses
   it may have." Later widened from one line to one row per model —
   session request: "since we have a bunch of different models now...
   show what models are active and what ones are not responding." See
   groq_client.ai_status_by_model for the full status list.

   Later still: "encapsulate all of the performance metrics into the
   bottom bar... it'll just rotate through it so it doesn't take up any
   screen real estate." Up to 5 stacked rows became up to 3 (AI
   summary/Dashboard/Kiosk) ROTATING slots, app.py's own job — only
   ONE row was ever actually in the DOM at a time.

   Session request: "make it so the score on the maintenance page is
   shown in the corner in a bigger style instead of the small rotating
   badges." dashboard_score.py's composite score already rolls up
   every one of those 3 slots' own underlying signals into one number
   — replaced the whole rotation with this one always-visible badge
   instead, class renamed .ai-status-bar -> .system-health-corner to
   match (same position/z-index/corner — see .stElementContainer:has()
   and the mobile breakpoint below, both updated to the new name; see
   .brdn-ticker's own comment for why ITS stacking clearance above this
   corner didn't need to change, same geometry either way). .ai-status-
   dot/.ai-status-text below are kept — still reused by the pulse row
   inside the new badge, see app.py's own comment on why that row
   stays separate from the score itself.

   Session follow-up, after seeing the static score-only version live:
   "I want that same kind of formatting on the little widget on the
   side... I want it to rotate between all the different ones and have
   the same formatting as that" — briefly a 20s rotation across score/
   dashboard/kiosk/internet slots, one at a time.

   Session follow-up, after THAT: "That's actually not what I wanted at
   all. I liked how you had it formatted with the other page where you
   had all three... with their stats in the bar big and visible. hide
   the 0-100 score and the little writing that says Dashboard: live."
   No rotation anymore — Dashboard/Kiosk/Internet all stacked and
   always visible at once, exactly matching pages_system_health.py's
   own 3-tile row (app.py now calls that page's own dashboard_stats()/
   kiosk_stats()/network_stats() directly — same .system-health-stat/
   -value/-label classes those emit, genuinely the same formatting by
   construction, not just visually matched). Score and the pulse-dot/
   text row are both gone entirely per that report. */
/* Session request: "clicking on that little box in the bottom right
   opened the dev window." The whole badge is now wrapped in a plain
   <a href="?page=maintenance">, which by default would underline and
   blue-tint every bit of text inside it (an <a>'s color/text-decoration
   inherit down through its children unless reset) — this makes the
   link itself invisible as a link, so the badge still reads as a
   plain glass status widget, not a suddenly-blue hyperlink. position:
   fixed still lives on .system-health-corner itself below, not this
   wrapper — an <a> around a fixed-position child doesn't affect that
   child's own fixed positioning, so this needed no layout changes. */
.system-health-corner-link {
    text-decoration: none;
    color: inherit;
    cursor: pointer;
}
.system-health-corner {
    position: fixed;
    bottom: 60px;
    right: 14px;
    z-index: 400;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.5rem;
    padding: 0.7rem 1.1rem;
    border-radius: 14px;
    background: rgba(12,12,16,0.68);
    backdrop-filter: blur(20px) saturate(160%);
    -webkit-backdrop-filter: blur(20px) saturate(160%);
    border: 1px solid rgba(255,255,255,0.12);
    /* Same elevation .tile/.market-pill/.score-card already use —
       audit fix: this floating glass badge used the same blur/border
       language as every card on the kiosk but skipped the shadow that
       normally comes with it, so it read flatter than it should next
       to them. */
    box-shadow: 0 10px 30px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.05);
    opacity: 0.85;
    transition: opacity 0.2s ease;
}
.system-health-corner:hover {
    opacity: 1;
}
/* One section per stat group (Dashboard/Kiosk/Internet) — its own
   wrapper, not flat children of .system-health-corner directly, so
   the title/stat-row gap can be tighter than the gap BETWEEN sections
   (a title belongs visually with its own row, not equidistant from
   the row above it too) and so a divider can target the boundary
   between sections specifically via the adjacent-sibling selector
   below (none above the first section, none below the last). */
.system-health-corner-section {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.15rem;
}
.system-health-corner-section + .system-health-corner-section {
    padding-top: 0.5rem;
    border-top: 1px solid rgba(255,255,255,0.08);
}
/* Audit fix: matches .system-health-stat-label's own weight/color now
   (700/#8E8E93, the same established "small uppercase caption" recipe
   .form-strip-label etc. already use) — only font-size stays its own
   smaller value, for the same "this corner pill is a scaled-down
   mirror of the page's own tiles" reason .system-health-stat-value/
   -label are scaled down just below. */
.system-health-corner-title {
    font-size: 0.68rem;
    font-weight: 700;
    color: #8E8E93;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}
/* Same .system-health-stat-row/-value/-label pages_system_health.py
   uses, just sized down for a corner pill instead of a full tile — a
   section showing 3 stats side by side (Kiosk's CPU/RAM/temp) needs
   to fit this much smaller footprint without overflowing. */
.system-health-corner .system-health-stat-row {
    gap: 0.7rem;
    padding-top: 0;
}
.system-health-corner .system-health-stat-value {
    font-size: 1.5rem;
}
.system-health-corner .system-health-stat-label {
    font-size: 0.62rem;
}
.ai-status-dot {
    flex-shrink: 0;
    width: 7px;
    height: 7px;
    border-radius: 50%;
}
.ai-status-dot-good { background: #32D74B; box-shadow: 0 0 6px 1px rgba(50,215,75,0.55); }
.ai-status-dot-medium { background: #FF9F0A; box-shadow: 0 0 6px 1px rgba(255,159,10,0.55); }
.ai-status-dot-low { background: #FF6961; box-shadow: 0 0 6px 1px rgba(255,105,97,0.55); }
.ai-status-dot-neutral { background: #5AC8FA; box-shadow: 0 0 6px 1px rgba(90,200,250,0.55); }
.ai-status-text {
    font-size: 0.68rem;
    font-weight: 600;
    color: rgba(255,255,255,0.6);
    white-space: nowrap;
}

/* Session request: "a little ticker... visible from across the room,
   but not obstructive... regardless of what page I'm on." First tried
   top-right — confirmed live that was wrong: .headline-rotation is
   position:fixed, top:0, left:0, right:0 (genuinely full-width) at
   z-index:502, well above this element's own z-index, and it's active
   often enough (bedtime countdown, leave-in timer, any weather/storm
   alert) that it silently covered this corner outright, not just
   overlapped it. Moved to bottom-right instead, stacked directly above
   .system-health-corner (measured live: bottom:60px, ~71.5px tall for
   its then-typical 4-row stack) rather than sharing that corner —
   bottom:145px clears even a slightly taller stack with real breathing
   room. That corner is down to one fixed-height badge now (see its
   own comment above) — this only means MORE clearance than strictly
   needed today, not a collision, so left as-is rather than re-tuned
   for a value that'd need remeasuring against a currently-disabled
   element (brayden_index.ENABLED) anyway. Sized
   and weighted to actually read at a glance from across a room (unlike
   .ai-status-text's deliberately-subtle 0.68rem debug telemetry just
   above) while staying a small corner pill, not a banner — "not
   obstructive" is the backdrop-blur + modest padding, not a smaller
   font. */
/* Audit fix: radius/border-alpha/fill-alpha now match .system-health-
   corner exactly (14px/0.12/0.68, plus the same elevation shadow) —
   this stacks directly above that corner (see this rule's own
   bottom:145px, sized for that clearance) and the two were drifting on
   3 separate properties despite being guaranteed to sit in the same
   screen corner, one above the other, whenever BRDN is re-enabled. */
.brdn-ticker {
    position: fixed;
    bottom: 145px;
    right: 14px;
    z-index: 401;
    padding: 0.5rem 1.1rem;
    border-radius: 14px;
    background: rgba(12,12,16,0.68);
    backdrop-filter: blur(20px) saturate(160%);
    -webkit-backdrop-filter: blur(20px) saturate(160%);
    border: 1px solid rgba(255,255,255,0.12);
    box-shadow: 0 10px 30px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.05);
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Helvetica Neue", sans-serif;
    font-weight: 700;
    font-size: 1.6rem;
    letter-spacing: 0.01em;
    line-height: 1.2;
    font-variant-numeric: tabular-nums;
    color: #D6D6DC;
}
.brdn-ticker-symbol {
    font-size: 0.8rem;
    font-weight: 600;
    letter-spacing: 0.09em;
    opacity: 0.6;
    margin-right: 0.45rem;
}
.brdn-ticker.market-up { color: #32D74B; }
.brdn-ticker.market-down { color: #FF6961; }

/* Voice assistant status badge (voice/status.py) — session's own
   explicit requirement: "a visible dashboard status showing something
   like MIC: MUTED / LISTENING FOR WAKE WORD / LISTENING / PROCESSING /
   SPEAKING... I want it to always be obvious when the assistant is
   actively processing a command." Bottom-LEFT, not bottom-right —
   that corner already stacks .system-health-corner and .brdn-ticker;
   this is a genuinely separate, unrelated status and putting it there
   too would just crowd one corner while the other sits empty. Same
   glass-card family (blur/border/shadow) as those two for visual
   consistency, not a new look. Omitted entirely from the DOM by app.py
   whenever voice/status.py has never reported in (service not
   deployed/running) rather than rendering a fake default state — same
   "just omit it" rule this app already applies to every other
   no-data-yet feature. */
.voice-status-badge {
    position: fixed;
    /* 60px, not 14px — found live: the shared bottom toast bar
       (.news-alert-bar/-market, and every other alert source that
       reuses it) is a full-width strip pinned to bottom:0 at
       z-index:10000, and it shows up often (any of ~10 different toast
       sources, roughly every 10s when one's active). 60px matches
       .system-health-corner's own bottom offset, already proven clear
       of that bar in this exact layout. */
    bottom: 60px;
    left: 14px;
    z-index: 400;
    display: flex;
    align-items: center;
    gap: 0.7rem;
    padding: 0.6rem 1.1rem;
    border-radius: 14px;
    background: rgba(12,12,16,0.68);
    backdrop-filter: blur(20px) saturate(160%);
    -webkit-backdrop-filter: blur(20px) saturate(160%);
    border: 1px solid rgba(255,255,255,0.12);
    box-shadow: 0 10px 30px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.05);
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Helvetica Neue", sans-serif;
}
.voice-status-icon { font-size: 1.5rem; line-height: 1; }
.voice-status-text { display: flex; flex-direction: column; line-height: 1.25; }
.voice-status-name {
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    color: #8E8E93;
}
.voice-status-state {
    font-size: 1rem;
    font-weight: 700;
    letter-spacing: 0.01em;
}
/* Neutral passive listening is deliberately the same muted gray as the
   name label above it — this is the steady-state 99% of the time, and
   shouldn't visually compete with an actually-active state. Listening/
   processing/speaking each get a distinct, brighter color specifically
   so a glance across the room can tell "idle" from "doing something"
   without reading the words. */
.voice-status-badge.voice-status-listening_for_wake_word .voice-status-state { color: #8E8E93; }
.voice-status-badge.voice-status-listening .voice-status-state { color: #3DD9FF; }
.voice-status-badge.voice-status-processing .voice-status-state { color: #FF9F0A; }
.voice-status-badge.voice-status-speaking .voice-status-state { color: #32D74B; }
.voice-status-badge.voice-status-muted .voice-status-state { color: #FF6961; }

/* pages_brdn_terminal.py — session request: "bring up the full
   institutional analysis on my stock in a Bloomberg terminal style,
   kinda like the Jumbotron, but for a Bloomberg terminal." Deliberately
   its own visual language, not this app's usual glass-card look: flat
   black, hard 1px borders, monospace, amber labels — Bloomberg's own
   real signature palette.

   Bug found live (session incident: the page appeared to hang, was
   actually rendering fine but invisible): there is NO real full-screen
   wrapper element here, on purpose now — an earlier version tried
   `st.markdown('<div class="brdn-terminal">', ...)` opened in one call
   and closed in a LATER, separate st.markdown call, assuming the HTML
   would nest across both like it would in a plain static document.
   Streamlit doesn't work that way: each st.markdown call gets its own
   independent DOM container, so that div immediately self-closed empty
   — and because it was still position:fixed/inset:0/z-index:500, it
   sat on top of the whole page as an opaque black square, hiding every
   real panel that rendered (correctly) as sibling elements after it.
   Confirmed live: all 6 panels were genuinely in the DOM the entire
   time, just visually buried under this element.

   The fix is the same trick pages_jumbotron.py already relies on and
   this should have copied from the start: .streamlit/config.toml's own
   backgroundColor is already #000000 app-wide, so a full-screen black
   background needs no wrapper element at all — just don't paint
   anything else over it (app.py's own _terminal_active already skips
   the normal sky/hero-row/etc. the same way it does for the
   jumbotron). Each real top-level piece (header/panel/footer) carries
   its own font-family/color directly instead of inheriting from a
   parent that no longer (and structurally never actually did) wrap
   them. .brdn-terminal-up/-down replace the old .up/.down (which used
   to rely on that same non-functional parent scoping) — a brighter,
   more clinical green/red than this app's normal market-up/market-
   down, applied directly wherever needed instead of via inheritance.
   No animation/transition here at all — theme.py's own global kill
   switch would just neuter it anyway (see this file's "Animations
   removed" note), so it's left out rather than shipped as dead code. */
.brdn-terminal-up { color: #00FF7F; }
.brdn-terminal-down { color: #FF3B30; }
.brdn-terminal-header {
    display: flex;
    align-items: baseline;
    gap: 1.3rem;
    border-bottom: 1px solid #FF9F0A;
    padding-bottom: 0.6rem;
    font-size: 1.15rem;
    font-variant-numeric: tabular-nums;
    font-family: "SF Mono", "Menlo", "Consolas", "Roboto Mono", monospace;
    color: #E8E8E0;
    margin: 0 0 0.7rem;
}
.brdn-terminal-ticker {
    color: #FF9F0A;
    font-weight: 700;
    letter-spacing: 0.04em;
}
.brdn-terminal-price {
    font-size: 1.6rem;
    font-weight: 700;
}
.brdn-terminal-tag {
    border: 1px solid currentColor;
    border-radius: 3px;
    padding: 0.05rem 0.4rem;
    font-size: 0.75rem;
    letter-spacing: 0.06em;
    opacity: 0.9;
}
.brdn-terminal-clock {
    margin-left: auto;
    font-size: 0.85rem;
}
.brdn-terminal-dim {
    color: #8A8A82;
    font-size: 0.85rem;
}
.brdn-terminal-panel {
    border: 1px solid #3A3A32;
    background: #0A0A08;
    padding: 0.75rem 0.9rem;
    height: 100%;
    box-sizing: border-box;
    overflow: hidden;
    font-family: "SF Mono", "Menlo", "Consolas", "Roboto Mono", monospace;
    color: #E8E8E0;
    /* Real spacing between st.columns() ROWS — each row of panels is
       its own separate Streamlit element now (no flex-column parent
       providing gap across rows the way the old, non-functional
       wrapper's CSS implied); bottom margin here is what actually
       creates that spacing. Columns WITHIN one row still align by
       height normally (a real st.columns() layout primitive, unlike
       the old wrapper div — this part was never actually broken). */
    margin-bottom: 0.7rem;
}
.brdn-terminal-label {
    color: #FF9F0A;
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    margin-bottom: 0.45rem;
}
.brdn-terminal-row {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 0.8rem;
    padding: 0.28rem 0;
    border-bottom: 1px solid #201F1A;
    font-size: 0.92rem;
    font-variant-numeric: tabular-nums;
}
.brdn-terminal-row:last-child { border-bottom: none; }
.brdn-terminal-quote {
    font-style: italic;
    font-size: 0.92rem;
    line-height: 1.45;
    color: #C8C8C0;
}
.brdn-terminal-wrap {
    line-height: 1.4;
    white-space: normal;
}
.brdn-terminal-footer {
    text-align: center;
    color: #5A5A50;
    font-size: 0.7rem;
    letter-spacing: 0.08em;
    padding-top: 0.4rem;
    font-family: "SF Mono", "Menlo", "Consolas", "Roboto Mono", monospace;
}

/* Today page's agenda only — same news-feed-row shape the News page
   uses for its own (much longer, faster-scanned) list, but scaled up
   here since this list is short and meant to be read at a glance, not
   skimmed. */
.agenda-feed-list.news-feed-list {
    padding: 0.5rem 1.5rem;
}
/* Today page's section label + commute tile, scaled up — session
   feedback: "I can see the twenty seven minutes. I can't read anything
   else there." The 27 was already big; the route, the delay/why line,
   and the trend/ice warnings underneath were the unreadable part, so
   everything around the number steps up with it. */
.agenda-label {
    font-size: 1.2rem;
}
.agenda-empty .tile-prev {
    font-size: 1.3rem;
}
.commute-tile .tile-label.compact {
    font-size: 1.2rem;
}
.commute-tile .tile-value {
    font-size: 3.4rem;
}
.commute-tile .tile-prev {
    font-size: 1.35rem;
    margin-top: 0.35rem;
}
.commute-tile .severity-caption.compact {
    font-size: 1.25rem;
    margin-top: 0.5rem;
}
/* Session request: "flash an amber/warning state on the Streamlit card
   so I can see it instantly at a glance" (commute_reminder.
   is_congested — a hybrid predictive+live traffic delay real enough to
   matter, not routine noise). A STATIC amber border/glow, not an
   actual flash/pulse — the global `* { animation: none !important; }`
   kill switch (see this file's own "Animations removed" note) would
   silently drop a keyframe-only treatment the same way it already did
   everywhere else, so the resting state alone has to read as a real
   warning. Same amber family as .leave-headline.intensity-aware
   (#FF9F0A) — one consistent "amber means traffic/commute warning"
   color across the whole app, not a new one invented just for this
   tile. box-shadow ADDS the glow onto the base .tile depth shadow
   (comma-separated) rather than replacing it, so the card doesn't lose
   its normal depth. */
.commute-tile.congested {
    border-color: rgba(255,159,10,0.55);
    box-shadow: 0 10px 30px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.05), 0 0 28px rgba(255,159,10,0.28);
}
.agenda-feed-list .news-feed-row {
    padding: 1.2rem 0 1.2rem 1.1rem;
    border-left-width: 5px;
}
.agenda-feed-list .news-feed-headline {
    font-size: 1.55rem;
    font-weight: 700;
}
.agenda-feed-list .news-feed-meta {
    font-size: 1.15rem;
}

.news-feed-headline {
    font-size: 1.05rem;
    font-weight: 600;
    color: #F5F5F7;
}

.headline-ticker-badge {
    display: inline-block;
    margin-left: 0.6rem;
    padding: 0.08rem 0.5rem;
    border-radius: 10px;
    font-size: 0.78rem;
    font-weight: 700;
    white-space: nowrap;
    vertical-align: middle;
}
.headline-ticker-badge.market-up { background: rgba(50,215,75,0.18); color: #32D74B; }
.headline-ticker-badge.market-down { background: rgba(255,105,97,0.18); color: #FF6961; }

.news-feed-meta {
    flex-shrink: 0;
    font-size: 0.85rem;
    color: #8E8E93;
}

/* Session request: "redesign the mobile UI... see the full pages...
   without issues and lag." Confirmed live (same root cause the
   jumbotron takeover already found and fixed for itself, see
   .block-container:has(.jumbo-root) > div's own comment below): every one
   of these renders via position:fixed, or is a pure CSS/JS injection
   with no visible content at all — so its own box is already always
   0-height, but Streamlit's vertical block still applies its own flex
   `gap` around it regardless (gap is the flex CONTAINER's property
   between items, not something a zero-height item can opt out of on
   its own). On the kiosk, centered layout (justify-content: center)
   absorbs that slack space as part of centering the whole block, so
   it's never visible there. Mobile's flex-start layout (below) can't
   absorb it the same way — confirmed live this compounds into 150+px
   of pure dead space above the first real content on every single
   page, not just one. `display: none` looked tempting but is wrong
   here: it would ALSO hide the actual fixed-position descendant (an
   ancestor's display:none removes its whole subtree from rendering
   regardless of the child's own position), which would break the
   always-in-DOM screen-picker overlay outright the moment this global
   rule loaded. `position: absolute` instead: takes the wrapper out of
   flex flow (no more gap contribution) without affecting how its real
   fixed-position content actually renders or shows/hides itself — a
   position:fixed descendant positions against the viewport regardless
   of its immediate parent's own position property. Global, not
   mobile-scoped, since the underlying waste exists on every page; it's
   just only ever visible once a page actually scrolls. */
.stElementContainer:has(> div.stMarkdown [data-testid="stMarkdownContainer"] > style:only-child),
.stElementContainer:has(iframe),
.stElementContainer:has(.screen-picker),
.stElementContainer:has(.system-health-corner),
.stElementContainer:has(.rotation-timer-track),
.stElementContainer:has(.ticker-bar),
.stElementContainer:has(.top-alert-bar),
.stElementContainer:has(.news-alert-bar),
.stElementContainer:has(.news-alert-bar-market),
.stElementContainer:has(.commute-alert-bar),
.stElementContainer:has(.sports-alert-bar-mlb),
.stElementContainer:has(.sports-alert-bar-nhl),
.stElementContainer:has(.sports-alert-bar-nfl),
.stElementContainer:has(.sports-alert-bar-goalline),
.stElementContainer:has(.sports-alert-bar-ufc),
.stElementContainer:has(.weather-alert-bar-watch),
.stElementContainer:has(.weather-alert-bar-statement),
.stElementContainer:has(.weather-statement-bar) {
    position: absolute !important;
    width: 0 !important;
    height: 0 !important;
    overflow: hidden !important;
}

/* Phone nav pills (app.py) — jump straight to any page instead of
   waiting out the kiosk's 5-minute rotation. Hidden by default: the
   kiosk monitor is always well above the mobile breakpoint below, so
   this never actually shows there, it's just present in the DOM. */
.mobile-nav {
    display: none;
    flex-wrap: wrap;
    gap: 0.4rem;
    margin-bottom: 0.9rem;
}
/* !important on color/text-decoration: Streamlit's own markdown-link
   CSS (blue + underline, on a more specific [data-testid] selector)
   otherwise wins here — same reason .block-container above needs
   !important to hold its layout against Streamlit's base styles. Each
   nav item's real color comes from an inline style (also !important,
   since inline beats a class rule of the same importance) set in
   app.py — this is just the fallback if that's ever missing. */
.mobile-nav-item {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.32rem 0.65rem;
    border-radius: 20px;
    font-size: 0.78rem;
    font-weight: 600;
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(255,255,255,0.12);
    text-decoration: none !important;
    color: #8E8E93 !important;
}
.mobile-nav-item::before {
    content: "";
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: currentColor;
    box-shadow: 0 0 5px 1px currentColor;
}
.mobile-nav-item-active {
    background: rgba(255,255,255,0.18);
    border-color: rgba(255,255,255,0.4);
}
/* Streamlit strips inline style="" attributes from <a> tags even with
   unsafe_allow_html=True (confirmed live — it also silently injects its
   own target/rel attributes, so it's clearly running anchors through
   its own post-processing) — unlike the <span> badges elsewhere in this
   app, which do take inline color fine. Per-page classes instead, same
   beacon colors as each page's own .page-title-*::before dot. */
.mobile-nav-item-auto { color: #8E8E93 !important; }
.mobile-nav-item-home { color: #F5F5F7 !important; }
.mobile-nav-item-conflicts { color: #FF6961 !important; }
.mobile-nav-item-news { color: #FFD60A !important; }
.mobile-nav-item-markets { color: #32D74B !important; }
.mobile-nav-item-internals { color: #BF5AF2 !important; }
.mobile-nav-item-today { color: #FF9F0A !important; }
.mobile-nav-item-household { color: #A2845E !important; }
.mobile-nav-item-weather { color: #64D2FF !important; }
.mobile-nav-item-radar { color: #32ADE6 !important; }
.mobile-nav-item-sports { color: #5E5CE6 !important; }
.mobile-nav-item-scores { color: #30D5C8 !important; }
.mobile-nav-item-portfolio { color: #A78BFA !important; }
.mobile-nav-item-predictions { color: #0A84FF !important; }
.mobile-nav-item-timeline { color: #00C7BE !important; }
.mobile-nav-item-system_health { color: #B4E61D !important; }
.mobile-nav-item-maintenance { color: #8E8E93 !important; }

/* Screen picker (app.py) — session request: "bind the S key to a
   selection menu where i can pick any of the screens we've built so i
   can look for ideas without needing to sit through the rotation."
   Always in the DOM; display alone gates visibility on .screen-picker-
   open (see app.py's own ?picker=open query param). z-index above
   every other overlay in this app (jumbotron controls top out at 9999)
   — an explicit, user-invoked override should always be reachable,
   including mid-takeover. */
.screen-picker {
    display: none;
    position: fixed;
    inset: 0;
    z-index: 10000;
    align-items: center;
    justify-content: center;
}
.screen-picker.screen-picker-open { display: flex; }
.screen-picker-backdrop {
    position: absolute;
    inset: 0;
    background: rgba(5,7,12,0.78);
    backdrop-filter: blur(3px);
}
.screen-picker-panel {
    position: relative;
    width: min(680px, 90vw);
    max-height: 80vh;
    overflow-y: auto;
    background: rgba(20,24,34,0.96);
    border: 1px solid rgba(255,255,255,0.14);
    border-radius: 16px;
    box-shadow: 0 24px 60px rgba(0,0,0,0.55);
    padding: 22px 24px 26px;
}
.screen-picker-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-size: 1.05rem;
    font-weight: 700;
    color: #F5F5F7;
    margin-bottom: 16px;
}
.screen-picker-close {
    font-size: 1.6rem;
    line-height: 1;
    color: #8E8E93 !important;
    text-decoration: none !important;
    padding: 0 4px;
}
.screen-picker-close:hover { color: #F5F5F7 !important; }
.screen-picker-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 10px;
}
.screen-picker-item {
    display: flex;
    align-items: center;
    justify-content: center;
    text-align: center;
    padding: 16px 10px;
    border-radius: 12px;
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.1);
    color: #8E8E93 !important;
    text-decoration: none !important;
    font-size: 0.92rem;
    font-weight: 600;
}
.screen-picker-item:hover { background: rgba(255,255,255,0.1); border-color: rgba(255,255,255,0.25); }
.screen-picker-item-active {
    background: rgba(255,255,255,0.16);
    border-color: rgba(255,255,255,0.4);
    color: #F5F5F7 !important;
}

/* ============ TIMELINE (pages_timeline.py) ============
   Session request, after reviewing an approved concept mockup: "That
   looks kind of incredible. Yeah. Build that." — the whole day on one
   shared axis instead of the page rotation: an hour ruler + vertical
   gridlines, a glowing "now" line, and 5 stacked lanes (Weather/
   Commute/Calendar/Markets/Sports), each item styled by real state —
   already happened (dimmed), happening right now (glowing), still
   ahead (outlined) — rather than by source. CSS translated directly
   from the approved mockup artifact; positioning math (the 132px
   lane-label offset every absolutely-positioned element on the shared
   axis has to account for) lives in pages_timeline.py's own _pct/
   _axis_left, not duplicated here. */
/* Design-pass fix, session report: "it looks kind of choppy... make
   it feel more premium." Root cause, found by comparing against every
   other card in this app: .timeline-board was a flat, fully-opaque
   box with a thin border and no shadow — every OTHER card here
   (.tile, .market-pill, .score-card, the two floating corner badges)
   shares one glass recipe (semi-transparent fill + backdrop-blur +
   soft elevation shadow), and this board was the one exception,
   sitting on the same screen looking visually disconnected from
   everything around it. Same recipe applied here now, not a new one
   invented for this page. */
.timeline-board {
    --tl-sun: #d3bc8d;
    --tl-commute: #5ac8fa;
    --tl-calendar: #b9bac2;
    --tl-markets: #32d74b;
    background: rgba(16,17,22,0.72);
    backdrop-filter: blur(24px) saturate(160%);
    -webkit-backdrop-filter: blur(24px) saturate(160%);
    border: 1px solid rgba(255,255,255,0.09);
    border-radius: 20px;
    padding: 1.7rem 1.9rem 1.4rem;
    position: relative;
    overflow: hidden;
    box-shadow: 0 10px 30px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.05);
}
/* Numeric/timestamp text (.mono, applied by pages_timeline.py) — the
   same monospace stack already used elsewhere in this file (jumbotron
   pitch counts etc.), not a new Google Fonts request: this app
   deliberately dropped external font loading (see this file's own
   opening comment) in favor of one converged system stack. */
.timeline-board .mono { font-family: "SF Mono", "Menlo", "Consolas", "Roboto Mono", monospace; }
.timeline-ruler {
    position: relative;
    height: 22px;
    margin-left: 132px;
    margin-bottom: 0.4rem;
}
.timeline-ruler .tick {
    position: absolute;
    top: 0;
    transform: translateX(-50%);
    font-size: 0.72rem;
    font-weight: 600;
    color: rgba(243,243,241,0.42);
}
.timeline-lanes { position: relative; }
.timeline-gridlines { position: absolute; inset: 0; }
/* Design-pass fix: was rgba(255,255,255,0.08), the same alpha as the
   old hard lane dividers below — a dense, visible grid competing with
   the actual events for attention, part of the same "choppy,
   spreadsheet" feeling. Faded to a quiet backdrop instead; the ruler's
   own hour labels above already carry the "where am I on the day"
   information, the gridlines just need to be felt, not read. */
.timeline-gridlines .gridline {
    position: absolute;
    top: 0;
    bottom: 0;
    width: 1px;
    background: rgba(255,255,255,0.045);
}
.timeline-lanes .now-line {
    position: absolute;
    top: 0;
    bottom: 0;
    width: 2px;
    background: linear-gradient(180deg, #ff6961, rgba(255,105,97,0.15));
    z-index: 5;
    animation: timeline-now-pulse 2.4s ease-in-out infinite;
}
.timeline-lanes .now-line .now-chip {
    position: absolute;
    top: -2.55rem;
    left: 50%;
    transform: translateX(-50%);
    background: #ff6961;
    color: #1a0503;
    font-weight: 700;
    font-size: 0.74rem;
    padding: 0.28rem 0.55rem;
    border-radius: 7px;
    white-space: nowrap;
}
@keyframes timeline-now-pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.6; } }
@media (prefers-reduced-motion: reduce) { .timeline-lanes .now-line { animation: none; } }

/* Design-pass fix: a hard 1px rule at the same 0.08 alpha as the old
   gridlines, between every single lane, was the single biggest
   contributor to the "choppy" report — 5 lanes ruled off from each
   other like spreadsheet rows. Faded to match the gridlines' own new
   quieter alpha, and given real room to breathe (58px -> 68px) so the
   lanes read as soft horizontal bands, not gridded cells. */
.timeline-lanes .lane {
    display: flex;
    align-items: center;
    min-height: 68px;
    border-top: 1px solid rgba(255,255,255,0.045);
    position: relative;
}
.timeline-lanes .lane:first-child { border-top: none; }
.timeline-lanes .lane-label {
    width: 132px;
    flex: 0 0 132px;
    display: flex;
    align-items: center;
    gap: 0.55rem;
    font-size: 0.82rem;
    font-weight: 700;
    color: rgba(243,243,241,0.68);
    padding-right: 0.6rem;
}
.timeline-lanes .lane[data-lane="weather"] .lane-label { color: var(--tl-sun); }
.timeline-lanes .lane[data-lane="commute"] .lane-label { color: var(--tl-commute); }
.timeline-lanes .lane[data-lane="calendar"] .lane-label { color: var(--tl-calendar); }
.timeline-lanes .lane[data-lane="markets"] .lane-label { color: var(--tl-markets); }
.timeline-lanes .lane-track { position: relative; flex: 1 1 auto; height: 100%; min-height: 68px; }
.timeline-lanes .lane-empty {
    position: absolute;
    left: 0;
    top: 50%;
    transform: translateY(-50%);
    font-size: 0.78rem;
    color: rgba(243,243,241,0.32);
    font-style: italic;
}

.timeline-lanes .block {
    position: absolute;
    top: 50%;
    transform: translateY(-50%);
    height: 32px;
    border-radius: 9px;
    display: flex;
    align-items: center;
    padding: 0 0.65rem;
    font-size: 0.76rem;
    font-weight: 700;
    white-space: nowrap;
    overflow: hidden;
    /* Design-pass fix, found live: real calendar/sports text has no
       length cap (a long real event summary, a full matchup label) and
       was silently clipping mid-character with no visual sign anything
       was cut off. */
    text-overflow: ellipsis;
}
/* Design-pass fix: flat single-alpha fills read thin/paper-like next
   to the rest of the app's own tiles, which almost always pair a
   subtle top-to-bottom gradient with their fill — same treatment
   applied here, purely a depth cue, no new colors introduced. */
.timeline-lanes .block.state-past { background: linear-gradient(180deg, rgba(255,255,255,0.08), rgba(255,255,255,0.05)); color: rgba(243,243,241,0.42); }
.timeline-lanes .block.state-upcoming { background: linear-gradient(180deg, rgba(255,255,255,0.065), rgba(255,255,255,0.035)); border: 1px dashed rgba(255,255,255,0.35); color: rgba(243,243,241,0.68); }
.timeline-lanes .block.state-live { color: #fff; background: linear-gradient(180deg, rgba(255,255,255,0.15), rgba(255,255,255,0.08)); box-shadow: 0 0 0 1px rgba(255,255,255,0.18), 0 6px 20px -2px rgba(50,215,75,0.5); }
.timeline-lanes .block.block-approx { border: 1px dashed rgba(255,255,255,0.35); background: linear-gradient(180deg, rgba(255,255,255,0.05), rgba(255,255,255,0.03)); }
.timeline-lanes .block[style*="--sport-accent"] { color: rgb(var(--sport-accent)); background: linear-gradient(180deg, rgba(255,255,255,0.08), rgba(255,255,255,0.05)); }
.timeline-lanes .block.state-live[style*="--sport-accent"] { box-shadow: 0 0 0 1px rgba(255,255,255,0.18), 0 6px 20px -2px rgb(var(--sport-accent)); }

.timeline-lanes .marker {
    position: absolute;
    top: 50%;
    transform: translate(-50%,-50%);
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.3rem;
}
.timeline-lanes .marker .pin { width: 11px; height: 11px; border-radius: 50%; border: 2px solid var(--tl-commute); background: #0c0d11; }
.timeline-lanes .marker.state-past .pin { border-color: rgba(255,255,255,0.35); }
.timeline-lanes .marker .pin-label { font-size: 0.68rem; font-weight: 700; color: rgba(243,243,241,0.68); white-space: nowrap; }
.timeline-lanes .marker.state-past .pin-label { color: rgba(243,243,241,0.42); }

.timeline-lanes .weather-svg { position: absolute; inset: 0; width: 100%; height: 100%; }
.timeline-lanes .weather-now-temp {
    position: absolute;
    top: 2px;
    transform: translateX(-50%);
    font-size: 0.68rem;
    font-weight: 700;
    color: var(--tl-sun);
}
.timeline-lanes .sun-icon-inline {
    position: absolute;
    top: 8px;
    transform: translateX(-50%);
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.15rem;
    font-size: 0.64rem;
    color: var(--tl-sun);
    font-weight: 700;
}

/* ============ JUMBOTRON (pages_jumbotron.py / jumbotron_data.py) ============
   "Scoreboard Console" — rebuilt from scratch 2026-09-20 after the
   previous skin accumulated five separate "content is cut off"
   incidents and one live regression from this app's own global
   animation kill switch.

   Three rules this section is built on. Breaking any one of them is how
   every bug it replaced got in:

   1. ONE HEIGHT BUDGET, COMPUTED ONCE. --jumbo-viewport-h below is the
      only `vh` unit in this entire section. Everything else sizes as a
      flex/grid fraction of the already-budgeted box. The old skin
      chained calc() off 100vh in several places, then fought the app's
      stepped zoom media queries with a `zoom: 1 !important` override —
      the jumbotron is now excluded from those media queries at the
      source instead (see the `:not(:has(.jumbo-root))` selectors up by
      .block-container), so there is no specificity race left to win.

   2. PAGINATION IS THE FIT MECHANISM; overflow:hidden IS ONLY THE
      SAFETY NET. This kiosk never scrolls, so a row that doesn't fit is
      permanently invisible, not below the fold. Every list that can
      grow (Around The Leagues, standings, UFC card, batting order,
      storylines) is paged on the Python side.

   3. NOTHING WAITS ON AN ANIMATION TO BECOME VISIBLE. Animations are
      permanently off app-wide, so every element's default state here is
      already its correct final appearance. In particular the two
      full-screen overlays (.jumbo-play-overlay, .jumbo-otc-overlay) and
      the enter/exit announcement (.jumbo-transition) are PRESENCE-GATED
      — jumbotron_data.py returns None and the markup simply isn't
      emitted — so they must NEVER be given a resting opacity:0 or
      visibility:hidden here. A resting-hidden band-aid written for
      toggle-by-class elements is exactly what made the play-result
      announcement and the game-mode caption invisible for good.

   Visual language: flat rectangular panels, 1px hairlines instead of
   glow/shadow, generous padding, real per-team accent colors as a flat
   top rule (no diagonal clip-path geometry anywhere — that's what used
   to clip live content), and exactly one warm accent (--jumbo-hot)
   reserved for "live"/urgent state. Numerals use the same system font
   stack + font-variant-numeric: tabular-nums the rest of this
   stylesheet already uses for aligned digits; no separate arena font is
   loaded (see this file's own top comment on why those @imports went
   away). */
.jumbo-root {
    /* --- the single height budget --- */
    --jumbo-viewport-h: 100vh;   /* the ONLY vh unit in this section */
    --jumbo-chrome-h: 7rem;      /* kiosk top padding + the fixed bottom ticker strip */
    --jumbo-safety-h: 10px;      /* real slack so sub-pixel rounding can never clip a panel */
    --jumbo-budget-h: calc(var(--jumbo-viewport-h) - var(--jumbo-chrome-h) - var(--jumbo-safety-h));
    /* Fixed, NOT content-dependent — the whole budget depends on this
       being a number, not "however tall the marquee happens to be." */
    --jumbo-marquee-h: 62px;
    --jumbo-gap: 12px;
    /* Clearance the rail column leaves for .st-key-jumbotron_controls
       (position:fixed, left:34px, bottom:88px, ~44px tall) — confirmed
       live via a real photo of the physical TV: without it the batting
       order's last row rendered underneath the DELAY input, text
       garbled together. A fixed overlay doesn't push flowed content out
       of its own way.

       Measured rather than guessed this time: at 1920x1080 the control
       cluster's top lands 42px inside --jumbo-budget-h's bottom edge
       (bottom:120px, ~44px tall), so 76px is that intrusion plus a real
       34px margin. The previous 150px was a guess that cost ~90px of
       rail height every render — measured live as 66px of My Teams
       content and 2 full standings rows being clipped, i.e. the reserve
       itself had become the cutoff bug it was added to prevent. */
    --jumbo-controls-clear: 76px;

    /* --- palette --- */
    --jumbo-bg: #08080A;
    --jumbo-panel: #0E0E11;
    --jumbo-panel-2: #131317;
    --jumbo-sunk: #0A0A0D;
    --jumbo-line: rgba(255,255,255,0.11);
    --jumbo-line-soft: rgba(255,255,255,0.055);
    --jumbo-fg: #F2F3F5;
    --jumbo-fg-2: #AEB6C2;
    --jumbo-fg-3: #79808D;
    /* The one warm accent. Reserved for live/urgent state and for "the
       single thing that matters most" (best performer, our own
       standings row). Everything else is neutral or a real team color. */
    --jumbo-hot: #FF9F0A;
    --jumbo-ok: #32D74B;
    --jumbo-bad: #FF453A;
    --jumbo-font: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Helvetica Neue', sans-serif;

    font-family: var(--jumbo-font);
    color: var(--jumbo-fg);
    background: var(--jumbo-bg);
    height: var(--jumbo-budget-h);
    display: flex;
    flex-direction: column;
    gap: var(--jumbo-gap);
    min-height: 0;
    overflow: hidden;
}
/* Every numeral that has to line up column-to-column or frame-to-frame
   (scores, clocks, countdowns, records, percentages) opts in to tabular
   figures through this one declaration rather than each rule repeating
   it. Same stack/technique the rest of this stylesheet already uses. */
.jumbo-root .jumbo-clock,
.jumbo-root .jumbo-countdown,
.jumbo-root .jumbo-score-num,
.jumbo-root .jumbo-situ-num,
.jumbo-root .jumbo-situ-clock,
.jumbo-root .jumbo-wp-pct,
.jumbo-root .jumbo-wx-temp,
.jumbo-root .jumbo-hero-rec-v,
.jumbo-root .jumbo-gl-cd,
.jumbo-root .jumbo-gl-score,
.jumbo-root .jumbo-mini-score,
.jumbo-root .jumbo-st-rec,
.jumbo-root .jumbo-lineup-ops,
.jumbo-root .jumbo-lineup-num,
.jumbo-root .jumbo-mu-stat,
.jumbo-root .jumbo-leader-value,
.jumbo-root .jumbo-top3-score-num,
.jumbo-root .jumbo-otc-timer,
.jumbo-root .jumbo-ufc-stat-v,
.jumbo-root .jumbo-ufc-tot-a,
.jumbo-root .jumbo-ufc-tot-b {
    font-variant-numeric: tabular-nums;
    font-feature-settings: "tnum" 1;
}

/* The normal kiosk caps content at 1800px and pads it for tiles —
   right for tiles, wrong for a full-bleed scoreboard. Scoped via :has()
   so it only applies on the takeover page; a browser without :has()
   support simply renders the board at the normal width instead of
   breaking. No `zoom` override needed anymore — the stepped zoom media
   queries near the top of this file now exclude this page by selector. */
.block-container:has(.jumbo-root) {
    max-width: 100% !important;
    padding-top: 1rem !important;
    padding-left: 1.1rem !important;
    padding-right: 1.1rem !important;
    justify-content: flex-start !important;
}
/* Confirmed live: with justify-content pinned to flex-start, the gap
   above the marquee is Streamlit's own per-element vertical gap
   (repeated across several invisible 0-height containers that render
   ahead of the page body) plus the autorefresh component's iframe
   height. Collapsed only while the jumbotron is showing. */
.block-container:has(.jumbo-root) > div {
    gap: 0 !important;
}
.block-container:has(.jumbo-root) .element-container:has(iframe) {
    height: 0 !important;
    min-height: 0 !important;
    overflow: hidden !important;
}

/* ---- Marquee ---- */
.jumbo-marquee {
    flex: 0 0 var(--jumbo-marquee-h);
    height: var(--jumbo-marquee-h);
    box-sizing: border-box;
    display: flex;
    align-items: center;
    gap: 20px;
    padding: 0 22px;
    background: var(--jumbo-panel);
    border: 1px solid var(--jumbo-line);
    border-left: 3px solid var(--jumbo-hot);
    overflow: hidden;
}
.jumbo-brand {
    font-size: 22px;
    font-weight: 800;
    letter-spacing: 0.06em;
    color: var(--jumbo-fg);
    line-height: 0.95;
    flex: 0 0 auto;
}
.jumbo-brand span {
    display: block;
    color: var(--jumbo-fg-3);
    font-weight: 700;
    letter-spacing: 0.3em;
    font-size: 9px;
}
.jumbo-clock { font-size: 34px; font-weight: 700; letter-spacing: 0.02em; line-height: 1.1; flex: 0 0 auto; }
.jumbo-clock em { font-style: normal; font-size: 15px; color: var(--jumbo-fg-3); margin-left: 6px; }
.jumbo-dateline {
    font-size: 11px;
    font-weight: 600;
    color: var(--jumbo-fg-3);
    letter-spacing: 0.22em;
    white-space: nowrap;
    overflow: hidden;
}
.jumbo-spacer { flex: 1 1 auto; min-width: 0; }
.jumbo-wx {
    display: flex;
    align-items: baseline;
    gap: 9px;
    flex: 0 0 auto;
    padding: 5px 14px;
    border: 1px solid var(--jumbo-line);
    background: var(--jumbo-sunk);
}
.jumbo-wx-temp { font-size: 24px; font-weight: 700; line-height: 1; }
.jumbo-wx-loc { font-size: 9px; font-weight: 700; color: var(--jumbo-fg-3); letter-spacing: 0.24em; }

/* ---- Grid + panels ----
   Same three-column shape as before (rail / featured board / around the
   leagues). That structure was never the source of the layout bugs —
   the diagonal clip-path geometry inside the board was. */
.jumbo-grid {
    flex: 1 1 auto;
    min-height: 0;
    display: grid;
    grid-template-columns: 420px minmax(0, 1fr) 370px;
    gap: var(--jumbo-gap);
}
.jumbo-panel {
    background: var(--jumbo-panel);
    border: 1px solid var(--jumbo-line);
    display: flex;
    flex-direction: column;
    min-height: 0;
    min-width: 0;
    overflow: hidden;
}
.jumbo-col-rail {
    display: flex;
    flex-direction: column;
    gap: var(--jumbo-gap);
    min-height: 0;
    padding-bottom: var(--jumbo-controls-clear);
}
/* My Teams sizes to its own content but may shrink if it truly has to
   (clipping its own lowest-priority bottom card) rather than starving
   the standings panel, which keeps a real floor — a 4th rail card once
   squeezed standings down to 124px live. */
.jumbo-col-rail .jumbo-rail { flex: 0 1 auto; min-height: 0; }
/* The floor is sized for the largest real division this rotates
   through — 8 teams (NHL) at ~24px a row plus padding and the panel
   header. Session report this exists for: "standings are only showing
   the top 4 teams in each div." Re-measured live 2026-09-20 at a real
   8-row division. */
.jumbo-col-rail .jumbo-standings-panel { flex: 1 1 auto; min-height: 250px; }

.jumbo-ph {
    flex: 0 0 auto;
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 9px 16px;
    background: var(--jumbo-panel-2);
    border-bottom: 1px solid var(--jumbo-line);
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    color: var(--jumbo-fg-2);
    white-space: nowrap;
    overflow: hidden;
}
.jumbo-ph-t { min-width: 0; overflow: hidden; text-overflow: ellipsis; }
.jumbo-ph-r { margin-left: auto; letter-spacing: 0.14em; color: var(--jumbo-fg-3); flex: 0 0 auto; }
.jumbo-sl {
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 0.24em;
    text-transform: uppercase;
    color: var(--jumbo-fg-3);
    margin-bottom: 8px;
    flex: 0 0 auto;
}
.jumbo-quiet { color: var(--jumbo-fg-3); }

/* ---- Featured board ---- */
.jumbo-board { background: var(--jumbo-panel-2); }
/* Live state is a flat warm hairline, not a pulse — the old glow
   animation never played once the kill switch landed, so the "live"
   cue has to be a resting appearance. */
.jumbo-board-live { border-color: rgba(255,159,10,0.55); }
/* One-time win marker, session-guarded per game_id on the Python side
   so it marks the moment a win is first observed rather than re-firing
   for the whole ~15min postgame hold. Static, same reason as above. */
.jumbo-board-won { border-color: var(--jumbo-hot); box-shadow: inset 0 0 0 1px rgba(255,159,10,0.45); }
.jumbo-board-body {
    flex: 1 1 auto;
    min-height: 0;
    display: flex;
    flex-direction: column;
    overflow: hidden;
}
.jumbo-state { font-weight: 800; letter-spacing: 0.2em; color: var(--jumbo-fg-3); }
.jumbo-state-live { color: var(--jumbo-hot); display: inline-flex; align-items: center; gap: 7px; }
.jumbo-state-live i {
    width: 8px; height: 8px; border-radius: 50%;
    background: var(--jumbo-hot); display: inline-block;
}

.jumbo-matchup {
    flex: 0 0 auto;
    display: flex;
    align-items: stretch;
    border-bottom: 1px solid var(--jumbo-line-soft);
}
.jumbo-side {
    flex: 1 1 0;
    min-width: 0;
    position: relative;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 7px;
    padding: 18px 16px 20px;
    text-align: center;
}
/* The team's real color, as a flat 4px rule across the top of its own
   column. Deliberately NOT a diagonal clip-path panel — that geometry
   is what clipped real content whenever the angle or padding moved. */
.jumbo-side-rule {
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 4px;
    background: rgb(var(--side-rgb, 122,130,144));
}
.jumbo-side-dim { opacity: 0.5; }
.jumbo-logobox { width: 108px; height: 108px; display: flex; align-items: center; justify-content: center; }
.jumbo-logobox img { max-width: 100%; max-height: 100%; object-fit: contain; }
.jumbo-tname {
    font-weight: 800;
    font-size: 23px;
    line-height: 1.15;
    max-width: 100%;
}
.jumbo-side-ball { margin-right: 8px; }
.jumbo-trec { font-size: 12px; font-weight: 700; color: var(--jumbo-fg-3); letter-spacing: 0.12em; }
.jumbo-center {
    flex: 0 0 auto;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 6px;
    padding: 16px 34px;
    background: var(--jumbo-sunk);
    border-left: 1px solid var(--jumbo-line);
    border-right: 1px solid var(--jumbo-line);
}
.jumbo-score { display: flex; align-items: baseline; gap: 16px; }
.jumbo-score-num { font-size: 86px; font-weight: 800; line-height: 1.1; color: var(--jumbo-fg); }
/* A score that just changed keeps the warm accent for exactly the one
   rerun the Python-side comparison flags it — a real resting state, not
   a flash animation. */
.jumbo-score-changed { color: var(--jumbo-hot); }
.jumbo-score-sep { font-size: 44px; font-weight: 600; color: var(--jumbo-fg-3); }
.jumbo-vs {
    font-size: 13px; font-weight: 800; letter-spacing: 0.16em; color: var(--jumbo-fg-3);
    border: 1px solid var(--jumbo-line); padding: 4px 12px;
}
.jumbo-countdown { font-size: 80px; font-weight: 800; line-height: 1; letter-spacing: 0.01em; }
/* Session report: "the jays game is delayed can you make it show
   delayed instead of sitting at 0:00." A real status phrase, not a
   number, so it needs a far smaller size than the countdown digits to
   fit MLB's own longer detail_state text ("Delayed Start: Rain"). */
.jumbo-delayed {
    font-size: 30px;
    font-weight: 700;
    color: var(--jumbo-hot);
    line-height: 1.2;
    text-align: center;
    max-width: 300px;
}
.jumbo-cd-label { font-size: 10px; font-weight: 700; color: var(--jumbo-fg-3); letter-spacing: 0.32em; }
.jumbo-final-badge {
    font-size: 12px;
    font-weight: 800;
    letter-spacing: 0.34em;
    color: var(--jumbo-bg);
    background: var(--jumbo-hot);
    padding: 4px 12px;
    margin-top: 6px;
}

/* ---- Live situation strip ---- */
.jumbo-situ {
    flex: 0 0 auto;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-wrap: wrap;
    gap: 14px 26px;
    padding: 13px 22px;
    border-bottom: 1px solid var(--jumbo-line-soft);
}
.jumbo-situ-key { font-size: 27px; font-weight: 800; letter-spacing: 0.04em; color: var(--jumbo-hot); }
.jumbo-situ-clock { font-size: 27px; font-weight: 700; letter-spacing: 0.04em; }
.jumbo-situ-cell { display: flex; flex-direction: column; align-items: center; gap: 2px; }
.jumbo-situ-cap { font-size: 9px; font-weight: 800; letter-spacing: 0.26em; color: var(--jumbo-fg-3); }
.jumbo-situ-num { font-size: 27px; font-weight: 800; line-height: 1.25; }
.jumbo-situ-sep { color: var(--jumbo-fg-3); margin: 0 3px; }
/* Session request: "make it so a ball is green and a strike is red and
   make it flash when [one] comes through." The color is permanent; the
   "just happened" cue is the brighter weight/underline below, which is
   a resting style rather than a flash the kill switch would eat. */
.jumbo-ball { color: var(--jumbo-ok); }
.jumbo-strike { color: var(--jumbo-bad); }
.jumbo-count-new { border-bottom: 3px solid currentColor; padding-bottom: 1px; }
.jumbo-situ-down { font-size: 19px; font-weight: 700; color: var(--jumbo-fg); letter-spacing: 0.02em; }
.jumbo-situ-sub { font-size: 13px; font-weight: 700; color: var(--jumbo-fg-3); letter-spacing: 0.12em; }
.jumbo-chip {
    font-size: 12px;
    font-weight: 800;
    letter-spacing: 0.16em;
    padding: 5px 11px;
    border: 1px solid var(--jumbo-line);
    color: var(--jumbo-fg-2);
}
.jumbo-chip-alert { color: var(--jumbo-hot); border-color: rgba(255,159,10,0.6); }
.jumbo-chip-us { color: var(--jumbo-fg); border-color: var(--jumbo-line); }
.jumbo-chip-opp { color: var(--jumbo-fg-3); }
.jumbo-diamond { width: 44px; height: 44px; flex: 0 0 auto; }
.jumbo-diamond rect { fill: transparent; stroke: var(--jumbo-fg-3); stroke-width: 2; }
.jumbo-diamond rect.on { fill: var(--jumbo-hot); stroke: var(--jumbo-hot); }
/* A base that JUST became occupied (a real before/after comparison on
   the Python side, keyed by game_id) reads brighter and outlined —
   again a resting appearance, not a one-shot flash. */
.jumbo-diamond rect.jumbo-base-new { fill: #FFFFFF; stroke: #FFFFFF; }

/* ---- Pregame extras ---- */
.jumbo-venue {
    flex: 0 0 auto;
    text-align: center;
    font-size: 13px;
    color: var(--jumbo-fg-2);
    padding: 8px 22px 0;
}
.jumbo-probables {
    flex: 0 0 auto;
    display: flex;
    justify-content: center;
    gap: 46px;
    padding: 8px 22px 12px;
    font-size: 14px;
}
.jumbo-probable { text-align: center; }
.jumbo-probable b { color: var(--jumbo-fg); font-weight: 700; font-size: 16px; }
.jumbo-probable-cap {
    display: block;
    font-size: 9px;
    font-weight: 800;
    letter-spacing: 0.24em;
    color: var(--jumbo-fg-3);
    margin-bottom: 3px;
}

/* ---- Win probability ----
   Session feedback: "find a better way to show the win odds since its
   hard to see" — the percentages are the headline, flanking a bar thick
   enough to read the split from across the room. */
.jumbo-wp { flex: 0 0 auto; padding: 14px 30px; border-bottom: 1px solid var(--jumbo-line-soft); }
.jumbo-wp-title {
    text-align: center;
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 0.34em;
    color: var(--jumbo-fg-3);
    margin-bottom: 9px;
}
.jumbo-wp-row { display: flex; align-items: center; gap: 16px; }
.jumbo-wp-pct { font-size: 32px; font-weight: 800; flex: 0 0 76px; }
.jumbo-wp-row .jumbo-wp-pct:first-child { text-align: right; }
.jumbo-wp-bar { flex: 1 1 auto; min-width: 0; height: 26px; display: flex; border: 1px solid var(--jumbo-line); }
.jumbo-wp-seg { min-width: 0; }
.jumbo-wp-labels {
    display: flex;
    justify-content: space-between;
    font-size: 13px;
    font-weight: 700;
    color: var(--jumbo-fg-2);
    margin-top: 7px;
}

/* ---- AI blurb ---- */
.jumbo-blurb { flex: 0 0 auto; padding: 12px 24px; border-bottom: 1px solid var(--jumbo-line-soft); }
.jumbo-blurb-text { font-size: 15px; line-height: 1.5; color: var(--jumbo-fg-2); }

/* ---- Feature panel ----
   The board's one flexible section: it absorbs whatever height the
   fixed sections above and below don't use, and clips inside itself
   rather than pushing the last-play strip off the bottom of the panel.
   Everything above it is flex: 0 0 auto, so the budget is explicit. */
.jumbo-feature {
    flex: 1 1 auto;
    min-height: 0;
    overflow: hidden;
    display: flex;
}
.jumbo-feature-inner {
    flex: 1 1 auto;
    min-width: 0;
    min-height: 0;
    display: flex;
    flex-direction: column;
    justify-content: center;
    padding: 14px 24px 16px;
    overflow: hidden;
}

/* Top performers — one spotlit big, the whole leaderboard beside it. */
.jumbo-leader-card {
    flex: 0 1 auto;
    min-height: 0;
    display: flex;
    align-items: center;
    gap: 22px;
    padding: 14px 20px;
    background: var(--jumbo-sunk);
    border: 1px solid var(--jumbo-line-soft);
    overflow: hidden;
}
.jumbo-leader-photo {
    width: 84px; height: 84px;
    object-fit: cover; object-position: top;
    background: #16161B;
    border: 1px solid var(--jumbo-line);
    flex: 0 0 auto;
}
.jumbo-leader-big { flex: 0 0 auto; min-width: 0; }
.jumbo-leader-value { font-size: 48px; font-weight: 800; line-height: 1; white-space: nowrap; }
.jumbo-leader-cat {
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    color: var(--jumbo-hot);
    margin-top: 6px;
}
.jumbo-leader-name {
    font-size: 15px;
    color: var(--jumbo-fg-2);
    margin-top: 4px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.jumbo-leader-list {
    flex: 1 1 auto;
    min-width: 0;
    min-height: 0;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    justify-content: center;
    gap: 1px;
    padding-left: 22px;
    border-left: 1px solid var(--jumbo-line-soft);
    font-size: 13px;
}
.jumbo-leader-item {
    display: flex;
    justify-content: space-between;
    gap: 14px;
    padding: 4px 0;
    color: var(--jumbo-fg-3);
}
.jumbo-leader-who { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.jumbo-leader-stat { flex: 0 0 auto; }
.jumbo-leader-item-on { color: var(--jumbo-fg); font-weight: 700; }
.jumbo-leader-item-on .jumbo-leader-stat { color: var(--jumbo-hot); }

/* Postgame Game Score trio — all three at once (they're meant to be
   compared, not cycled); the best one gets the single warm accent. */
.jumbo-top3 { flex: 0 1 auto; min-height: 0; display: flex; gap: 14px; overflow: hidden; }
.jumbo-top3-card {
    flex: 1 1 0;
    min-width: 0;
    min-height: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    gap: 4px;
    padding: 12px 10px;
    background: var(--jumbo-sunk);
    border: 1px solid var(--jumbo-line-soft);
    overflow: hidden;
}
.jumbo-top3-best { border-color: rgba(255,159,10,0.55); }
.jumbo-top3-photowrap { position: relative; flex: 0 0 auto; }
.jumbo-top3-photo { width: 62px; height: 62px; object-fit: cover; object-position: top; background: #16161B; }
.jumbo-top3-logo { position: absolute; right: 0; bottom: 0; width: 22px; height: 22px; object-fit: contain; }
.jumbo-top3-name { font-size: 15px; font-weight: 700; line-height: 1.2; }
.jumbo-top3-role { font-size: 9px; font-weight: 800; letter-spacing: 0.2em; color: var(--jumbo-fg-3); text-transform: uppercase; }
.jumbo-top3-summary { font-size: 12px; color: var(--jumbo-fg-2); line-height: 1.35; overflow: hidden; }
.jumbo-top3-score { margin-top: auto; display: flex; flex-direction: column; align-items: center; }
.jumbo-top3-score-num { font-size: 28px; font-weight: 800; line-height: 1.15; }
.jumbo-top3-best .jumbo-top3-score-num { color: var(--jumbo-hot); }
.jumbo-top3-score-cap { font-size: 8px; font-weight: 800; letter-spacing: 0.2em; color: var(--jumbo-fg-3); }

/* Pregame storyline card — one full-width card at a time (session
   request: "big... take up the whole bottom part... one card at a
   time... look professional"). --story-rgb is this sport's own real
   accent, reused as a flat left rule rather than a gradient wash. */
.jumbo-story-card {
    flex: 0 1 auto;
    min-height: 0;
    display: flex;
    gap: 22px;
    padding: 16px 20px;
    background: var(--jumbo-sunk);
    border: 1px solid var(--jumbo-line-soft);
    border-left: 4px solid rgb(var(--story-rgb, 122,130,144));
    overflow: hidden;
}
.jumbo-story-photowrap { flex: 0 0 auto; }
.jumbo-story-photo {
    width: 104px; height: 104px;
    object-fit: cover; object-position: top;
    background: #16161B;
    border: 1px solid var(--jumbo-line);
    display: block;
}
.jumbo-story-photo-blank {
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 42px;
    font-weight: 800;
    color: var(--jumbo-fg-3);
}
.jumbo-story-main { flex: 1 1 auto; min-width: 0; min-height: 0; overflow: hidden; }
.jumbo-story-tag {
    display: inline-block;
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    padding: 3px 9px;
    border: 1px solid currentColor;
    color: var(--jumbo-fg-2);
    margin-bottom: 7px;
}
.jumbo-story-tag-hot { color: var(--jumbo-hot); }
.jumbo-story-tag-cold { color: #64B5F6; }
.jumbo-story-tag-career { color: #C9A227; }
.jumbo-story-tag-callup { color: var(--jumbo-ok); }
.jumbo-story-tag-injury { color: var(--jumbo-bad); }
.jumbo-story-tag-matchup { color: #B18CFF; }
.jumbo-story-tag-default { color: var(--jumbo-fg-2); }
.jumbo-story-headline { font-size: 21px; font-weight: 800; line-height: 1.2; }
.jumbo-story-name { font-size: 15px; font-weight: 700; color: var(--jumbo-fg-2); margin-top: 4px; }
.jumbo-story-stat { font-size: 13px; font-weight: 700; color: var(--jumbo-hot); letter-spacing: 0.06em; margin-top: 3px; }
.jumbo-story-text { font-size: 14px; line-height: 1.45; color: var(--jumbo-fg-2); margin-top: 8px; overflow: hidden; }

/* Live at-bat matchup — batter, strike zone, pitcher. */
.jumbo-mu { flex: 0 1 auto; min-height: 0; display: flex; align-items: stretch; gap: 16px; overflow: hidden; }
.jumbo-mu-col {
    flex: 1 1 0;
    min-width: 0;
    min-height: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    gap: 5px;
    overflow: hidden;
}
.jumbo-mu-photo { width: 72px; height: 72px; object-fit: cover; object-position: top; background: #16161B; flex: 0 0 auto; }
.jumbo-mu-tag { font-size: 9px; font-weight: 800; letter-spacing: 0.26em; text-transform: uppercase; color: var(--jumbo-fg-3); }
.jumbo-mu-name { font-size: 18px; font-weight: 700; line-height: 1.15; }
.jumbo-mu-stat-row { display: flex; gap: 20px; justify-content: center; }
.jumbo-mu-stat-block { display: flex; flex-direction: column; align-items: center; }
.jumbo-mu-stat { font-size: 26px; font-weight: 800; line-height: 1.05; }
/* Hot/cold heat comes from sports_client's own real comparisons
   (vs-pitcher history, season deltas) and, for STRIKE%, from real
   league-average thresholds — never a guess. */
.jumbo-mu-stat-hot { color: var(--jumbo-hot); }
.jumbo-mu-stat-cold { color: #64B5F6; }
.jumbo-mu-stat-cap { font-size: 8px; font-weight: 800; letter-spacing: 0.2em; color: var(--jumbo-fg-3); }
.jumbo-mu-line { font-size: 12px; color: var(--jumbo-fg-3); margin-top: 2px; }
.jumbo-matchup-vs {
    flex: 0 0 auto;
    align-self: center;
    font-size: 13px;
    font-weight: 800;
    letter-spacing: 0.16em;
    color: var(--jumbo-fg-3);
}
.jumbo-zone { flex: 0 0 auto; display: flex; flex-direction: column; align-items: center; gap: 6px; min-height: 0; }
.jumbo-zone-svg { width: 96px; height: 110px; flex: 0 0 auto; }
.jumbo-pitch-chips { display: flex; flex-wrap: wrap; justify-content: center; gap: 4px 8px; max-width: 150px; }
.jumbo-pitch-chip { font-size: 11px; font-weight: 700; letter-spacing: 0.04em; }

/* ---- Last play ---- */
.jumbo-lastplay {
    flex: 0 0 auto;
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 10px 24px;
    border-top: 1px solid var(--jumbo-line-soft);
    background: var(--jumbo-sunk);
}
.jumbo-lastplay-score { display: flex; align-items: center; gap: 9px; flex: 0 0 auto; }
.jumbo-lastplay-logo { width: 26px; height: 26px; object-fit: contain; }
.jumbo-lastplay-tally { font-size: 19px; font-weight: 800; }
.jumbo-lastplay-desc {
    flex: 1 1 auto;
    min-width: 0;
    font-size: 15px;
    color: var(--jumbo-fg-2);
    line-height: 1.3;
    overflow: hidden;
}

/* ---- My Teams rail ---- */
.jumbo-rail-body { flex: 1 1 auto; min-height: 0; overflow: hidden; }
.jumbo-hero {
    position: relative;
    padding: 8px 18px 8px 20px;
    border-bottom: 1px solid var(--jumbo-line-soft);
}
.jumbo-hero:last-child { border-bottom: none; }
/* Full-height team-color flag down the left edge — flat, no wash. */
.jumbo-hero-rule {
    position: absolute;
    left: 0; top: 0; bottom: 0;
    width: 5px;
    background: var(--tc, var(--jumbo-fg-3));
}
.jumbo-hero-nhl { --tc: #D8323F; }
.jumbo-hero-mlb { --tc: #3E7CC9; }
.jumbo-hero-nfl { --tc: #D3BC8D; }
.jumbo-hero-ufc { --tc: #D20A0A; }
.jumbo-hero-head { display: flex; align-items: center; gap: 13px; }
.jumbo-hero-head img {
    width: 46px; height: 46px; padding: 4px; box-sizing: border-box;
    object-fit: contain; flex: 0 0 auto;
    background: rgba(255,255,255,0.06);
}
.jumbo-hero-id { min-width: 0; }
.jumbo-hero-name { font-weight: 800; font-size: 20px; line-height: 1.1; white-space: nowrap; }
.jumbo-hero-div {
    font-size: 12px;
    font-weight: 600;
    color: var(--jumbo-fg-3);
    letter-spacing: 0.1em;
    text-transform: uppercase;
    margin-top: 3px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.jumbo-hero-odds { color: var(--tc, var(--jumbo-fg-2)); font-weight: 700; }
.jumbo-hero-rec { margin-left: auto; text-align: right; flex: 0 0 auto; padding-left: 10px; }
.jumbo-hero-rec-v { font-weight: 800; font-size: 26px; line-height: 1; white-space: nowrap; }
.jumbo-hero-rec-c { font-size: 8px; font-weight: 800; color: var(--jumbo-fg-3); letter-spacing: 0.26em; }
.jumbo-form { display: flex; gap: 5px; align-items: center; margin-top: 6px; }
.jumbo-form-cap { font-size: 9px; font-weight: 800; color: var(--jumbo-fg-3); letter-spacing: 0.2em; margin-right: 3px; }
.jumbo-form i { width: 9px; height: 9px; display: inline-block; }
.jumbo-form-w { background: var(--jumbo-ok); }
.jumbo-form-l { background: transparent; border: 1px solid rgba(255,69,58,0.65); }
.jumbo-gameline {
    margin-top: 5px;
    padding: 6px 12px;
    background: var(--jumbo-sunk);
    border: 1px solid var(--jumbo-line-soft);
    font-size: 15px;
    font-weight: 600;
    color: var(--jumbo-fg-2);
    line-height: 1.35;
}
.jumbo-gameline-quiet { color: var(--jumbo-fg-3); border-style: dashed; letter-spacing: 0.04em; }
.jumbo-gameline b { color: var(--jumbo-fg); font-weight: 700; }
.jumbo-gl-score { color: var(--jumbo-fg); font-weight: 800; font-size: 18px; }
.jumbo-gl-cd { color: var(--jumbo-fg); font-size: 20px; font-weight: 700; letter-spacing: 0.04em; margin-left: 9px; }
.jumbo-gl-cd-delayed { color: var(--jumbo-hot); font-size: 16px; }
.jumbo-hero-live .jumbo-gameline { border-color: rgba(255,159,10,0.5); }
.jumbo-w { color: var(--jumbo-ok); }
.jumbo-l { color: var(--jumbo-bad); }

/* ---- Batting order rail (replaces My Teams during a live MLB game) ---- */
.jumbo-lineup-head { position: relative; display: flex; align-items: center; gap: 12px; padding: 9px 16px 9px 18px; }
.jumbo-lineup-head-rule {
    position: absolute;
    left: 0; top: 0; bottom: 0;
    width: 5px;
    background: rgb(var(--side-rgb, 122,130,144));
}
.jumbo-lineup-logo { width: 38px; height: 38px; object-fit: contain; flex: 0 0 auto; }
.jumbo-lineup-headtext { min-width: 0; }
.jumbo-lineup-team { font-size: 18px; font-weight: 800; line-height: 1.1; }
.jumbo-lineup-atbat { font-size: 9px; font-weight: 800; letter-spacing: 0.26em; color: var(--jumbo-fg-3); text-transform: uppercase; }
.jumbo-lineup-head-row,
.jumbo-lineup-row {
    display: flex;
    align-items: center;
    gap: 9px;
    padding: 5px 16px 5px 18px;
    font-size: 14px;
    border-bottom: 1px solid var(--jumbo-line-soft);
}
.jumbo-lineup-head-row {
    font-size: 9px;
    font-weight: 800;
    letter-spacing: 0.2em;
    color: var(--jumbo-fg-3);
    background: var(--jumbo-sunk);
}
.jumbo-lineup-num { flex: 0 0 26px; color: var(--jumbo-fg-3); font-weight: 700; }
.jumbo-lineup-name { flex: 1 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 700; }
.jumbo-lineup-pos { flex: 0 0 32px; color: var(--jumbo-fg-3); }
.jumbo-lineup-ab { flex: 0 0 46px; text-align: right; color: var(--jumbo-fg-2); font-size: 12px; }
.jumbo-lineup-ops { flex: 0 0 46px; text-align: right; font-weight: 700; color: var(--jumbo-fg-2); }
/* OPS colored by this hitter's real, current league percentile tier
   (sports_client.ops_tier against a live qualified-hitter
   distribution), session request: "top ten percent gets brightest
   green... bottom twenty five red... dynamic so it shows exactly where
   they are in context to the entire league." */
.jumbo-lineup-ops-elite { color: #32D74B; }
.jumbo-lineup-ops-good { color: #8FD694; }
.jumbo-lineup-ops-average { color: var(--jumbo-fg-2); }
.jumbo-lineup-ops-below { color: #FF6961; }
/* The current batter gets a left accent bar rather than a full-row
   wash — deliberately, so it can't fight the OPS tier color sitting in
   the same row (a real colour clash fixed once already). */
.jumbo-lineup-row-on {
    border-left: 3px solid var(--jumbo-hot);
    padding-left: 15px;
    background: rgba(255,159,10,0.07);
}
.jumbo-lineup-row-on .jumbo-lineup-name,
.jumbo-lineup-row-on .jumbo-lineup-num { color: var(--jumbo-hot); }

/* ---- Around The Leagues ---- */
.jumbo-around-body { flex: 1 1 auto; min-height: 0; overflow: hidden; padding: 10px; display: flex; flex-direction: column; gap: 7px; }
.jumbo-mini {
    flex: 0 0 auto;
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 7px 11px;
    background: var(--jumbo-sunk);
    border: 1px solid var(--jumbo-line-soft);
}
.jumbo-around-body > .jumbo-mini { flex: 1 1 auto; max-height: 112px; }
.jumbo-mini-live { border-color: rgba(255,159,10,0.45); }
.jumbo-mini-final { opacity: 0.72; }
.jumbo-mini-teams { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.jumbo-mini-team { display: flex; align-items: center; gap: 7px; }
.jumbo-mini-team img { width: 22px; height: 22px; object-fit: contain; flex: 0 0 auto; }
.jumbo-mini-abbr { font-size: 15px; font-weight: 800; letter-spacing: 0.04em; }
.jumbo-mini-rec { font-size: 10px; color: var(--jumbo-fg-3); font-weight: 600; }
.jumbo-mini-score { margin-left: auto; font-size: 19px; font-weight: 800; }
.jumbo-mini-status {
    flex: 0 0 auto;
    max-width: 96px;
    text-align: right;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.06em;
    color: var(--jumbo-fg-3);
    text-transform: uppercase;
    line-height: 1.25;
}
.jumbo-mini-live .jumbo-mini-status { color: var(--jumbo-hot); }
.jumbo-mini-leader { font-size: 11px; color: var(--jumbo-fg-3); margin-top: 2px; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.jumbo-mini-leader-stat { color: var(--jumbo-fg-2); font-weight: 700; }

/* ---- Division standings (rotating) ---- */
.jumbo-st-body { flex: 1 1 auto; min-height: 0; overflow: hidden; padding: 8px 12px 12px; }
.jumbo-st { border: 1px solid var(--jumbo-line-soft); background: var(--jumbo-sunk); font-size: 14px; }
.jumbo-st-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 3px 12px;
    border-bottom: 1px solid var(--jumbo-line-soft);
    color: var(--jumbo-fg-2);
}
.jumbo-st-row:last-child { border-bottom: none; }
.jumbo-st-row-us { color: var(--jumbo-hot); font-weight: 800; border-left: 3px solid var(--jumbo-hot); padding-left: 9px; }
.jumbo-st-rank { flex: 0 0 18px; color: var(--jumbo-fg-3); font-weight: 700; }
.jumbo-st-logo { flex: 0 0 auto; width: 17px; height: 17px; object-fit: contain; }
.jumbo-st-team { flex: 1 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.jumbo-st-rec { flex: 0 0 auto; font-weight: 700; }
.jumbo-st-extra { flex: 0 0 40px; text-align: right; color: var(--jumbo-fg-3); }
.jumbo-st-odds { flex: 0 0 auto; text-align: right; color: var(--jumbo-hot); font-weight: 800; margin-left: 6px; }

/* ============ Presence-gated full-screen overlays ============
   READ THIS BEFORE EDITING EITHER RULE BELOW.

   Both elements are only ever in the DOM on the reruns they're meant to
   be seen — jumbotron_data.py returns None otherwise and
   pages_jumbotron.py emits nothing. There is therefore NO class toggle,
   and NO resting opacity:0/visibility:hidden here. Adding one (even
   "temporarily", even meant to be overridden by another class) makes
   them invisible forever, which is exactly the live bug this rebuild
   fixed. If it's in the DOM, it's visible. */
.jumbo-otc-overlay {
    position: fixed;
    inset: 0;
    z-index: 9997;
    display: flex;
    justify-content: center;
    background: #06070A;
    padding: 40px 56px;
    overflow: hidden;
}
.jumbo-otc-inner { display: flex; flex-direction: column; align-items: center; width: 100%; max-width: 1440px; min-height: 0; }
.jumbo-otc-title { font-size: 18px; font-weight: 800; letter-spacing: 0.3em; color: var(--jumbo-fg-3); text-transform: uppercase; }
.jumbo-otc-sub { font-size: 30px; font-weight: 800; color: var(--jumbo-fg); margin-top: 8px; }
.jumbo-otc-timer-block { display: flex; flex-direction: column; align-items: center; margin: 14px 0 24px; }
.jumbo-otc-timer { font-size: 54px; font-weight: 800; line-height: 1.05; }
.jumbo-otc-timer-cap { font-size: 11px; font-weight: 800; letter-spacing: 0.24em; color: var(--jumbo-hot); text-transform: uppercase; margin-top: 4px; }
.jumbo-otc-league {
    width: 100%;
    font-size: 12px;
    font-weight: 800;
    letter-spacing: 0.24em;
    color: var(--jumbo-fg-3);
    text-transform: uppercase;
    margin: 12px 0 5px;
}
/* Sized up for a full-screen read — session request: "make the scores a
   little bigger so you can see them from a glance." Two columns, since
   the Python side caps a page at AROUND_PAGE_SIZE rows; no overflow-y
   anywhere, because pagination (not scrolling) is what makes this fit. */
.jumbo-otc-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 9px 28px; width: 100%; min-height: 0; }
.jumbo-otc-grid .jumbo-mini { padding: 12px 18px; }
.jumbo-otc-grid .jumbo-mini-team img { width: 40px; height: 40px; }
.jumbo-otc-grid .jumbo-mini-abbr { font-size: 28px; }
.jumbo-otc-grid .jumbo-mini-rec { font-size: 13px; }
.jumbo-otc-grid .jumbo-mini-score { font-size: 42px; }
.jumbo-otc-grid .jumbo-mini-status { font-size: 16px; max-width: 150px; }
.jumbo-otc-grid .jumbo-mini-leader { font-size: 14px; }

/* Full-screen play-result announcement — session request: "add an
   animation that takes up the screen after every play. Single, Double,
   Triple, Home Run, Lineout, Strikout, Pop Out etc so i can tell what
   happened." Held for PLAY_RESULT_HOLD_SECONDS of real elapsed time by
   re-rendering across as many 5s fragment ticks as that takes, then
   simply not emitted. Sits above the out-of-town overlay (9997) but
   below the control cluster (9999), and pointer-events:none so it never
   blocks the End Session button underneath. */
.jumbo-play-overlay {
    position: fixed;
    inset: 0;
    z-index: 9998;
    display: flex;
    align-items: center;
    justify-content: center;
    pointer-events: none;
    background: rgba(6,7,10,0.92);
}
.jumbo-play-text { font-size: 92px; font-weight: 800; letter-spacing: 0.06em; text-align: center; line-height: 1.05; max-width: 90%; }
/* Green for offense succeeding, red for an out, neutral for anything
   MLB's own event field doesn't classify either way. */
.jumbo-play-hit .jumbo-play-text { color: var(--jumbo-ok); }
.jumbo-play-out .jumbo-play-text { color: var(--jumbo-bad); }
.jumbo-play-neutral .jumbo-play-text { color: var(--jumbo-fg); }

/* ---- UFC ----
   Its own two-row grid rather than the rail/board/around layout — a
   fight card is a genuinely different data shape from one team's
   evolving score. The hero takes the dominant share (session request:
   "I want the live fight to take up like the whole screen"), with the
   full card as a fixed reference strip underneath. */
.jumbo-ufc-grid {
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: 3fr minmax(0, 1fr);
}
.jumbo-ufc-hero-body {
    flex: 1 1 auto;
    min-height: 0;
    display: flex;
    flex-direction: column;
    padding: 14px 22px 16px;
    overflow: hidden;
}
.jumbo-ufc-phase {
    flex: 0 0 auto;
    text-align: center;
    font-size: 20px;
    font-weight: 800;
    letter-spacing: 0.14em;
    color: var(--jumbo-fg-3);
    text-transform: uppercase;
    margin-bottom: 10px;
}
.jumbo-ufc-phase-live { color: var(--jumbo-hot); }
.jumbo-ufc-recent-a { color: #FF6961; }
.jumbo-ufc-recent-b { color: #64B5F6; }
.jumbo-ufc-hero { flex: 1 1 auto; min-height: 0; display: flex; align-items: stretch; gap: 16px; overflow: hidden; }
.jumbo-ufc-fighter {
    flex: 1 1 0;
    min-width: 0;
    min-height: 0;
    position: relative;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-align: center;
    gap: 5px;
    padding: 14px 12px;
    background: var(--jumbo-sunk);
    border: 1px solid var(--jumbo-line-soft);
    overflow: hidden;
}
/* Red/blue corners are a broadcast convention, not each fighter's real
   color — checked live, no such data exists anywhere in ESPN's UFC
   feed, so this is deliberately not presented as one. */
.jumbo-ufc-corner-rule { position: absolute; top: 0; left: 0; right: 0; height: 4px; }
.jumbo-ufc-corner-a .jumbo-ufc-corner-rule { background: #D33A3A; }
.jumbo-ufc-corner-b .jumbo-ufc-corner-rule { background: #3A7BD3; }
.jumbo-ufc-winner { border-color: rgba(255,159,10,0.6); }
.jumbo-ufc-winner .jumbo-ufc-name { color: var(--jumbo-hot); }
.jumbo-ufc-photowrap { position: relative; flex: 0 1 auto; min-height: 0; }
.jumbo-ufc-photo { max-height: 240px; width: auto; object-fit: contain; display: block; }
.jumbo-ufc-flag { position: absolute; right: 0; bottom: 4px; width: 26px; height: 18px; object-fit: cover; }
.jumbo-ufc-name { font-size: 24px; font-weight: 800; line-height: 1.1; }
.jumbo-ufc-nick { font-size: 13px; font-style: italic; color: var(--jumbo-fg-3); }
.jumbo-ufc-recordline { display: flex; align-items: center; gap: 9px; }
.jumbo-ufc-record { font-size: 15px; font-weight: 700; color: var(--jumbo-fg-2); }
.jumbo-ufc-kd { font-size: 11px; font-weight: 800; letter-spacing: 0.12em; color: var(--jumbo-hot); border: 1px solid rgba(255,159,10,0.6); padding: 2px 7px; }
.jumbo-ufc-method { font-size: 11px; font-weight: 700; letter-spacing: 0.1em; color: var(--jumbo-fg-3); }
.jumbo-ufc-mid { flex: 0 0 auto; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; padding: 0 6px; }
.jumbo-ufc-weight { font-size: 10px; font-weight: 800; letter-spacing: 0.2em; color: var(--jumbo-fg-3); text-transform: uppercase; writing-mode: horizontal-tb; max-width: 110px; text-align: center; }
.jumbo-ufc-vs { font-size: 15px; font-weight: 800; letter-spacing: 0.14em; color: var(--jumbo-fg-3); border: 1px solid var(--jumbo-line); padding: 5px 10px; }
/* Tale of the tape — one compact row, never three stacked: this panel
   is fixed-height and already carries two photos, two names, records
   and the live stat bars below it. */
.jumbo-ufc-tot { flex: 0 0 auto; display: flex; gap: 10px; margin-top: 10px; }
.jumbo-ufc-tot-cell {
    flex: 1 1 0;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 16px;
    padding: 6px 12px;
    background: var(--jumbo-sunk);
    border: 1px solid var(--jumbo-line-soft);
    font-size: 16px;
    font-weight: 700;
}
.jumbo-ufc-tot-cap { font-size: 9px; font-weight: 800; letter-spacing: 0.2em; color: var(--jumbo-fg-3); }
.jumbo-ufc-tot-a, .jumbo-ufc-tot-b { flex: 0 0 auto; }
.jumbo-ufc-stats { flex: 0 0 auto; display: flex; gap: 18px; margin-top: 10px; }
.jumbo-ufc-stat-row { flex: 1 1 0; min-width: 0; }
.jumbo-ufc-stat-cap { font-size: 9px; font-weight: 800; letter-spacing: 0.22em; color: var(--jumbo-fg-3); text-align: center; text-transform: uppercase; }
.jumbo-ufc-stat-line { display: flex; align-items: center; gap: 9px; margin-top: 4px; }
.jumbo-ufc-stat-v { font-size: 17px; font-weight: 800; flex: 0 0 auto; }
.jumbo-ufc-stat-va { color: #FF8A84; }
.jumbo-ufc-stat-vb { color: #8FB8F0; }
.jumbo-ufc-stat-bar { flex: 1 1 auto; min-width: 0; height: 9px; display: flex; border: 1px solid var(--jumbo-line); }
.jumbo-ufc-seg { min-width: 0; }
.jumbo-ufc-seg-a { background: #D33A3A; }
.jumbo-ufc-seg-b { background: #3A7BD3; }
.jumbo-ufc-stat-names { display: flex; justify-content: space-between; font-size: 10px; font-weight: 700; color: var(--jumbo-fg-3); margin-top: 3px; }
.jumbo-ufc-card-body { flex: 1 1 auto; min-height: 0; overflow: hidden; display: flex; flex-direction: column; }
.jumbo-ufc-row {
    flex: 0 0 auto;
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 9px 20px;
    border-bottom: 1px solid var(--jumbo-line-soft);
    font-size: 16px;
}
.jumbo-ufc-row:last-child { border-bottom: none; }
.jumbo-ufc-row-main { background: var(--jumbo-sunk); }
.jumbo-ufc-row-weight { flex: 0 0 160px; font-size: 10px; font-weight: 800; letter-spacing: 0.16em; color: var(--jumbo-fg-3); text-transform: uppercase; }
.jumbo-ufc-row-fighter { flex: 1 1 0; min-width: 0; font-weight: 700; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.jumbo-ufc-row-vs { flex: 0 0 auto; font-size: 11px; color: var(--jumbo-fg-3); }
.jumbo-ufc-row-status { flex: 0 0 190px; text-align: right; font-size: 12px; font-weight: 700; letter-spacing: 0.08em; }
.jumbo-ufc-row-live { color: var(--jumbo-hot); }
.jumbo-ufc-row-final { color: var(--jumbo-fg-3); }
.jumbo-ufc-row-up { color: var(--jumbo-fg-3); }

/* ============ Game-mode enter/exit announcement (app.py) ============
   Presence-gated exactly like the two overlays above: app.py emits this
   ONLY on the single rerun where _jumbotron_active actually flipped.

   Deliberately NOT a full-screen opaque curtain. It used to be one,
   relying on `animation: ... forwards` to fade itself away — which the
   global animation kill switch permanently prevents. A full-screen
   opaque element with no way to fade would sit on top of the entire
   dashboard for a whole outer rerun cycle (up to ~75s), so the honest
   animation-free form of "mark the moment" is a compact, pointer-events
   :none banner that states it and blocks nothing. No resting-hidden
   style here either, for the same reason as the overlays above: the
   captions inside this were invisible for weeks because of one. */
.jumbo-transition {
    position: fixed;
    top: 22px;
    left: 50%;
    transform: translateX(-50%);
    z-index: 9999;
    pointer-events: none;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 4px;
    padding: 14px 34px;
    background: rgba(6,7,10,0.94);
    border: 1px solid rgba(255,255,255,0.14);
    max-width: 80vw;
    text-align: center;
}
.jumbo-transition-in { border-bottom: 3px solid #FF9F0A; }
.jumbo-transition-out { border-bottom: 3px solid rgba(255,255,255,0.3); }
.jumbo-transition-brand {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Helvetica Neue", sans-serif;
    font-size: 26px;
    font-weight: 800;
    letter-spacing: 0.06em;
    color: #F2F3F5;
    line-height: 1;
}
.jumbo-transition-brand span { color: #FF9F0A; letter-spacing: 0.22em; font-size: 12px; margin-left: 10px; }
.jumbo-transition-brand-normal {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Helvetica Neue", sans-serif;
    font-size: 24px;
    font-weight: 700;
    color: #F5F5F7;
    line-height: 1;
}
.jumbo-transition-sub {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Helvetica Neue", sans-serif;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0.24em;
    text-transform: uppercase;
    color: #AEB6C2;
}
.jumbo-transition-sub-normal {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Helvetica Neue", sans-serif;
    font-size: 12px;
    color: #8E8E93;
    letter-spacing: 0.06em;
}

/* ============ Control cluster (pages_jumbotron._controls) ============
   End Session + the live-data delay stepper — this app's only real
   interactive widgets. Grouped in one st.container(key="jumbotron_
   controls") so they lay out as a single fixed-position row via that
   key's own class rather than a bare stButton selector. Bottom-left,
   clearing the toast alert bar below it; z-index above the out-of-town
   overlay (9997) so it stays reachable if that's showing.

   bottom: 120px, raised from 88px — measured live 2026-09-20 against
   .voice-status-badge (position:fixed, left:14px, bottom:60px, ~45px
   tall, rendered by app.py whenever voice/status.py has reported in and
   NOT suppressed during a takeover the way .system-health-corner is).
   At 88px the two boxes genuinely overlapped in the same bottom-left
   corner; 120px clears the badge's own top edge with real margin. The
   rail column's own reserve (--jumbo-controls-clear) was re-measured to
   match. */
.st-key-jumbotron_controls {
    position: fixed;
    left: 34px;
    bottom: 120px;
    z-index: 9999;
    width: auto !important;
    /* Streamlit's own stVerticalBlock rule sets flex-direction: column
       at higher specificity than a plain class can beat — confirmed
       live that without !important this stacked vertically at full
       viewport width instead of sitting as a row pinned bottom-left. */
    display: flex !important;
    flex-direction: row !important;
    align-items: center;
    gap: 10px;
}
.st-key-jumbotron_controls .stElementContainer {
    width: auto !important;
    flex: 0 0 auto;
}
/* The delay stepper is its own st.fragment, which Streamlit wraps in an
   extra stLayoutWrapper > stVerticalBlock pair that defaults back to
   column layout — confirmed live: without this the stepper dropped onto
   its own column below End Session instead of sitting in the same row. */
.st-key-jumbotron_controls div[data-testid="stLayoutWrapper"] {
    width: auto !important;
    flex: 0 0 auto;
}
.st-key-jumbotron_controls div[data-testid="stVerticalBlock"] {
    display: flex !important;
    flex-direction: row !important;
    align-items: center;
    gap: 10px;
}
.st-key-jumbotron_controls div[data-testid="stButton"] button {
    background: #0E0E11;
    border: 1px solid rgba(255,255,255,0.14);
    color: #AEB6C2;
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Helvetica Neue", sans-serif;
    font-weight: 800;
    font-size: 12px;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    padding: 10px 18px;
    border-radius: 0;
    white-space: nowrap;
}
.st-key-jumbotron_controls div[data-testid="stButton"] button:hover {
    border-color: #FF9F0A;
    color: #F2F3F5;
}
.jumbo-delay-label {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Helvetica Neue", sans-serif;
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 0.2em;
    color: #79808D;
    white-space: nowrap;
}
/* Session request: "make it so i can type my ideal stream delay please.
   the plus/minus boxes are finnicky" — a real st.number_input, so
   tapping it brings up this touchscreen kiosk's own numeric keypad.
   Streamlit's built-in label is collapsed but still reserves a hidden
   row of layout height by default; zeroed out so the field sits at the
   same compact size as the button beside it. */
.st-key-jumbotron_controls label[data-testid="stWidgetLabel"] {
    display: none;
}
.st-key-jumbotron_controls div[data-testid="stNumberInputContainer"] {
    background: #0E0E11;
    border: 1px solid rgba(255,255,255,0.14);
    border-radius: 0;
    width: 84px;
}
.st-key-jumbotron_controls input[data-testid="stNumberInputField"] {
    background: transparent;
    color: #F2F3F5;
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Helvetica Neue", sans-serif;
    font-size: 18px;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    text-align: center;
    padding: 11px 6px;
}

/* ============ NIGHT MODE (night_mode.py) ============
   Session request: "get rid of the smart plug generation... replace
   [it] by a designated night mode where the display goes dark, and
   it's used as like a nightstand display... clock, weather...
   minimalist... make the colors friendly on the eyes... as little
   blue light as possible." Deliberately its own small, self-contained
   palette rather than reusing this app's normal --bone/--mut greys or
   any accent blue (#0A84FF, used all over the daytime UI) — those are
   exactly the cool/bright tones that make a 3am glance actually wake
   you up.

   Originally a dim warm amber/copper, described even then as "closer
   to a red-light flashlight... than to the rest of this kiosk" —
   session correction: "make the color like a brighter red... keep the
   dimming intact. That way you can actually read the numbers and they
   kinda pop... without unleashing a ton of blue light." Now an actual
   warm red instead of amber, same reasoning that inspired the amber
   choice in the first place — red is the literal longest-wavelength
   visible color, zero blue component by construction, the same
   physics behind a genuine red-light flashlight or a cockpit's own
   night-vision-preserving displays; brighter than the old amber was
   specifically for legibility, not because dim itself was wrong.
   Dimming behavior (night_mode.py's own overlay_alpha) is completely
   unchanged — this pass only recolors, doesn't touch how dark it gets
   at full night. */
.night-mode {
    position: fixed;
    inset: 0;
    /* Full-audit finding: this was 10000, believed to be "the highest
       z-index anywhere in this app" against jumbotron's own 9999
       ceiling — but .news-alert-bar/.email-alert-bar/.commute-alert-
       bar/.sports-alert-bar-*/.weather-alert-bar-* are ALSO 10000 (see
       .news-alert-bar's own comment: raised there, separately, to beat
       the SAME jumbotron ceiling). Two elements at an identical
       z-index resolve by DOM/paint order, not "which one is meant to
       win" — confirmed live: a road-closure toast rendered on top of
       night mode at 2:33am, the exact failure this comment already
       claimed couldn't happen. 10001 — one above every other value
       anywhere in this stylesheet (checked: nothing else exceeds
       10000) — actually is the deliberate safety net this comment
       always meant it to be: night mode is supposed to be the one
       thing on screen, guaranteed to visually win over any toast/
       ticker/badge that still tries to render underneath, rather than
       relying on every single one of those being individually
       suppressed correctly. */
    z-index: 10001;
    background: #000000;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 1.2rem;
}
/* Session report: "dim the display to the same extent that it's
   dimmed overnight normally." app.py's own regular sleep-dim overlay
   sits at z-index:20, well under .night-mode's own 10000, so it was
   rendering completely hidden underneath this view the whole time —
   see night_mode.render()'s own `dim` param for the fix. position:
   absolute (not fixed) since .night-mode itself is already the fixed,
   full-viewport containing block this needs to cover. */
.night-mode-overlay {
    position: absolute;
    inset: 0;
    pointer-events: none;
}
.night-clock {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Helvetica Neue", sans-serif;
    font-size: 13rem;
    /* Session request: "keep the background black but the red should
       pop like a bedside alarm clock — easy to see numbers, big pop
       bright digits." Follow-up: "keep fonts the same" — weight stays
       300 exactly as it was; the "pop" here comes entirely from the
       glow below (a third, hotter inner shadow layer), not from
       thickening the strokes. */
    font-weight: 300;
    line-height: 1;
    letter-spacing: -0.02em;
    color: #FF3B30;
    font-variant-numeric: tabular-nums;
    /* Session follow-up: "it's not that bright yet or, like, poppy
       yet." The R channel was already maxed (255) — there's no more
       "brighter red" left in the flat color itself, so this reaches
       for a different lever instead of just tweaking the hex again: a
       real glow, the same way an actual LED alarm clock or a neon sign
       "pops" against a dark room — light bleeding outward, not just a
       brighter fill. Static (three fixed shadow layers, tight + mid +
       wide bloom), no animation — this app's own global kill-switch
       would drop a pulsing version anyway, and a steady glow is the
       more honest read for a display that's just sitting there being a
       clock, not alerting about anything.

       Session follow-up 2: "the red should pop like a bedside alarm
       clock — easy to see numbers, big pop bright digits." Added a
       tight, near-opaque inner layer (10px @ .95) on top of the
       original two — that's what actually reads as a hot, lit source
       right at the stroke edge up close; the original 25px/60px pair
       is the softer bloom that carries the glow out to kiosk viewing
       distance. Kept both, this only adds the missing third layer
       rather than replacing what was already tuned; weight stays
       exactly as it was per the same follow-up ("keep fonts the
       same"). Background stays pure #000000 either way — this is
       glow radius/opacity, not a background change. */
    text-shadow: 0 0 10px rgba(255, 59, 48, 0.95), 0 0 34px rgba(255, 59, 48, 0.8), 0 0 75px rgba(255, 59, 48, 0.45);
}
.night-ampm {
    font-size: 3rem;
    font-weight: 400;
    margin-left: 0.8rem;
    color: #B8342A;
    vertical-align: middle;
}
.night-date {
    font-size: 1.7rem;
    font-weight: 400;
    color: #9C2E24;
    letter-spacing: 0.02em;
}
.night-weather {
    display: flex;
    align-items: center;
    gap: 0.9rem;
    margin-top: 0.8rem;
    color: #9C2E24;
}
.night-weather-icon {
    width: 2.2rem;
    height: 2.2rem;
    display: flex;
    color: #D9382A;
}
.night-weather-icon svg {
    width: 100%;
    height: 100%;
}
.night-weather-temp {
    font-size: 2rem;
    font-weight: 500;
    color: #FF3B30;
    /* Same "pop like a bedside alarm clock" pass as .night-clock just
       above — the other digit readout on this screen, so it gets the
       same third, tighter inner-glow layer for consistency. Weight
       untouched (see .night-clock's own comment — "keep fonts the
       same"). */
    text-shadow: 0 0 7px rgba(255, 59, 48, 0.9), 0 0 18px rgba(255, 59, 48, 0.6), 0 0 40px rgba(255, 59, 48, 0.3);
    font-variant-numeric: tabular-nums;
}
.night-weather-cond {
    font-size: 1.4rem;
}
.night-weather-low {
    font-size: 1.4rem;
    padding-left: 0.9rem;
    border-left: 1px solid #3D1512;
}
/* Session request: "tomorrow's forecast high is nice" — same treatment
   as .night-weather-low just above, its own separator since both can
   show at once (tonight's low, tomorrow's high). */
.night-weather-high {
    font-size: 1.4rem;
    padding-left: 0.9rem;
    border-left: 1px solid #3D1512;
}
/* Session history: "subtle urgency... a little tab that shows it's
   still active when I wake up" (small static corner pill) -> "make it
   bigger and write it out fully... not very visible in the corner"
   (bigger pill, real content) -> "like a modified headline bar... dash
   across the top like we do on the main page... without the red or the
   colors" (tried as a scrolling ticker, reusing ticker.py's own
   ticker-scroll keyframe) -> this pass, correcting that last guess:
   "centered in the middle, please, just like on the main display."
   That's .headline-rotation below, not the scrolling bottom ticker —
   a static, full-width, CENTERED bar is the real reference. Static
   again now (no animation, so .night-ticker-track's entry in the
   global animation kill-switch's own exception list above it in this
   file — the one right under `* { animation: none !important; }` —
   was removed along with it; nothing here needs that carve-out
   anymore). Still deliberately the same warm amber family as the rest
   of this screen, not .headline-rotation's own severity-tiered
   blue/amber/red/critical gradient — "without the red or the colors"
   was explicit from the start and still holds; only .headline-
   rotation's SHAPE (fixed, full-width, centered text) got borrowed,
   not its coloring. Multiple simultaneous items (weather + a road
   closure both active) join on one centered line with a dot separator
   rather than rotating between them — .headline-rotation's own
   rotation needs real timing state across many more sources; night
   mode realistically never has more than two, so one joined line is
   the proportionate version, not a scaled-down copy of that machinery.
   position:absolute (not fixed) — .night-mode itself is already the
   fixed, full-viewport containing block this needs to span. */
.night-ticker {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    text-align: center;
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Helvetica Neue", sans-serif;
    font-size: 2rem;
    font-weight: 600;
    letter-spacing: 0.01em;
    line-height: 1.3;
    color: #FF3B30;
    background: rgba(24, 9, 7, 0.85);
    border-bottom: 1px solid rgba(255, 59, 48, 0.35);
    padding: 1.15rem 2.5rem;
}
.night-ticker-dot {
    display: inline-block;
    width: 0.5rem;
    height: 0.5rem;
    border-radius: 50%;
    background: #FF3B30;
    margin: 0 0.9rem;
    vertical-align: middle;
}
/* Session request: "make sure [the bedtime timer] appears on all
   screens" — night mode used to have no bedtime content at all (it
   starts at a flat 9:30pm, which can land BEFORE a later real bedtime,
   see app.py's own _night_mode_day_end comment), and .night-mode's own
   z-index:10001 sits well above .jumbo-leave-ticker's 10, so that
   element would've rendered invisibly underneath this screen anyway —
   night_mode.py embeds sleep_tracker.countdown_span_html's raw span
   directly inside this view's own single markdown call instead. Same
   "without the red or the colors" rule .night-ticker's own comment
   already established for this screen — no severity-tiered blue/amber/
   red gradient here, just this screen's one warm family throughout;
   .night-bedtime-cta (added once the real 10-minute call-to-action
   window starts, see BEDTIME_CTA_MINUTES) only brightens/glows within
   that same red, the same escalation language .night-clock's own glow
   already uses for "this is the important thing on screen." */
/* Session request: "make the get into bed timer on the night page
   bigger so I can actually see it... I wanna know exactly when I need
   to be in bed." 1.6rem read as an afterthought next to .night-clock's
   own 13rem — this IS the actionable thing on this screen once it's
   showing, same "sized up so it's actually readable at kiosk viewing
   distance" fix .jumbo-leave-ticker's own CSS comment already
   documents for the exact same complaint on the leave timer. Still
   deliberately smaller than the clock itself (that stays the one
   unmissable focal point of this screen) but now closer in weight to
   .night-ampm than to .night-weather-cond. */
.night-bedtime {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Helvetica Neue", sans-serif;
    font-size: 4rem;
    font-weight: 700;
    letter-spacing: 0.01em;
    color: #D9382A;
    font-variant-numeric: tabular-nums;
}
.night-bedtime-cta {
    color: #FF3B30;
    text-shadow: 0 0 26px rgba(255, 59, 48, 0.65), 0 0 56px rgba(255, 59, 48, 0.35);
}
/* Session request: "when it says get into bed, we get a little timer
   that shows when the screen's going to go to sleep... how long I
   have to stare at my beautiful clock." Deliberately a small secondary
   detail next to .night-bedtime-cta, not competing with it — smaller,
   no glow, same "plainest treatment" reasoning .night-wakeup's own
   comment already gives for a fact that's real but not the main
   focus. */
.night-sleep-countdown {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Helvetica Neue", sans-serif;
    font-size: 1.3rem;
    font-weight: 500;
    letter-spacing: 0.01em;
    color: #9C2E24;
    margin-top: 0.3rem;
}
/* Session request: "the leave in timer [can] show up during the night
   screen... just a heads up, you're gonna be waking up soon, buddy,
   but not in a very serious... way." Deliberately the plainest
   treatment on this screen — no glow, no brightening tier the way
   .night-bedtime-cta gets in its final stretch — this is explicitly
   NOT meant to read as urgent, just a quiet fact sitting there. Same
   warm family, dimmer than .night-bedtime since it's the lesser of
   the two on the rare occasion both could theoretically show at once. */
.night-wakeup {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Helvetica Neue", sans-serif;
    font-size: 1.5rem;
    font-weight: 500;
    letter-spacing: 0.01em;
    color: #9C2E24;
}
/* Session request: "have the TV turn on like an hour before I have to
   get up... this same thing that says like get up in blah blah blah...
   if I wake up I know how much time I have and whether it's worth
   going back to bed." Deliberately given the SAME prominent, bold
   treatment as .night-bedtime/.night-bedtime-cta just above (not
   .night-wakeup's deliberately-calm styling) -- this is meant to be
   read at a glance the moment the TV wakes up for it, same "the
   actionable thing on this screen" role bedtime already has in its
   own window. */
.night-wake {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Helvetica Neue", sans-serif;
    font-size: 4rem;
    font-weight: 700;
    letter-spacing: 0.01em;
    color: #D9382A;
    font-variant-numeric: tabular-nums;
}
.night-wake-cta {
    color: #FF3B30;
    text-shadow: 0 0 26px rgba(255, 59, 48, 0.65), 0 0 56px rgba(255, 59, 48, 0.35);
}
/* Session request: "I think tomorrow's first commitment is nice."
   Purely informational, same calm treatment as .night-wakeup. */
.night-tomorrow {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Helvetica Neue", sans-serif;
    font-size: 1.5rem;
    font-weight: 500;
    letter-spacing: 0.01em;
    color: #9C2E24;
}

/* Phone breakpoint. Everything above this point is untouched at any
   width above it (including the kiosk monitor, always far wider) —
   nothing in this block redefines a rule, it only adds overrides that
   apply exclusively below 640px. Built and checked against an actual
   375px viewport (see session history), not guessed from the desktop
   CSS alone: the block-container's forced vertical centering in
   particular looked fine at kiosk width but left real content stranded
   off-screen on a phone, which is why it's turned off here rather than
   just resized. */
@media (max-width: 640px) {
    .mobile-nav { display: flex; }

    .block-container {
        padding-top: 1rem;
        padding-bottom: 5rem;
        padding-left: 1rem;
        padding-right: 1rem;
        justify-content: flex-start !important;
    }

    /* Hero row: side-by-side (clock left, weather right) only works
       with real horizontal room. Stacked and left-aligned reads far
       better one-handed than two cramped, wrapping halves. */
    .hero-row {
        flex-direction: column;
        align-items: stretch;
        gap: 0.7rem;
    }
    .hero-weather { text-align: left; }
    .weather-condition { justify-content: flex-start; }
    .weather-extras { justify-content: flex-start; flex-wrap: wrap; }

    /* The kiosk's giant "readable from across the room" type is the
       opposite of what a phone held at arm's length needs — scaled
       down across every oversized hero/headline element. */
    .clock { font-size: 2.5rem; }
    .date-sub { font-size: 1.05rem; }
    .weather-condition-label { font-size: 1.1rem; }
    .weather-extra { font-size: 1.05rem; padding: 0.35rem 0.8rem; }
    .weather-icon svg { width: 2.3rem; height: 2.3rem; }
    .confidence-value { font-size: 4rem; }
    .internals-verdict { font-size: 1.3rem; }
    .confidence-hero .internals-verdict { font-size: 1.6rem; }
    .internals-context { font-size: 1rem; }
    .internals-ratio-tile .tile-value { font-size: 2.2rem; }
    .commute-tile .tile-value { font-size: 2.4rem; }
    .commute-tile .tile-prev { font-size: 1.05rem; }
    .commute-tile .severity-caption.compact { font-size: 1rem; }
    .leave-headline { font-size: 1.9rem; }
    .storm-headline { font-size: 1.9rem; }
    .game-countdown-headline { font-size: 1.4rem; }
    /* .headline-rotation.leave-headline (a real leave candidate showing
       via the unified rotation) already inherits .leave-headline's own
       1.9rem above at equal specificity to its base 2rem, and wins on
       source order — this covers the other 3 candidates (storm/
       weather-statement/news), which only ever carry .headline-rotation
       alone and would otherwise stay at the full desktop 2rem here. */
    .headline-rotation { font-size: 1.9rem; }
    /* .mini-jumbo's own children set their own absolute rem sizes
       (they don't inherit .headline-rotation's font-size above), so
       they need their own mobile downsize here too. */
    .mini-jumbo-logo { height: 1.85rem; width: 1.85rem; }
    .mini-jumbo-abbr { font-size: 1rem; }
    .mini-jumbo-score { font-size: 1.5rem; }
    .mini-jumbo-status { font-size: 0.9rem; }
    .mini-jumbo-wp { font-size: 0.82rem; }
    .mini-jumbo-base { width: 7px; height: 7px; }
    /* Same reasoning — .bedtime-headline's own 2.4rem is an absolute
       size too, so it also needs its own explicit mobile downsize
       rather than inheriting .headline-rotation's 1.9rem above (which
       it already out-specificities anyway, so it wouldn't shrink
       without this). */
    .bedtime-headline { font-size: 2rem; }

    /* Design-pass fix, found live: the whole night-mode screen (night_
       mode.py) had zero mobile-specific sizing — .night-ticker's own
       2rem font + 2.5rem side padding leaves ~295px for real text on a
       375px phone, easy to wrap awkwardly since night mode's own "join
       on one centered line with a dot separator" convention (see that
       class's own comment) doesn't otherwise account for a narrow
       viewport. Scoped to this one element (not a full night-mode
       mobile pass) — this is the one absolute-sized night element an
       earlier audit specifically flagged as still missing a downsize
       despite the explicit "appears on all screens" requirement its
       own neighboring comment documents. */
    .night-ticker { font-size: 1.4rem; padding: 0.9rem 1.2rem; }

    /* Session report: "when there's a red headline or the leave in
       badge it covers the clock and weather." These, .top-alert-bar,
       and .weather-statement-bar are all position:fixed with hardcoded
       top:Npx stacking offsets — a deliberate fix (see each class's own
       comment above) for the KIOSK's forced vertical-centering layout,
       which pushes tall content off both the top and bottom of the
       viewport. Mobile's block-container is flex-start, not centered,
       so it never had that problem to begin with — but it inherited
       the fixed positioning anyway. That was harmless while a separate
       bug left ~500px of dead space above the real hero row (see the
       .stElementContainer:has(...) rule above, "Fix huge dead-space
       gap" commit): the fixed banners just floated over blank space.
       Once that dead space was removed, the hero row moved up to meet
       them, and now they float over the clock/weather instead. Static
       here instead of fixed: each one only ever takes up real space
       exactly when it's actually rendered, pushing whatever comes after
       it (ultimately the clock) down by its own height, rather than
       reserving a permanent gap or pinning over real content. The
       hardcoded top offsets (88px/184px/194px/300-360px) that used to
       stack these regardless of which combination was showing are now
       meaningless once they're back in normal flow, so they're dropped
       instead of overridden.

       Audit fix — .headline-rotation added to this list too: it never
       was originally, which meant the 3 candidates that don't also
       carry .leave-headline (storm/weather-statement/news) stayed
       position:fixed on mobile and could still cover the clock/weather,
       reintroducing the exact collision this whole rule exists to
       prevent — confirmed live (offsetParent was BODY, not null, i.e.
       genuinely static, for .leave-headline itself via its own listing
       here, but .headline-rotation alone had no equivalent entry). */
    .top-alert-bar, .weather-statement-bar, .leave-headline,
    .storm-headline, .game-countdown-headline, .headline-rotation {
        position: static;
        top: auto;
        left: auto;
        transform: none;
        margin: 0 0 0.7rem;
    }
    .leave-headline, .storm-headline, .game-countdown-headline {
        width: fit-content;
        margin-left: auto;
        margin-right: auto;
    }
    /* .leave-headline's own "overdue" pulse (see @keyframes
       leave-headline-pulse-overdue above) bakes translateX(-50%) into
       every frame because on the desktop/kiosk layout above, that's how
       the element stays centered while position:fixed — its own
       comment says as much. Now that this class is position:static up
       above (centered with margin:auto instead), that same translateX
       would instead shift the headline sideways by half its own width
       on every pulse. Same shadow/scale pulse, transform trimmed down
       to just the scale component. */
    @keyframes leave-headline-pulse-overdue-mobile {
        0%, 100% { text-shadow: 0 0 22px rgba(255,69,58,0.5); transform: scale(1); }
        50% { text-shadow: 0 0 40px rgba(255,69,58,0.9), 0 0 70px rgba(255,69,58,0.4); transform: scale(1.03); }
    }
    .leave-headline.intensity-overdue {
        animation: leave-headline-pulse-overdue-mobile 0.7s ease-in-out infinite;
    }
    .news-breaking-label { font-size: 1.15rem; }
    .tile-value { font-size: 2rem; }
    .market-hero-value { font-size: 1.5rem; }
    .morning-briefing { padding: 0.8rem 1.1rem; }
    .morning-headline { font-size: 0.72rem; }
    .morning-body { font-size: 1.08rem; }
    .page-title { font-size: 1.2rem; }

    /* Streamlit stacks st.columns() grids into single-column full-width
       blocks below its own ~640px internal breakpoint already — every
       tile grid (Home, Markets, Internals, Weather's day columns,
       Sports, Conflicts) rides on that for free, nothing to add here. */

    /* Static top banners: fine to wrap onto a second line at this
       width. The bottom toast bars (breaking-news/commute) are left
       alone — their intro animation's translateX math assumes a single
       unwrapped line (see the toast-*-intro keyframes above), so they
       just get smaller text instead of wrapping. */
    .top-alert-bar, .weather-statement-bar, .regime-bar {
        flex-wrap: wrap;
        padding: 0.6rem 1rem;
    }
    .news-alert-bar, .news-alert-bar-market, .commute-alert-bar,
    .sports-alert-bar-mlb, .sports-alert-bar-nhl, .sports-alert-bar-nfl,
    .sports-alert-bar-goalline, .sports-alert-bar-ufc {
        padding: 0.7rem 1rem;
    }
    .news-alert-headline, .top-alert-headline { font-size: 0.95rem; }
    .sports-alert-score { font-size: 1.15rem; }
    .sports-alert-score img { width: 1.5rem; height: 1.5rem; }

    /* News/agenda rows: headline + meta side by side needs width
       neither has at this size — meta drops to its own line instead of
       squeezing the headline. */
    .news-feed-row {
        flex-wrap: wrap;
    }
    .news-feed-meta {
        flex-basis: 100%;
    }
    .agenda-feed-list .news-feed-headline { font-size: 1.25rem; }
    .agenda-feed-list .news-feed-meta { font-size: 1rem; }

    /* The kiosk never scrolls (the whole page is sized to fit one
       screen, see .block-container above), so this fixed bottom
       ticker's 92%-opaque background never had anything to actually
       hide behind it. Mobile pages are much taller and now genuinely
       scroll — confirmed live that page content ghosts through right
       at that 8% gap wherever it lands under the ticker. Bumped to
       near-fully-opaque here rather than globally, since it's only
       ever been a problem once scrolling entered the picture. */
    .ticker-bar { background: rgba(8,8,11,0.98); }

    /* Confirmed live: position:fixed pins this to the same viewport
       spot regardless of scroll, so on a genuinely scrolling mobile
       page it permanently sits on top of whatever real content
       happens to land there (a market-pill, in one live check) —
       blocking taps on it and just adding clutter. It's AI-provider
       debug telemetry, not something a quick phone glance needs; the
       kiosk (where scrolling never happens, so this never overlaps
       anything) keeps it. */
    .system-health-corner { display: none; }

    /* Same position:fixed-on-a-scrolling-phone-page bug as
       .system-health-corner just above, same fix — see that rule's
       own comment. */
    .brdn-ticker { display: none; }

    /* The jumbotron's 3-column bento is built for a 1080p wall, not a
       phone — stack it and let the page scroll like the other mobile
       views do, rather than crushing three panels into 375px. */
    .jumbo { height: auto; }
    .jumbo-grid { grid-template-columns: 1fr; }
    .jumbo-digit { font-size: 46px; }
    .jumbo-countdown { font-size: 44px; }
    .jumbo-logobox { width: 62px; height: 62px; }
    .jumbo-dateline, .jumbo-wx { display: none; }
}
</style>
"""


def inject():
    import streamlit as st
    st.markdown(CSS, unsafe_allow_html=True)
