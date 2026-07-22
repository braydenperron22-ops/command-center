"""Apple-style dark glass CSS injected once at app start."""

CSS = """
<style>
/* Jumbotron faces only (pages_jumbotron.py) — the rest of the kiosk
   deliberately stays on the system font stack below. @import has to be
   the first thing in the sheet to be valid CSS at all, which is why
   it sits above even the Streamlit chrome rules. Every jumbo-* rule
   names real fallbacks, so a blocked/slow font request costs the
   arena look, not the layout. */
@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Oswald:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;600;700;800&display=swap');

#MainMenu, header, footer { visibility: hidden; }

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
   banners use above it. */
.morning-briefing {
    font-size: 1.3rem;
    line-height: 1.5;
    color: #E5E5EA;
    background: rgba(255,255,255,0.05);
    backdrop-filter: blur(24px) saturate(160%);
    -webkit-backdrop-filter: blur(24px) saturate(160%);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 16px;
    padding: 0.9rem 1.4rem;
    margin-bottom: 0.8rem;
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
    color: #ABB2C4;
}

.market-metric-value {
    font-size: 1.3rem;
    font-weight: 600;
    color: #F5F5F7;
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
    font-size: 6.4rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    color: #F5F5F7;
    line-height: 1.1;
    margin: 0.1rem 0 0.35rem;
}
/* Market Internals' 3 supporting ratio tiles — deliberately more
   compact than the shared .tile padding, since they're secondary
   content next to the confidence hero and this page needs real margin
   to fit reliably across zoom levels, not just at exactly 100%. */
.internals-ratio-tile {
    padding-top: 1.1rem;
    padding-bottom: 1.1rem;
}
/* Verdict-first Internals typography — session feedback: the meaning
   has to be readable from across the room, not fine print ("super tiny
   little context bars that I cannot read unless I'm an inch away").
   The verdict word is nearly value-sized and tone-colored; the context
   line is a real sentence at readable size, replacing the old
   severity-caption small print entirely on this page. */
.internals-ratio-tile .tile-label {
    height: auto;
    font-size: 1.05rem;
}
.internals-ratio-tile .tile-value {
    font-size: 3rem;
}
.internals-verdict {
    font-size: 1.8rem;
    font-weight: 800;
    letter-spacing: 0.01em;
    line-height: 1.15;
    text-transform: uppercase;
    margin-top: 0.25rem;
}
.confidence-hero .internals-verdict {
    font-size: 2.3rem;
}
.internals-verdict-good { color: #32D74B; }
.internals-verdict-bad { color: #FF6961; }
.internals-verdict-neutral { color: #5AC8FA; }
.internals-context {
    font-size: 1.2rem;
    color: #ECECF1;
    line-height: 1.4;
    margin-top: 0.55rem;
}
.confidence-hero .internals-context {
    max-width: 46rem;
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

/* Jays/Habs scoring-play alerts (sports_alerts.py) — same bottom-strip
   takeover/intro as the bars above, own team color instead: Jays blue,
   Habs red (session request: "make it red i guess," same red the
   breaking-news bar already uses since that's genuinely the Canadiens'
   own color too). */
.sports-alert-bar-mlb, .sports-alert-bar-nhl {
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
.sports-alert-bar-mlb {
    background: linear-gradient(90deg, #0f2a7a 0%, #1a5ab3 50%, #0f2a7a 100%);
    box-shadow: 0 -4px 24px rgba(26,90,179,0.4);
}
.sports-alert-bar-nhl {
    background: linear-gradient(90deg, #7a0f10 0%, #b3181a 50%, #7a0f10 100%);
    box-shadow: 0 -4px 24px rgba(179,20,20,0.35);
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
   nothing active, so the two never appear at once. */
.weather-statement-bar {
    display: flex;
    align-items: center;
    gap: 0.9rem;
    padding: 0.5rem 1.3rem;
    margin-bottom: 0.5rem;
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
.weather-statement-watch .weather-statement-label { color: #FFB340; }
.weather-statement-watch .weather-statement-text {
    color: #FFFFFF;
    font-weight: 600;
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
    border-radius: 16px;
    background: rgba(255,255,255,0.05);
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
/* Confirmed live (same finding as the rotation-timer bar above):
   Streamlit patches this element's style attribute on the same
   persisted DOM node across reruns rather than replacing it, and once
   an animation has started OR finished on a node, mutating
   animation-delay is a no-op — it does not reposition a running
   animation, and does not restart a completed one either. With a
   single class, only the FIRST alert to ever occupy this node position
   gets the real stretch-then-slide intro; a burst of several alerts in
   a row (a real scenario — see MAX_BURST_ALERTS in app.py) has every
   alert after the first reuse the same already-completed animation
   instance and just appear instantly, with no intro at all. Fixed the
   same way: alternate between two functionally identical keyframe
   animations each time a new alert renders (see the variant argument
   threaded through news.render_alert_bar/commute_reminder.render_bar
   from app.py) — changing animation-name always forces a genuine
   restart even on the same node. */
@keyframes toast-label-intro-a {
    0%    { opacity: 0; letter-spacing: 0em; transform: translateX(0%); }
    60%   { opacity: 1; letter-spacing: 0.5em; transform: translateX(0%); }
    90.8% { opacity: 0; letter-spacing: 0.5em; transform: translateX(-107.7%); }
    100%  { opacity: 0; letter-spacing: 0.5em; transform: translateX(-140%); }
}
@keyframes toast-label-intro-b {
    0%    { opacity: 0; letter-spacing: 0em; transform: translateX(0%); }
    60%   { opacity: 1; letter-spacing: 0.5em; transform: translateX(0%); }
    90.8% { opacity: 0; letter-spacing: 0.5em; transform: translateX(-107.7%); }
    100%  { opacity: 0; letter-spacing: 0.5em; transform: translateX(-140%); }
}
@keyframes toast-headline-intro-a {
    0%    { opacity: 0; transform: translateX(16px); }
    60%   { opacity: 0; transform: translateX(16px); }
    90.8% { opacity: 1; transform: translateX(3.7px); }
    100%  { opacity: 1; transform: translateX(0px); }
}
@keyframes toast-headline-intro-b {
    0%    { opacity: 0; transform: translateX(16px); }
    60%   { opacity: 0; transform: translateX(16px); }
    90.8% { opacity: 1; transform: translateX(3.7px); }
    100%  { opacity: 1; transform: translateX(0px); }
}
.toast-label-anim-a { animation: toast-label-intro-a 3s linear forwards; }
.toast-label-anim-b { animation: toast-label-intro-b 3s linear forwards; }
.toast-headline-anim-a { animation: toast-headline-intro-a 3s linear forwards; }
.toast-headline-anim-b { animation: toast-headline-intro-b 3s linear forwards; }

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
.page-title-radar::before {
    background: #FF375F;
    box-shadow: 0 0 8px 1px rgba(255,55,95,0.5);
}
.page-title-scores::before {
    background: #30D5C8;
    box-shadow: 0 0 8px 1px rgba(48,213,200,0.5);
}
.page-title-portfolio::before {
    background: #A78BFA;
    box-shadow: 0 0 8px 1px rgba(167,139,250,0.5);
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
    color: #ABB2C4;
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
/* That game's standout performer (see scores_client._game_leader) —
   real box-score color, not just the bare score. Single line, clipped
   rather than wrapped: a long stat line ("3-4, 2 HR, 2B, 3 RBI, 2 R")
   shouldn't be able to stretch or break this grid's compact card. */
.score-card-leader {
    margin-top: 0.4rem;
    padding-top: 0.4rem;
    border-top: 1px solid rgba(255,255,255,0.06);
    font-size: 0.78rem;
    color: #ABB2C4;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.score-card-status {
    margin-top: 0.5rem;
    padding-top: 0.5rem;
    border-top: 1px solid rgba(255,255,255,0.08);
    font-size: 0.85rem;
    color: #ABB2C4;
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
    color: #ABB2C4;
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
    color: #ABB2C4;
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
    color: #ABB2C4;
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
    color: #ABB2C4;
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
    color: #ABB2C4;
}

/* Live radar tile — a real map image (Environment Canada's own WMS
   composite, see ec_radar.py), not a themed chart, so it gets a plain
   dark frame rather than the sky-gradient treatment the rest of the
   app uses, and the location marker is just CSS-positioned dead center
   since the image's bbox is always centered on the user's own point. */
.weather-radar-frame {
    position: relative;
    width: 100%;
    aspect-ratio: 1 / 1;
    max-width: 22rem;
    margin: 0 auto;
    border-radius: 12px;
    overflow: hidden;
    background: #0a1420;
}
.weather-radar-image {
    width: 100%;
    height: 100%;
    display: block;
}
/* Blue dot for "this is you", fixed at the map's own center. */
.weather-radar-marker {
    position: absolute;
    top: 50%;
    left: 50%;
    width: 10px;
    height: 10px;
    margin: -5px 0 0 -5px;
    border-radius: 50%;
    background: #64D2FF;
    box-shadow: 0 0 8px 2px rgba(100,210,255,0.7);
}

/* Real nearby towns (see config.RADAR_NEARBY_CITIES / ec_radar.
   nearby_city_markers) — plain neutral gray, deliberately much quieter
   than the blue "you" marker or the red/white storm marker, since
   these are just reference points for reading the map (where the rain
   actually is relative to real places), not something to react to. */
.weather-radar-city-marker {
    position: absolute;
    width: 5px;
    height: 5px;
    margin: -2.5px 0 0 -2.5px;
    border-radius: 50%;
    background: rgba(255,255,255,0.4);
}
.weather-radar-city-label {
    position: absolute;
    transform: translate(6px, -50%);
    font-size: 0.62rem;
    font-weight: 600;
    color: rgba(255,255,255,0.55);
    white-space: nowrap;
    pointer-events: none;
}

/* Radar page's own version — a live map is the entire point of that
   page, so it gets real screen space instead of sharing a column with
   the 7-day forecast the way it briefly did on the Weather page. Was
   capped at 28rem (too small); widening to max-width:100% alone turned
   out worse — this frame is a square (aspect-ratio 1/1), so on a wide
   screen "100% of the tile's width" also means "just as tall," which
   overran the viewport and pushed most of the map (including anything
   below the vertical center, where the location marker sits) off
   screen entirely. Confirmed live: the marker was still mathematically
   dead center (50.0%/50.0%) the whole time — the frame itself was just
   taller than what was visible. Sizing *width* itself via min(): Nvh
   (a length here, N% of viewport height) caps the width at whatever
   height allows, and aspect-ratio derives a matching height from that
   same resolved width — a real square, bounded by whichever of
   width/height is the tighter constraint. 55vh still overflowed the
   viewport in testing at both 800px and 1080px window heights — the
   hero row/badges/morning-briefing stack above this tile is close to a
   fixed pixel height regardless of viewport, so it doesn't shrink as a
   share of a taller viewport the way vh math assumes. Tuned down to
   40vh against that real content stack (measured live, page title
   through an active alert banner and the morning-briefing box) turned
   out to still overflow slightly on retest — that content stack isn't
   perfectly stable even at a fixed viewport size (badges/alerts change
   with live conditions between one test and the next — confirmed live
   that commute_reminder's page-independent "Leave in X min" headline,
   which shows above the clock on every page including this one during
   the actual pre-departure window, was what grew the stack mid-testing,
   not measurement error), so there's no single vh value that's ever
   *guaranteed* safe against every real content combination (leave
   headline + an active EC alert + every hero badge + a long
   morning-briefing sentence, all at once, is the genuine worst case)
   without JS-measuring the actual remaining space, which isn't
   practical for a static injected stylesheet. 28vh (as a square) was
   confirmed live to leave under 10px of margin above the bottom ticker
   on a 768px-tall screen (a real kiosk resolution, not a hypothetical)
   even in the calm case — no headroom at all to size up further there
   without risking real overlap. A taller screen (1024px+, the other
   real resolution in play here) has a lot more slack, so this stays
   height-tiered: unchanged height budget on short screens, meaningfully
   bigger once there's actually room for it.

   No longer square, though — was a 1:1 inset sitting in the middle of
   this tile with empty black space on either side, since the tile
   itself is much wider than the old height-bounded square ever was.
   ec_radar.py now fetches a genuinely wider image (2.5:1, more real
   horizontal coverage, not a stretched/cropped version of the old
   square one) to match, so this aspect-ratio has to track that same
   2.5 exactly or the image and the box would disagree. The vh
   multiplier below is the same height budget as before, just expressed
   as a width via the new ratio (e.g. 28vh height * 2.5 = 70vh width) —
   same technique as the square version: constrain width directly via
   min(), let aspect-ratio derive a matching height from that, rather
   than fighting a competing max-height (confirmed earlier that combo
   stretches instead of shrinking proportionally). */
.weather-radar-frame-large {
    aspect-ratio: 2.5 / 1;
    width: min(100%, 70vh);
    max-width: 100%;
}
@media (min-height: 850px) {
    .weather-radar-frame-large {
        width: min(100%, 105vh);
    }
}
.weather-radar-tile-large {
    align-items: center;
    text-align: center;
    padding-top: 1rem;
    padding-bottom: 0.9rem;
}
/* Was margin-top (the badge used to sit below the frame) — now sits
   between the label and the map, so it needs its spacing on the other
   side instead. */
.weather-radar-tile-large .badge {
    margin-bottom: 0.7rem;
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
    /* Slow breathing glow, not a strobe — this only shows up in a
       genuinely time-critical window (see commute_reminder.
       render_leave_headline), so it earns pulling more attention than
       the market tiles' static accent strip does, without reading as
       cheap/busy the way a fast blink would. */
    animation: leave-headline-pulse 2s ease-in-out infinite;
}
@keyframes leave-headline-pulse {
    0%, 100% { text-shadow: 0 0 22px rgba(255,69,58,0.45); }
    50% { text-shadow: 0 0 36px rgba(255,69,58,0.85), 0 0 60px rgba(255,69,58,0.35); }
}

/* Same page-independent headline treatment for the final hour before a
   Jays/Habs game (sports_alerts.render_game_countdown) — deliberately
   smaller and calmer than the leave headline (no pulse): a game
   starting is anticipation, not a deadline, and if both ever render at
   once the commute one must clearly be the urgent one. Team-colored,
   matching each team's own alert bar (see .sports-alert-bar-*). */
.game-countdown-headline {
    text-align: center;
    font-size: 1.9rem;
    font-weight: 800;
    letter-spacing: -0.01em;
    margin: 0 0 0.6rem;
}
.game-countdown-mlb {
    color: #4AA8FF;
    text-shadow: 0 0 22px rgba(74,168,255,0.4);
}
.game-countdown-nhl {
    color: #FF5A5F;
    text-shadow: 0 0 22px rgba(255,90,95,0.4);
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
    color: #ABB2C4 !important;
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
.mobile-nav-item-radar { color: #FF375F !important; }
.mobile-nav-item-sports { color: #5E5CE6 !important; }
.mobile-nav-item-scores { color: #30D5C8 !important; }
.mobile-nav-item-portfolio { color: #A78BFA !important; }

/* ============ JUMBOTRON (pages_jumbotron.py) ============
   A self-contained arena-scoreboard skin that only ever renders while
   sports_alerts.takeover_state() has the screen (T-60min through ~15min
   past final). Every rule here is namespaced .jumbo* so none of it can
   leak into the normal kiosk pages, which keep the Apple-glass look.
   LED amber on near-black, glass bento panels, Bebas Neue numerals. */
.jumbo {
    --led: #FFB300;
    --ledglow: rgba(255,179,0,0.5);
    --arena: #05070C;
    --glass: rgba(16,22,32,0.66);
    --edge: #1E2634;
    --edge-hi: #2E3B54;
    --bone: #F4F1E8;
    /* Session feedback: "a lot of it is just gray... let's remove that
       muted gray to a more visible color overall" — brightened both
       secondary-text tones (records, start times, probables labels,
       standings, captions — everywhere in the jumbotron that reads off
       these two custom properties picks this up automatically, no
       per-element changes needed). Kept two distinct tones rather than
       one flat color so there's still a readable hierarchy between
       "secondary" (--mut) and "tertiary" (--mut-2) text, just both
       shifted much lighter than the original near-invisible grays. */
    --mut: #C2CAD8;
    --mut-2: #9BA6BA;
    --live: #FF453A;
    --ok: #32D583;
    --disp: 'Oswald', 'Arial Narrow', sans-serif;
    --num: 'Bebas Neue', 'Oswald', Impact, sans-serif;
    --mono: 'JetBrains Mono', ui-monospace, Consolas, monospace;
    font-family: var(--disp);
    color: var(--bone);
    display: flex;
    flex-direction: column;
    /* Fills the viewport minus the kiosk's own top padding and the
       fixed ticker strip at the bottom — this page owns the whole
       screen, unlike the normal pages that stack under the hero row. */
    height: calc(100vh - 7rem);
    min-height: 0;
    gap: 10px;
}
/* The normal kiosk caps content at 1450px and centers it vertically —
   right for tiles, wrong for a full-bleed scoreboard. Scoped via :has()
   so it only applies on the takeover page; if a browser ever lacks
   :has() support the jumbotron simply renders at the normal width
   instead of breaking. */
.block-container:has(.jumbo) {
    max-width: 100% !important;
    padding-top: 0.4rem !important;
    padding-left: 1.1rem !important;
    padding-right: 1.1rem !important;
    justify-content: flex-start !important;
}
/* Confirmed live: with justify-content pinned to flex-start above, the
   ~1.5-2 inch gap above the marquee was Streamlit's own per-element
   vertical gap (repeated across several invisible 0-height markdown/
   iframe containers that render ahead of the page body — the hotkey
   listener, the sky/scenery markdown, staleness pills, etc.) plus the
   autorefresh component's own 26px iframe height. None of that is
   visible on the normal pages because centered layout just swallows it
   as part of the whole block being centered — flex-start is what makes
   it show up as a hard gap instead. Collapsed only while the jumbotron
   is showing, since the normal pages still want that centering intact. */
.block-container:has(.jumbo) > div {
    gap: 0 !important;
}
.block-container:has(.jumbo) .element-container:has(iframe) {
    height: 0 !important;
    min-height: 0 !important;
    overflow: hidden !important;
}

.jumbo-marquee {
    display: flex;
    align-items: center;
    gap: 18px;
    padding: 8px 16px;
    flex: 0 0 auto;
    background: linear-gradient(180deg, rgba(14,19,28,0.94), rgba(8,11,16,0.94));
    border: 1px solid var(--edge);
    border-radius: 12px;
    position: relative;
}
/* Jays blue on the left half, Habs red on the right — the arena's own
   two-team identity, stated once at the top instead of repeated. */
.jumbo-marquee::after {
    content: "";
    position: absolute;
    left: 0; right: 0; bottom: -1px;
    height: 2px;
    background: linear-gradient(90deg, #3E7CC9 0 50%, #D8323F 50% 100%);
    opacity: 0.85;
    border-radius: 0 0 12px 12px;
}
.jumbo-brand {
    font-family: var(--num);
    font-size: 30px;
    letter-spacing: 0.12em;
    color: var(--led);
    text-shadow: 0 0 16px var(--ledglow);
    line-height: 0.92;
}
.jumbo-brand span {
    display: block;
    color: var(--mut);
    font-family: var(--disp);
    font-weight: 300;
    letter-spacing: 0.4em;
    font-size: 9px;
}
.jumbo-clock {
    font-family: var(--num);
    font-size: 36px;
    letter-spacing: 0.05em;
    line-height: 1;
}
.jumbo-clock em { font-style: normal; font-size: 16px; color: var(--mut); margin-left: 5px; }
.jumbo-dateline {
    font-size: 11px;
    font-weight: 300;
    color: var(--mut);
    letter-spacing: 0.2em;
}
.jumbo-spacer { flex: 1; }
.jumbo-wx {
    display: flex;
    align-items: baseline;
    gap: 9px;
    border: 1px solid var(--edge);
    border-radius: 10px;
    padding: 5px 14px;
    background: var(--glass);
}
.jumbo-wx-temp { font-family: var(--num); font-size: 26px; line-height: 1; }
.jumbo-wx-loc { font-size: 9px; font-weight: 300; color: var(--mut); letter-spacing: 0.24em; }

.jumbo-grid {
    flex: 1;
    display: grid;
    grid-template-columns: 420px 1fr 340px;
    gap: 12px;
    min-height: 0;
}
.jumbo-panel {
    border: 1px solid var(--edge);
    border-radius: 14px;
    background: var(--glass);
    box-shadow: 0 10px 32px rgba(0,0,0,0.4);
    display: flex;
    flex-direction: column;
    min-height: 0;
    overflow: hidden;
}
.jumbo-ph {
    flex: 0 0 auto;
    display: flex;
    align-items: center;
    padding: 12px 18px;
    border-bottom: 1px solid var(--edge);
    font-family: var(--mono);
    font-size: 13px;
    letter-spacing: 0.32em;
    color: var(--led);
    text-transform: uppercase;
}
.jumbo-ph-right { margin-left: auto; letter-spacing: 0.12em; color: var(--mut-2); }
.jumbo-live { color: var(--live); font-weight: 800; animation: jumbo-blink 1.4s infinite; }
@keyframes jumbo-blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.25; } }

/* ---- My Teams rail ---- */
.jumbo-rail-body { flex: 1; min-height: 0; overflow: hidden; }
.jumbo-hero {
    padding: 20px 20px 22px;
    border-bottom: 1px solid rgba(30,38,52,0.55);
    position: relative;
}
.jumbo-hero:last-child { border-bottom: none; }
.jumbo-hero::before {
    content: "";
    position: absolute;
    left: 0; top: 10%; bottom: 10%;
    width: 4px;
    border-radius: 2px;
    background: var(--tc, var(--edge-hi));
}
.jumbo-hero-nhl { --tc: #D8323F; }
.jumbo-hero-mlb { --tc: #3E7CC9; }
.jumbo-hero-head { display: flex; align-items: center; gap: 14px; }
.jumbo-hero-head img { width: 58px; height: 58px; object-fit: contain; flex: 0 0 auto; }
.jumbo-hero-id { min-width: 0; white-space: nowrap; }
.jumbo-hero-name { font-weight: 600; font-size: 24px; letter-spacing: 0.02em; line-height: 1.1; white-space: nowrap; }
.jumbo-hero-div {
    font-size: 13px;
    font-weight: 300;
    color: var(--mut);
    letter-spacing: 0.14em;
    text-transform: uppercase;
    margin-top: 4px;
}
.jumbo-hero-rec { margin-left: auto; text-align: right; flex: 0 0 auto; padding-left: 10px; }
.jumbo-hero-rec-v { font-family: var(--num); font-size: 30px; line-height: 1; white-space: nowrap; }
.jumbo-hero-rec-l { font-size: 10px; font-weight: 300; color: var(--mut-2); letter-spacing: 0.3em; white-space: nowrap; }
.jumbo-form { display: flex; gap: 7px; align-items: center; margin-top: 13px; }
.jumbo-form-label { font-size: 12px; font-weight: 300; color: var(--mut-2); letter-spacing: 0.24em; margin-right: 3px; }
.jumbo-form i { width: 13px; height: 13px; border-radius: 50%; display: inline-block; }
.jumbo-form-w { background: var(--ok); box-shadow: 0 0 6px rgba(50,213,131,0.5); }
.jumbo-form-l { background: rgba(255,69,58,0.35); border: 1px solid rgba(255,69,58,0.5); }
.jumbo-gameline {
    margin-top: 14px;
    border: 1px solid var(--edge);
    border-radius: 10px;
    background: rgba(8,11,17,0.7);
    padding: 12px 15px;
    font-family: var(--mono);
    font-size: 16px;
    color: var(--mut);
    line-height: 1.7;
}
.jumbo-gameline b { color: var(--bone); font-weight: 600; }
.jumbo-gl-score { color: var(--led); font-weight: 800; font-size: 19px; }
.jumbo-gl-cd { font-family: var(--num); color: var(--bone); font-size: 24px; letter-spacing: 0.08em; margin-left: 10px; }
.jumbo-w { color: var(--ok); }
.jumbo-l { color: var(--live); }
.jumbo-offseason { border-style: dashed; color: var(--mut-2); letter-spacing: 0.28em; font-size: 13px; }
.jumbo-hero-live .jumbo-gameline { border-color: rgba(255,69,58,0.45); box-shadow: 0 0 16px rgba(255,69,58,0.1); }
.jumbo-livechip {
    position: absolute;
    top: 18px; right: 20px;
    font-family: var(--mono);
    font-size: 11px;
    font-weight: 800;
    color: var(--live);
    letter-spacing: 0.26em;
    animation: jumbo-blink 1.4s infinite;
}
/* My Teams + Division Standings share the left column as two stacked
   panels — session request moved standings out of each hero card into
   its own rotating panel at the bottom. My Teams sizes to its own
   content (1-2 compact hero cards); standings takes whatever's left. */
.jumbo-rail-col { display: flex; flex-direction: column; gap: 12px; min-height: 0; }
.jumbo-rail-col .jumbo-rail { flex: 0 0 auto; }
.jumbo-rail-col .jumbo-standings-panel { flex: 1; min-height: 0; }

/* Division standings panel (pages_jumbotron._rotating_standings_html)
   — session request: real team logos per row, and its own dedicated
   (now rotating, ~20s per league) panel instead of a cramped snippet
   inside each hero card — same data/shape as pages_sports.py's own
   _standings_table, restyled for the jumbotron's LED-mono look. */
.jumbo-standings-body { flex: 1; min-height: 0; padding: 4px 18px 14px; overflow: hidden; }
.jumbo-standings {
    border: 1px solid var(--edge);
    border-radius: 9px;
    background: rgba(8,11,17,0.7);
    overflow: hidden;
    font-family: var(--mono);
    font-size: 14px;
}
.jumbo-standings-row {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 9px 14px;
    border-bottom: 1px solid rgba(30,38,52,0.5);
    color: var(--mut);
}
.jumbo-standings-row:last-child { border-bottom: none; }
.jumbo-standings-row-team { color: var(--bone); background: rgba(255,179,0,0.07); font-weight: 700; }
.jumbo-standings-rank { flex: 0 0 18px; color: var(--mut-2); }
.jumbo-standings-logo { width: 22px; height: 22px; object-fit: contain; flex: 0 0 auto; }
.jumbo-standings-team { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.jumbo-standings-record { flex: 0 0 auto; }
.jumbo-standings-extra { flex: 0 0 40px; text-align: right; color: var(--mut-2); }

/* ---- Featured board ---- */
.jumbo-board { position: relative; }
.jumbo-board-live {
    border-color: rgba(255,69,58,0.5);
    animation: jumbo-boardpulse 2.6s ease-in-out infinite;
}
@keyframes jumbo-boardpulse {
    0%, 100% { box-shadow: 0 10px 32px rgba(0,0,0,0.4), 0 0 0 rgba(255,69,58,0); }
    50% { box-shadow: 0 10px 32px rgba(0,0,0,0.4), 0 0 26px rgba(255,69,58,0.22); }
}
/* Win celebration (pages_jumbotron._board_html) — session request:
   "the j's win." One-shot gold burst around the whole board the
   moment a win is first observed (session-guarded per game_id so it
   never replays during the ~15min postgame hold — see the Python
   side), instead of the live board's own continuous pulse. */
.jumbo-win-burst {
    animation: jumbo-win-burst 1.8s cubic-bezier(.2,.8,.2,1);
}
@keyframes jumbo-win-burst {
    0% { box-shadow: 0 10px 32px rgba(0,0,0,0.4), 0 0 0 rgba(255,179,0,0); border-color: var(--edge); }
    30% { box-shadow: 0 10px 32px rgba(0,0,0,0.4), 0 0 70px rgba(255,179,0,0.65); border-color: var(--led); }
    100% { box-shadow: 0 10px 32px rgba(0,0,0,0.4), 0 0 0 rgba(255,179,0,0); border-color: var(--edge); }
}
/* Centers the board's contents in whatever height is left over. A
   pregame board is just a matchup and a countdown, a live one adds a
   linescore and scoring summary — without this the sparse version
   clings to the top of a very tall panel with a void beneath it. */
.jumbo-board-body {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
    justify-content: center;
    overflow: hidden;
}
.jumbo-matchup {
    display: grid;
    grid-template-columns: 1fr auto 1fr;
    align-items: center;
    gap: 8px;
    padding: 18px 26px 6px;
}
.jumbo-side { display: flex; flex-direction: column; align-items: center; gap: 5px; text-align: center; }
.jumbo-side-dim { opacity: 0.55; }
.jumbo-logobox { width: 132px; height: 132px; display: flex; align-items: center; justify-content: center; }
.jumbo-logobox img {
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
    filter: drop-shadow(0 5px 18px rgba(0,0,0,0.75));
}
.jumbo-tname { font-weight: 600; font-size: 26px; letter-spacing: 0.05em; }
.jumbo-trec { font-size: 13px; font-weight: 300; color: var(--mut); letter-spacing: 0.14em; }
.jumbo-center { display: flex; flex-direction: column; align-items: center; gap: 4px; }
.jumbo-score { display: flex; align-items: center; gap: 12px; }
.jumbo-digitbox { display: flex; gap: 6px; }
/* Plain numerals, not the amber LED-panel look this used to have —
   session feedback: "why are the scoreboard numbers like a yellow
   emoji? I don't really fuck with that. Can we just make it regular
   numbers." */
.jumbo-digit {
    font-family: var(--num);
    font-size: 104px;
    line-height: 0.92;
    width: 0.62em;
    text-align: center;
    color: var(--bone);
    font-weight: 700;
}
/* Score-change flash (pages_jumbotron._board_html) — session request:
   "are there animations for when the j score" (the original static
   mockup's full-screen confetti blast on a score, which was dropped as
   too fragile against Streamlit's rerun model — see sports_alerts.py's
   module docstring). This is the same idea kept server-rendered-safe:
   one box-scale-and-glow pulse the instant a score changes, gold for
   our own side, a dimmer neutral pulse for the opponent's — applied
   only for the single rerun right after the change (Python side), so
   it can't get stuck replaying every 5s tick. */
.jumbo-digitbox-flash-us .jumbo-digit {
    animation: jumbo-score-flash-us 1.1s ease-out;
}
.jumbo-digitbox-flash-opp .jumbo-digit {
    animation: jumbo-score-flash-opp 1.1s ease-out;
}
@keyframes jumbo-score-flash-us {
    0% { transform: scale(1.35); text-shadow: 0 0 30px rgba(255,255,255,0.85); }
    100% { transform: scale(1); text-shadow: none; }
}
@keyframes jumbo-score-flash-opp {
    0% { transform: scale(1.12); text-shadow: 0 0 20px rgba(255,255,255,0.5); }
    100% { transform: scale(1); text-shadow: none; }
}
.jumbo-dash { color: var(--edge-hi); font-family: var(--num); font-size: 50px; }
.jumbo-vs { font-family: var(--num); font-size: 26px; letter-spacing: 0.4em; color: var(--mut-2); padding-left: 0.4em; }
.jumbo-countdown { font-family: var(--num); font-size: 96px; color: var(--bone); letter-spacing: 0.06em; line-height: 1; }
.jumbo-cd-label { font-size: 10px; font-weight: 300; color: var(--mut-2); letter-spacing: 0.4em; }
.jumbo-final-badge {
    font-family: var(--num);
    font-size: 16px;
    letter-spacing: 0.4em;
    color: #0A0D12;
    background: var(--led);
    padding: 4px 14px 3px 18px;
    border-radius: 6px;
    margin-top: 8px;
    box-shadow: 0 0 18px rgba(255,179,0,0.4);
}
/* Session feedback: "make the inning, bases, count, and outs more
   visible from across the room" — sized up across the board (the
   inning-by-inning linescore this used to sit above was dropped in
   the same request, freeing up real room to grow into). */
.jumbo-situ {
    text-align: center;
    font-family: var(--mono);
    font-size: 24px;
    letter-spacing: 0.05em;
    padding: 10px 26px 14px;
    line-height: 1.7;
}
.jumbo-situ-hot { color: var(--led); font-weight: 700; margin-right: 16px; font-size: 28px; }
.jumbo-dim { color: var(--mut-2); }
.jumbo-clockbig { font-family: var(--num); font-size: 30px; color: var(--bone); letter-spacing: 0.06em; }
/* Pregame venue/weather + probable starters (pages_jumbotron.
   _pregame_extra_html) — session request, all free data off the same
   feed already used for scoring plays. */
.jumbo-pregame-venue {
    text-align: center;
    font-family: var(--mono);
    font-size: 13px;
    color: var(--mut);
    letter-spacing: 0.03em;
    padding: 2px 26px 4px;
}
.jumbo-probables {
    display: flex;
    justify-content: center;
    gap: 40px;
    padding: 6px 0 10px;
    font-family: var(--mono);
    font-size: 13px;
}
.jumbo-probables b { color: var(--bone); font-weight: 700; font-size: 15px; }
.jumbo-probables-label {
    font-size: 9px;
    letter-spacing: 0.26em;
    color: var(--mut-2);
    display: block;
    margin-bottom: 3px;
    font-weight: 600;
}
/* Win probability bar (pages_jumbotron._win_probability_html) —
   session request, from ESPN's own live model (see
   scores_client.win_probability's own docstring for why the native
   MLB/NHL feeds this board otherwise runs on can't provide this). */
/* Session feedback: "find a better way to show the win odds since its
   hard to see" — was a thin 11px bar with 11px-print percentages
   underneath. Now the percentages are the headline, big and bold,
   flanking a bar thick enough to actually read the split at a glance. */
.jumbo-wp { padding: 12px 36px 8px; }
.jumbo-wp-title {
    text-align: center;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.4em;
    color: var(--mut-2);
    margin-bottom: 10px;
}
.jumbo-wp-row { display: flex; align-items: center; gap: 16px; }
.jumbo-wp-pct {
    font-family: var(--mono);
    font-size: 34px;
    font-weight: 700;
    flex: 0 0 auto;
    min-width: 78px;
}
.jumbo-wp-row .jumbo-wp-pct:first-child { text-align: right; }
.jumbo-wp-bar {
    flex: 1;
    height: 30px;
    border-radius: 8px;
    overflow: hidden;
    display: flex;
    border: 1px solid var(--edge);
}
.jumbo-wp-seg { transition: width 1s ease; }
.jumbo-wp-labels {
    display: flex;
    justify-content: space-between;
    font-family: var(--mono);
    font-size: 14px;
    font-weight: 700;
    color: var(--bone);
    margin-top: 8px;
    letter-spacing: 0.03em;
}
/* Top Performers — single big rotating card with a real headshot
   (pages_jumbotron._top_performers_html) — session request: "make top
   performers bigger or put them in a single slot that rotates
   continuously." Replaced the earlier shared-width grid entirely
   (cramming 6-8 categories into one row left each card too small to
   actually read at a glance) — one stat at a time, large, cycling
   every 5s. */
.jumbo-leaders { border-top: 1px solid var(--edge); padding: 12px 26px 16px; }
.jumbo-leader-big {
    display: flex;
    align-items: center;
    gap: 22px;
    background: rgba(8,11,17,0.65);
    border: 1px solid var(--edge);
    border-radius: 14px;
    padding: 16px 26px;
}
.jumbo-leader-big-hshot {
    width: 84px; height: 84px;
    border-radius: 50%;
    object-fit: cover;
    object-position: top;
    background: #141A25;
    border: 2px solid var(--led);
    flex: 0 0 auto;
}
.jumbo-leader-big-col { min-width: 0; }
.jumbo-leader-big-stat {
    font-family: var(--num);
    font-size: 52px;
    line-height: 1;
    color: var(--bone);
    letter-spacing: 0.03em;
    white-space: nowrap;
}
.jumbo-leader-big-cat {
    font-family: var(--mono);
    font-size: 13px;
    letter-spacing: 0.2em;
    color: var(--led);
    text-transform: uppercase;
    margin-top: 6px;
    font-weight: 700;
}
.jumbo-leader-big-who {
    font-size: 16px;
    font-weight: 400;
    color: var(--bone);
    margin-top: 4px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
/* Full-roster list filling the rest of the card — session feedback:
   "put the names in the big empty slot... kind of a waste of space
   having it all empty." The currently-featured leader (highlighted)
   still gets the big photo/stat treatment on the left; this is
   everyone else, so the card reads as "here's the whole leaderboard,
   spotlighting one" rather than one stat floating in a mostly-blank
   card between rotations. */
.jumbo-leader-namelist {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding-left: 24px;
    margin-left: 4px;
    border-left: 1px solid var(--edge);
    font-family: var(--mono);
    font-size: 13px;
}
.jumbo-leader-name-item {
    display: flex;
    justify-content: space-between;
    gap: 14px;
    padding: 5px 0;
    color: var(--mut);
}
.jumbo-leader-name-who { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.jumbo-leader-name-stat { flex: 0 0 auto; color: var(--mut-2); }
.jumbo-leader-name-active {
    color: var(--bone);
    font-weight: 700;
}
.jumbo-leader-name-active .jumbo-leader-name-stat { color: var(--led); font-weight: 700; }
/* Current batter/pitcher, live-game replacement for the Top Performers
   card — session request: "during the game can you make the top
   performers tab show current pitcher and batter and their stats use
   OPS for batter and ERA for pitchers." Photo-up-top, stat-below-name
   layout — session request: "add the pitcher and batter pics and put
   the stats below them like youd see on a jumbotron in the ballpark."
   Sized up further, and the stat split into a big number plus a small
   caption underneath (same pattern as the Top Performers big card's
   own jumbo-leader-big-stat/-cat) rather than one "4.31 ERA" string —
   session feedback: "make the ops and era less clunky and easier to
   read from across the room... the whole matchup thing needs to be
   easier to read." */
.jumbo-live-matchup { display: flex; align-items: center; justify-content: center; gap: 32px; padding: 4px 4px 6px; }
.jumbo-live-matchup-col { display: flex; flex-direction: column; align-items: center; text-align: center; gap: 3px; flex: 1; min-width: 0; }
.jumbo-live-matchup-photo {
    width: 104px;
    height: 104px;
    border-radius: 50%;
    object-fit: cover;
    object-position: top;
    background: #141A25;
    border: 3px solid var(--led);
    margin-bottom: 6px;
}
.jumbo-live-matchup-tag {
    font-family: var(--mono);
    font-size: 13px;
    letter-spacing: 0.18em;
    color: var(--led);
    font-weight: 700;
    text-transform: uppercase;
}
.jumbo-live-matchup-name {
    /* Same fix as jumbo-live-matchup-stat below — this was silently
       inheriting var(--disp) (Oswald, condensed) at a forced 700, same
       swollen/blobby look. Session feedback: "can we make their name
       skinnier as well please i wanna be able to read that too." */
    font-family: var(--mono);
    font-size: 21px;
    font-weight: 600;
    color: var(--bone);
    max-width: 100%;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
/* Session request: "for pitchers add number of pitches below ERA and
   then just do average for batter" — a pitcher now carries two stat
   blocks (ERA, pitch count) side by side, a batter just the one (AVG);
   this row wraps however many _current_matchup_html's own col() built. */
.jumbo-live-matchup-stat-row { display: flex; gap: 26px; margin-top: 4px; }
.jumbo-live-matchup-stat-block { display: flex; flex-direction: column; align-items: center; }
.jumbo-live-matchup-stat {
    /* Session feedback: "the font is still so clunky that it just looks
       like a blob. pick a skinnier font." var(--num) is Bebas Neue — a
       squat display font with no real bold weight of its own, so
       font-weight:700 on it was faking a bold and coming out swollen at
       this size. JetBrains Mono actually has real weight steps and
       tabular figures, reads far slimmer for a stat number like this. */
    font-family: var(--mono);
    font-size: 32px;
    font-weight: 600;
    color: var(--bone);
    line-height: 1.1;
}
.jumbo-live-matchup-stat-label {
    font-family: var(--mono);
    font-size: 12px;
    letter-spacing: 0.2em;
    color: var(--led);
    font-weight: 700;
    text-transform: uppercase;
}
.jumbo-live-matchup-vs {
    font-family: var(--mono);
    font-size: 16px;
    font-weight: 700;
    color: var(--mut-2);
    letter-spacing: 0.1em;
    flex: 0 0 auto;
}
.jumbo-diamond { width: 62px; height: 62px; display: inline-block; vertical-align: -18px; margin: 0 18px; }
.jumbo-diamond rect { fill: #1A2230; stroke: var(--edge-hi); stroke-width: 1.5; }
.jumbo-diamond rect.on { fill: var(--led); stroke: var(--led); }
/* Session request: "make counts and outs actual numbers instead of
   dots" — replaces the old ball/strike/out dot rows. */
.jumbo-situ-count, .jumbo-situ-outs {
    display: inline-block;
    font-weight: 700;
    color: var(--bone);
}
.jumbo-situ-count { margin-left: 14px; }
.jumbo-situ-outs { margin-left: 22px; }
/* Session request (carried over from the old dots): "are there
   animations for... there's a strikeout" — the count/outs number
   pulses the instant it climbs instead of just silently updating
   (pages_jumbotron._mlb_situation_html decides when that's genuine). */
.jumbo-situ-pulse { animation: jumbo-situ-pulse 0.6s ease-out; display: inline-block; }
@keyframes jumbo-situ-pulse {
    0% { transform: scale(1.35); text-shadow: 0 0 16px var(--led); }
    100% { transform: scale(1); text-shadow: none; }
}

.jumbo-sl {
    font-family: var(--mono);
    font-size: 8.5px;
    letter-spacing: 0.32em;
    color: var(--led);
    text-transform: uppercase;
    margin-bottom: 7px;
}

/* ---- Around the leagues ---- */
.jumbo-around-body { flex: 1; min-height: 0; overflow: hidden; }
.jumbo-around-league {
    font-family: var(--mono);
    font-size: 12px;
    letter-spacing: 0.32em;
    color: var(--led);
    padding: 13px 18px 6px;
}
.jumbo-mini {
    display: flex;
    align-items: center;
    padding: 10px 18px;
    gap: 14px;
    border-bottom: 1px solid rgba(30,38,52,0.4);
}
.jumbo-mini-final { opacity: 0.42; }
.jumbo-mini-live { background: rgba(255,69,58,0.05); border-left: 3px solid var(--live); }
.jumbo-mini-teams { flex: 1; display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.jumbo-mini-team { display: flex; align-items: center; gap: 10px; }
.jumbo-mini-team img { width: 28px; height: 28px; object-fit: contain; flex: 0 0 auto; }
.jumbo-mini-abbr { font-size: 17px; font-weight: 500; color: var(--mut); letter-spacing: 0.08em; }
.jumbo-mini-record { font-size: 11px; font-weight: 300; color: var(--mut-2); letter-spacing: 0.05em; }
.jumbo-mini-score { margin-left: auto; font-family: var(--num); font-size: 26px; line-height: 1; color: var(--bone); }
/* Session request: bring back the standout-performer line (see
   scores_client._game_leader) that used to show on the regular
   rotation's own Scores page. */
.jumbo-mini-leader {
    font-family: var(--mono);
    font-size: 11px;
    color: var(--led);
    letter-spacing: 0.02em;
    margin-top: 3px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
.jumbo-mini-leader-stat { color: var(--bone); font-weight: 700; }
.jumbo-mini-status {
    font-family: var(--mono);
    font-size: 12px;
    color: var(--mut-2);
    letter-spacing: 0.1em;
    text-transform: uppercase;
    text-align: right;
    flex: 0 0 auto;
    line-height: 1.6;
}
.jumbo-mini-live .jumbo-mini-status { color: var(--live); font-weight: 800; }

/* Page-flip crossfade (pages_jumbotron._around_html) — session
   request: "add a cool animation to make it less robotic." Two
   identically-defined classes rather than one, alternated on each
   genuine page change: Streamlit patches this markdown block in place
   across reruns, and re-applying a class that's already finished
   animating is a no-op, the same reason news.py's toast bars alternate
   between two keyframe classes (see its own comment). Only applied for
   the one rerun immediately after a real change (see the Python side),
   so a page sitting still for 12s never re-triggers this every 5s tick. */
.jumbo-around-fade-a, .jumbo-around-fade-b {
    animation: jumbo-around-fade-in 0.5s cubic-bezier(.2,.8,.2,1) backwards;
}
@keyframes jumbo-around-fade-in {
    from { opacity: 0; transform: translateY(10px); }
    to { opacity: 1; transform: translateY(0); }
}

/* Takeover transition curtain (app.py) — session feedback: the hard
   cut between the everyday dashboard and the jumbotron "feels
   dystopian," worth a real transition each way. A fixed full-screen
   layer that holds briefly then fades itself out via CSS alone (no JS,
   no second Streamlit rerun needed) — the real destination page is
   already rendering underneath it in the same script run, this just
   reveals it a couple seconds later instead of cutting instantly.
   pointer-events:none from the very first frame so it can never trap
   a touch/click even before the fade finishes. */
.jumbo-transition {
    position: fixed;
    inset: 0;
    z-index: 9999;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 14px;
    pointer-events: none;
    animation: jumbo-transition-hold-fade 2.4s cubic-bezier(.4,0,.2,1) forwards;
}
@keyframes jumbo-transition-hold-fade {
    0% { opacity: 1; }
    62% { opacity: 1; }
    100% { opacity: 0; visibility: hidden; }
}
/* Entering the jumbotron — same LED-amber arena identity as the board
   itself (Bebas Neue is already loaded globally, see the @import at
   the top of this file, so no extra font request here). */
.jumbo-transition-in { background: #05070C; }
.jumbo-transition-brand {
    font-family: 'Bebas Neue', 'Oswald', Impact, sans-serif;
    font-size: 72px;
    letter-spacing: 0.12em;
    color: #FFB300;
    text-shadow: 0 0 30px rgba(255,179,0,0.6), 0 0 4px rgba(255,179,0,0.9);
    line-height: 0.9;
    text-align: center;
    animation: jumbo-transition-flicker 1.4s ease-out;
}
.jumbo-transition-brand span {
    display: block;
    font-family: 'Oswald', sans-serif;
    font-weight: 300;
    letter-spacing: 0.5em;
    font-size: 16px;
    color: #7E8898;
    margin-top: 8px;
}
/* Same flicker-on beat the original static mockup's own boot splash
   used for its logo — a dead-flat fade-in read as too clinical for
   what's meant to feel like a stadium scoreboard powering up. */
@keyframes jumbo-transition-flicker {
    0% { opacity: 0; }
    8% { opacity: 1; }
    12% { opacity: 0.2; }
    18% { opacity: 1; }
    24% { opacity: 0.4; }
    32% { opacity: 1; }
    100% { opacity: 1; }
}
.jumbo-transition-sub {
    font-family: 'JetBrains Mono', ui-monospace, Consolas, monospace;
    font-size: 14px;
    letter-spacing: 0.32em;
    color: #FFB300;
    text-transform: uppercase;
    opacity: 0;
    animation: jumbo-transition-sub-in 0.6s ease-out 1s forwards;
}
@keyframes jumbo-transition-sub-in {
    from { opacity: 0; transform: translateY(6px); }
    to { opacity: 1; transform: translateY(0); }
}
/* Leaving the jumbotron — back to the normal kiosk's own Apple-glass
   identity (SF Pro stack), deliberately calmer than the arena look:
   this is a return to "everyday," not another spectacle. */
.jumbo-transition-out { background: rgba(5,7,12,0.97); }
.jumbo-transition-brand-normal {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Helvetica Neue", sans-serif;
    font-size: 40px;
    font-weight: 700;
    letter-spacing: -0.01em;
    color: #F5F5F7;
    animation: jumbo-transition-sub-in 0.8s ease-out;
}
.jumbo-transition-sub-normal {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", sans-serif;
    font-size: 15px;
    color: #8E8E93;
    opacity: 0;
    animation: jumbo-transition-sub-in 0.6s ease-out 0.5s forwards;
}

/* Full-screen "new pitcher" intro — session request: "can we create a
   full screen toast for when a new pitcher comes in that shows their
   full profile and season stats." Same fixed-full-viewport approach as
   .jumbo-transition above, but held far longer (see
   pages_jumbotron._PITCHER_OVERLAY_HOLD_SECONDS) since this has to
   actually be read — driven by animation-delay set from real elapsed
   time (same technique sports_alerts.render_alert_bar's own toast bars
   use), not a delay that resets every Streamlit rerun. */
.jumbo-pitcher-overlay {
    position: fixed;
    inset: 0;
    z-index: 9998;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 10px;
    background: rgba(5,7,12,0.97);
    pointer-events: none;
    animation: jumbo-pitcher-overlay-fade 8.6s cubic-bezier(.4,0,.2,1) forwards;
}
@keyframes jumbo-pitcher-overlay-fade {
    0% { opacity: 0; }
    5% { opacity: 1; }
    88% { opacity: 1; }
    100% { opacity: 0; visibility: hidden; }
}
.jumbo-pitcher-overlay-inner { display: flex; flex-direction: column; align-items: center; gap: 10px; }
.jumbo-pitcher-overlay-label {
    font-family: var(--mono);
    font-size: 16px;
    letter-spacing: 0.28em;
    color: var(--led);
    text-transform: uppercase;
    font-weight: 700;
    margin-bottom: 6px;
}
.jumbo-pitcher-overlay-photo {
    width: 200px;
    height: 200px;
    border-radius: 50%;
    object-fit: cover;
    object-position: top;
    background: #141A25;
    border: 4px solid var(--led);
    box-shadow: 0 0 60px rgba(255,179,0,0.25);
    margin-bottom: 8px;
}
.jumbo-pitcher-overlay-name {
    font-family: var(--mono);
    font-size: 52px;
    font-weight: 600;
    color: var(--bone);
    text-align: center;
}
.jumbo-pitcher-overlay-bio {
    font-family: var(--mono);
    font-size: 16px;
    color: var(--mut);
    letter-spacing: 0.04em;
    text-align: center;
    margin-bottom: 18px;
}
.jumbo-pitcher-overlay-stats { display: flex; align-items: flex-start; justify-content: center; gap: 44px; }
.jumbo-pitcher-overlay-stat { display: flex; flex-direction: column; align-items: center; gap: 4px; }
.jumbo-pitcher-overlay-stat-v { font-family: var(--mono); font-size: 34px; font-weight: 600; color: var(--bone); }
.jumbo-pitcher-overlay-stat-l {
    font-family: var(--mono);
    font-size: 12px;
    letter-spacing: 0.2em;
    color: var(--led);
    text-transform: uppercase;
    font-weight: 700;
}

/* Full-screen "out of town scoreboard" during a natural break in the
   featured game — session request: "between innings / periods can we
   go to a full screen out of town scoreboard. with a timer till the
   game resumes again." Same fixed-full-viewport approach as
   .jumbo-pitcher-overlay above, one z-index lower so a new-pitcher
   overlay firing right at a break still plays on top first. Reuses
   the sidebar Around The Leagues panel's own .jumbo-mini row markup
   (pages_jumbotron._mini_row_html) inside a bigger grid rather than a
   separate template — .jumbo-otc-grid-scoped overrides below just
   size those same rows up for a full-screen read. No animation-hold
   timing here (unlike the pitcher overlay): this is driven by real
   game state, up for exactly as long as the break itself lasts. */
.jumbo-otc-overlay {
    position: fixed;
    inset: 0;
    z-index: 9997;
    display: flex;
    justify-content: center;
    background: rgba(5,7,12,0.98);
    padding: 44px 60px;
    overflow: hidden;
}
.jumbo-otc-inner { display: flex; flex-direction: column; align-items: center; width: 100%; max-width: 1440px; min-height: 0; }
.jumbo-otc-title {
    font-family: var(--mono);
    font-size: 20px;
    letter-spacing: 0.32em;
    color: var(--led);
    text-transform: uppercase;
    font-weight: 700;
}
.jumbo-otc-sub { font-family: var(--mono); font-size: 30px; font-weight: 700; color: var(--bone); margin-top: 8px; }
.jumbo-otc-timer-block { display: flex; flex-direction: column; align-items: center; margin: 16px 0 26px; }
.jumbo-otc-timer { font-family: var(--mono); font-size: 54px; font-weight: 700; color: var(--bone); line-height: 1.1; }
.jumbo-otc-timer-label { font-family: var(--mono); font-size: 13px; letter-spacing: 0.22em; color: var(--led); text-transform: uppercase; font-weight: 700; margin-top: 4px; }
.jumbo-otc-league {
    grid-column: 1 / -1;
    font-family: var(--mono);
    font-size: 14px;
    letter-spacing: 0.24em;
    color: var(--led);
    text-transform: uppercase;
    font-weight: 700;
    margin: 14px 0 4px;
}
.jumbo-otc-league:first-child { margin-top: 0; }
.jumbo-otc-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 8px 26px;
    width: 100%;
    min-height: 0;
    overflow-y: auto;
}
.jumbo-otc-grid .jumbo-mini { padding: 9px 16px; border-radius: 8px; }
.jumbo-otc-grid .jumbo-mini-abbr { font-size: 19px; }
.jumbo-otc-grid .jumbo-mini-score { font-size: 28px; }
.jumbo-otc-grid .jumbo-mini-team img { width: 30px; height: 30px; }
.jumbo-otc-grid .jumbo-mini-status { font-size: 13px; }
.jumbo-otc-grid .jumbo-mini-leader { font-size: 12px; }

/* Manual "End Session" button (pages_jumbotron.render()) — session
   request: "an end session button... that closes out the game session
   therefore closing the jumbotron." This app's first real interactive
   widget (everything else is passive display) — a genuine st.button.
   Originally pinned bottom-right, but that collided with Streamlit's
   own "Made with Streamlit" badge there — session correction: "put it
   in the bottom left in the same box as the standings." Positioned via
   its own Streamlit-generated wrapper (can't nest an actual st widget
   inside the standings panel's raw-HTML block) at coordinates matched
   to that panel's own on-screen box: left column starts at the
   .block-container's 1.1rem left padding, panel width 420px (see
   .jumbo-grid's grid-template-columns). Broad div[data-testid="stButton"]
   selector is safe only because this is currently the app's ONLY
   button anywhere — revisit with a scoped selector if a second one is
   ever added elsewhere. Higher z-index than both full-screen overlays
   above (9998/9997) so it's always reachable regardless of which one
   happens to be showing (neither has pointer-events:none the way the
   pitcher overlay does, so without this it could get covered instead
   of just visually topped). */
div[data-testid="stButton"] {
    position: fixed;
    left: 34px;
    bottom: 18px;
    z-index: 9999;
    width: auto;
}
div[data-testid="stButton"] button {
    background: rgba(16,22,32,0.82);
    border: 1px solid var(--edge);
    color: var(--mut);
    font-family: var(--mono);
    font-size: 12px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    padding: 8px 16px;
    border-radius: 8px;
}
div[data-testid="stButton"] button:hover {
    border-color: var(--led);
    color: var(--bone);
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
    .game-countdown-headline { font-size: 1.4rem; }
    .news-breaking-label { font-size: 1.15rem; }
    .tile-value { font-size: 2rem; }
    .market-hero-value { font-size: 1.5rem; }
    .morning-briefing { font-size: 1.05rem; padding: 0.8rem 1.1rem; }
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
    .sports-alert-bar-mlb, .sports-alert-bar-nhl {
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
