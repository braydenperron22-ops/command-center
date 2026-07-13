"""Apple-style dark glass CSS injected once at app start."""

CSS = """
<style>
#MainMenu, header, footer { visibility: hidden; }
.block-container {
    padding-top: 1.8rem;
    padding-bottom: 4.6rem;
    max-width: 1450px;
    min-height: calc(100vh - 4.6rem) !important;
    display: flex !important;
    flex-direction: column !important;
    justify-content: center !important;
}

.block-container > div {
    flex-shrink: 0;
}

html, body, [class*="css"] {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Helvetica Neue", sans-serif;
}

.hero-row {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 0.4rem;
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
    color: #ABB2C4;
    font-weight: 500;
}

.weather-extras {
    display: flex;
    justify-content: flex-end;
    gap: 0.8rem;
    margin-top: 0.6rem;
}

/* Big enough to read from across the room, same as the rest of this
   kiosk's hero text — these used to be smaller than the date line
   beneath them, which was backwards given they're time-sensitive
   conditions worth noticing. Color/background are set inline per
   render now (UV scales orange->vibrant red with magnitude, rain
   scales pale->deep blue with proximity), not fixed here. */
.weather-extra {
    font-size: 1.7rem;
    font-weight: 700;
    padding: 0.45rem 1rem;
    border-radius: 14px;
    border: 2px solid currentColor;
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
    color: #ABB2C4;
}

.market-metric-value {
    font-size: 1.3rem;
    font-weight: 600;
    color: #F5F5F7;
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
   the old background elements did — depth without motion. */
.tile, .market-pill, .news-feed-list {
    background: rgba(12,12,16,0.86);
    border: 1px solid rgba(255,255,255,0.09);
    border-radius: 16px;
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

/* Market Internals: the Confidence Index is the headline of that page,
   not a peer to the three ratio tiles below it — a much larger value
   (bigger than the clock, since this is the one thing that page exists
   to show) and centered layout set it apart. */
.confidence-hero {
    align-items: center;
    text-align: center;
    padding-top: 0.8rem;
    padding-bottom: 0.7rem;
}
.confidence-value {
    font-size: 4.2rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    color: #F5F5F7;
    line-height: 1.1;
    margin: 0.1rem 0 0.35rem;
}
.confidence-metrics {
    width: 100%;
    max-width: 26rem;
    margin-top: 0.4rem;
}
/* Market Internals' 3 supporting ratio tiles — deliberately more
   compact than the shared .tile padding, since they're secondary
   content next to the confidence hero and this page needs real margin
   to fit reliably across zoom levels, not just at exactly 100%. */
.internals-ratio-tile {
    padding-top: 1.1rem;
    padding-bottom: 1rem;
}
/* Tighter than the default .market-metric row spacing — this page's
   hero already has a lot competing for vertical room (value + badge +
   3 rows + caption), and needs to fit comfortably even when a viewer
   runs their browser above 100% zoom, not just exactly fill 1200px at
   the nominal scale. */
.confidence-metrics .market-metric {
    padding: 0.35rem 0;
}

.tile-extra {
    margin-top: 0.5rem;
    padding-top: 0.5rem;
    height: 1.2em;
    font-size: 0.8rem;
    color: #ABB2C4;
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

.badge-bad { background: rgba(255,69,58,0.18); color: #FF6961; }
.badge-good { background: rgba(50,215,75,0.18); color: #32D74B; }
.badge-neutral { background: rgba(10,132,255,0.14); color: #5AC8FA; }
.badge-inline { background: rgba(255,255,255,0.08); color: #D6D6DC; }

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

.ticker-item-soon {
    color: #FFD60A;
    font-weight: 600;
}

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
    z-index: 15;
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
}
/* Generic market-news items aren't a surprise worth a red alert, but
   should still visibly take over the strip like breaking news does —
   solid black instead signals "new headline" without false urgency. */
.news-alert-bar-market {
    background: linear-gradient(90deg, #0a0a0c 0%, #1c1c20 50%, #0a0a0c 100%);
    box-shadow: 0 -4px 24px rgba(0,0,0,0.45);
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
    z-index: 15;
    display: flex;
    align-items: center;
    gap: 1.1rem;
    padding: 0.9rem 1.5rem;
    border-top: 2px solid rgba(255,255,255,0.25);
    overflow: hidden;
    background: linear-gradient(90deg, #7a4a0f 0%, #b3811a 50%, #7a4a0f 100%);
    box-shadow: 0 -4px 24px rgba(179,142,20,0.35);
}

/* Persistent top banner: holds the latest red (important) headline for
   up to TOP_ALERT_HOLD_SECONDS, or until the next one replaces it. Sits
   in normal document flow above the hero row (not fixed/overlaid) — it's
   static content, so there's no animation or backdrop-filter here to
   fight the per-second rerun the way the bottom bar's intro sequence did. */
.top-alert-bar {
    display: flex;
    align-items: center;
    gap: 0.9rem;
    padding: 0.7rem 1.5rem;
    margin-bottom: 0.9rem;
    border-radius: 12px;
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
   nothing active, so the two never appear at once. */
.weather-statement-bar {
    display: flex;
    align-items: center;
    gap: 0.9rem;
    padding: 0.5rem 1.3rem;
    margin-bottom: 0.5rem;
    border-radius: 12px;
    background: rgba(255,159,10,0.16);
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

/* Persistent macro-regime banner — see regime.py/regime_bar.py. Same
   dot+label+text shape as the weather-statement bar above, tone-colored
   like everything else in the app (good/bad/neutral) rather than a
   fixed color, since what this says can genuinely be favorable,
   unfavorable, or a growth/inflation-vs-risk-appetite mismatch. */
.regime-bar {
    display: flex;
    align-items: center;
    gap: 0.9rem;
    padding: 0.7rem 1.5rem;
    margin-bottom: 0.9rem;
    border-radius: 12px;
    background: rgba(255,255,255,0.05);
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
    color: #ABB2C4;
}
.regime-text {
    font-size: 1.05rem;
    font-weight: 500;
    color: #F5F5F7;
}

.news-breaking-label {
    position: absolute;
    left: 0;
    right: 0;
    text-align: center;
    font-size: 1.6rem;
    font-weight: 800;
    color: #FFFFFF;
    text-transform: uppercase;
    pointer-events: none;
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

/* Stretch-then-slide toast intro (news.render_alert_bar,
   commute_reminder.render_bar) — a real CSS animation rather than
   per-rerun inline styles interpolated via `transition`. A transition
   only has something to interpolate FROM if the browser already holds
   the previous value, which breaks the moment reruns get infrequent
   enough that Streamlit re-emits the whole element fresh (5s
   autorefresh, was 1s) — it snapped straight to wherever the most
   recent rerun's inline style landed instead of animating through the
   gap. A CSS `animation` doesn't have that problem: the caller sets
   `animation-delay: -{elapsed}s` (a negative delay resumes a clip
   partway through, a standard CSS mechanism) once per rerun, and the
   browser's own render loop plays it smoothly from there regardless of
   how long until the next rerun. Percentages below encode
   STRETCH_END=1.8s/SLIDE_END=3.0s from news.py/commute_reminder.py —
   keep in sync if either changes. */
@keyframes toast-label-intro {
    0%    { opacity: 0; letter-spacing: 0em; transform: translateX(0%); }
    60%   { opacity: 1; letter-spacing: 0.5em; transform: translateX(0%); }
    90.8% { opacity: 0; letter-spacing: 0.5em; transform: translateX(-107.7%); }
    100%  { opacity: 0; letter-spacing: 0.5em; transform: translateX(-140%); }
}
@keyframes toast-headline-intro {
    0%    { opacity: 0; transform: translateX(16px); }
    60%   { opacity: 0; transform: translateX(16px); }
    90.8% { opacity: 1; transform: translateX(3.7px); }
    100%  { opacity: 1; transform: translateX(0px); }
}
.toast-label-anim { animation: toast-label-intro 3s linear forwards; }
.toast-headline-anim { animation: toast-headline-intro 3s linear forwards; }

/* Scoped to .news-alert-tag specifically — these category classes are
   reused on .news-feed-row (below) for just a left-border accent color,
   and that row must NOT pick up this solid pill background too. */
.news-alert-tag.news-cat-fed-boc { background: rgba(191,90,242,0.9); color: #2b0f3d; }
.news-alert-tag.news-cat-data-surprise { background: rgba(90,200,250,0.9); color: #0a2c3d; }
.news-alert-tag.news-cat-earnings { background: rgba(50,215,75,0.9); color: #0b2b12; }
.news-alert-tag.news-cat-macro-shock { background: rgba(255,255,255,0.9); color: #7a0f10; }
.news-alert-tag.news-cat-market-news { background: rgba(255,214,10,0.9); color: #4d3c00; }
.news-alert-tag.news-cat-mergers { background: rgba(255,159,10,0.9); color: #4d2c00; }
.news-alert-tag.news-cat-milestone { background: rgba(100,210,255,0.9); color: #0a2c3d; }

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

.conflict-headlines {
    margin-top: 0.7rem;
    padding-top: 0.6rem;
    border-top: 1px solid rgba(255,255,255,0.08);
}

.conflict-headline {
    font-size: 0.82rem;
    color: #D6D6DC;
    line-height: 1.4;
    margin-bottom: 0.4rem;
}
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

/* Standalone headline at the top of the Today page — promoted out of
   the agenda card entirely (see pages_today._render_leave_headline) so
   it's the first thing on screen, not nested inside another tile.
   Plain bold text with a soft glow rather than a boxed card — reads as
   a headline/statement, not another chip competing with the agenda
   for attention right below it. Distinct from the transient bottom-bar
   toast (commute_reminder.render_bar), which still owns the "Leave
   now" moment once this stops rendering. */
.leave-headline {
    text-align: center;
    font-size: 2.6rem;
    font-weight: 800;
    color: #FF453A;
    letter-spacing: -0.01em;
    margin: 0 0 0.6rem;
    text-shadow: 0 0 22px rgba(255,69,58,0.45);
}

/* Today page's agenda only — same news-feed-row shape the News page
   uses for its own (much longer, faster-scanned) list, but scaled up
   here since this list is short and meant to be read at a glance, not
   skimmed. */
.agenda-feed-list.news-feed-list {
    padding: 0.5rem 1.5rem;
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
    color: #ABB2C4;
}
</style>
"""


def inject():
    import streamlit as st
    st.markdown(CSS, unsafe_allow_html=True)
