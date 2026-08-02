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

/* Predictions page — session request: "make it its own page for just
   prediction market things." Session follow-up: "don't make the BoC,
   Fed, and the other one big, make them fit into the same row...
   nice, clean format, like a list almost" — every bank, Fed/BoC/BoJ
   included, is one compact row here; there's no separate hero-tile
   treatment anymore. */
.prediction-source-note {
    font-size: 1.15rem;
    color: #ABB2C4;
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
    grid-template-columns: 2.6rem 4.4rem 1fr;
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
    color: #ABB2C4;
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
    color: #ABB2C4;
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
/* Session request: "color the bottom bar the same way it's colored on
   the [Predictions] page" — same fire/ice values as
   .prediction-direction-cut/-hike, not the green/red good/bad
   language above (a rate direction isn't "good or bad news" the way a
   market move is). Hold uses .ticker-item-neutral (plain white)
   already, no separate class needed. */
.ticker-item-cut { color: #3DD9FF; font-weight: 600; }
.ticker-item-hike { color: #FF5A1F; font-weight: 600; }

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
    z-index: 10000;  /* see .news-alert-bar's own comment above */
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
.sports-alert-bar-mlb, .sports-alert-bar-nhl, .sports-alert-bar-nfl {
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
.sports-alert-bar-mlb {
    background: linear-gradient(90deg, #0f2a7a 0%, #1a5ab3 50%, #0f2a7a 100%);
    box-shadow: 0 -4px 24px rgba(26,90,179,0.4);
}
.sports-alert-bar-nhl {
    background: linear-gradient(90deg, #7a0f10 0%, #b3181a 50%, #7a0f10 100%);
    box-shadow: 0 -4px 24px rgba(179,20,20,0.35);
}
/* Saints' own gold — real team color (ESPN's #d3bc8d), not the fixed
   FLASH_BLUE/FLASH_RED shared by every other team's non-opponent
   scoring play, since this one already IS a genuine team color. */
.sports-alert-bar-nfl {
    background: linear-gradient(90deg, #7a6a3f 0%, #b3993f 50%, #7a6a3f 100%);
    box-shadow: 0 -4px 24px rgba(179,153,63,0.35);
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
.weather-alert-bar-extreme {
    background: linear-gradient(90deg, #5c0a0b 0%, #d4181a 50%, #5c0a0b 100%);
    box-shadow: 0 -4px 24px rgba(212,24,26,0.5);
}
.weather-alert-bar-warning {
    background: linear-gradient(90deg, #7a0f10 0%, #b3181a 50%, #7a0f10 100%);
    box-shadow: 0 -4px 24px rgba(179,20,20,0.35);
}
.weather-alert-bar-warning-moderate {
    background: linear-gradient(90deg, #7a3d10 0%, #b3641a 50%, #7a3d10 100%);
    box-shadow: 0 -4px 24px rgba(179,100,20,0.3);
}
.weather-alert-bar-watch, .weather-alert-bar-statement {
    background: linear-gradient(90deg, #7a4a0f 0%, #b3811a 50%, #7a4a0f 100%);
    box-shadow: 0 -4px 24px rgba(179,142,20,0.35);
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
.weather-statement-watch .weather-statement-label { color: #FFB340; }
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
       first paint, see commute_reminder.render_leave_headline, so this
       should only ever be visible for a flash). */
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
   groq_client.ai_status_by_model for the full status list. */
.ai-status-bar {
    position: fixed;
    bottom: 60px;
    right: 14px;
    z-index: 400;
    display: flex;
    flex-direction: column;
    gap: 0.22rem;
    padding: 0.32rem 0.65rem;
    border-radius: 10px;
    background: rgba(12,12,16,0.62);
    backdrop-filter: blur(20px) saturate(160%);
    -webkit-backdrop-filter: blur(20px) saturate(160%);
    border: 1px solid rgba(255,255,255,0.1);
    opacity: 0.55;
    transition: opacity 0.2s ease;
}
.ai-status-bar:hover {
    opacity: 1;
}
.ai-status-row {
    display: flex;
    align-items: center;
    gap: 0.4rem;
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

/* Session request: "redesign the mobile UI... see the full pages...
   without issues and lag." Confirmed live (same root cause the
   jumbotron takeover already found and fixed for itself, see
   .block-container:has(.jumbo) > div's own comment below): every one
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
.stElementContainer:has(.ai-status-bar),
.stElementContainer:has(.rotation-timer-track),
.stElementContainer:has(.ticker-bar),
.stElementContainer:has(.top-alert-bar),
.stElementContainer:has(.news-alert-bar),
.stElementContainer:has(.news-alert-bar-market),
.stElementContainer:has(.commute-alert-bar),
.stElementContainer:has(.sports-alert-bar-mlb),
.stElementContainer:has(.sports-alert-bar-nhl),
.stElementContainer:has(.sports-alert-bar-nfl),
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
.mobile-nav-item-predictions { color: #0A84FF !important; }
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
    color: #ABB2C4 !important;
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

/* ============ JUMBOTRON (pages_jumbotron.py) ============
   A self-contained arena-scoreboard skin that only ever renders while
   sports_alerts.takeover_state() has the screen (T-60min through ~15min
   past final). Every rule here is namespaced .jumbo* so none of it can
   leak into the normal kiosk pages, which keep the Apple-glass look.
   LED amber on near-black, glass bento panels, Apple-system type
   throughout (see --label's own comment for why this no longer runs
   its own separate arena font stack). */
.jumbo {
    --led: #FFB300;
    --ledglow: rgba(255,179,0,0.5);
    --arena: #05070C;
    --glass: rgba(16,22,32,0.66);
    --edge: #1E2634;
    --edge-hi: #2E3B54;
    /* Session request: "you know how we have the apple style thing for
       the main page... I want that but keep the display dark." --edge
       is arena identity (dividers, glyph strokes, accent fallbacks —
       left untouched everywhere it already appears) and stays an
       opaque blue-gray; this is a separate, dedicated tone specifically
       for the handful of real card-surface borders below (.jumbo-panel,
       .jumbo-marquee, etc.), matching the translucent white edge every
       .tile elsewhere in this app already uses — the trait that actually
       reads as "glass" rather than "flat dark panel," independent of
       the arena color palette sitting on top of it. */
    --glass-edge: rgba(255,255,255,0.10);
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
    /* --label was JetBrains Mono, swapped for the small/secondary text
       (standings, Around The Leagues rows, situation strip, stat
       labels, blurb text) — session feedback: "pick a better font...
       I can't really read the little fonts... it's still not very
       apple-ish." --num (Bebas Neue) then got the same swap for the
       big numeric displays (clock, countdown, records, standings/
       leader scores) — "make the big numbers the same font as the ones
       you just implemented." Session feedback on the result: "that
       looks amazing, can you make every single text in the sheet that
       font" — --disp (Oswald, the board's own default/heading font:
       team names, division labels, everything that doesn't set its own
       font-family) now points to the same stack too, so every one of
       these three aliases the same system font. Kept as three separate
       variables rather than collapsing to one, since a future session
       asking to bring back a distinct display font only needs one line
       changed here, not a hunt through every call site again. */
    --label: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Helvetica Neue', sans-serif;
    --disp: var(--label);
    --num: var(--label);
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
    backdrop-filter: blur(24px) saturate(160%);
    -webkit-backdrop-filter: blur(24px) saturate(160%);
    border: 1px solid var(--glass-edge);
    border-radius: 18px;
    box-shadow: 0 10px 30px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.05);
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
    border-radius: 0 0 18px 18px;
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
    /* Session feedback: "make the big numbers the same font as the
       ones you just implemented" — every genuinely numeric big display
       (this clock, the weather temp, records, countdowns, standings/
       leader stats) reads in the same --label font as the small text.
       --num itself is now just an alias for --label (see its own
       comment) — kept as its own explicit font-family here rather than
       relying on inheritance so it's clear at a glance this element is
       the same font on purpose, not by accident. */
    font-family: var(--label);
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
    border: 1px solid var(--glass-edge);
    border-radius: 14px;
    padding: 5px 14px;
    background: var(--glass);
    backdrop-filter: blur(24px) saturate(160%);
    -webkit-backdrop-filter: blur(24px) saturate(160%);
}
.jumbo-wx-temp { font-family: var(--label); font-size: 26px; line-height: 1; }
.jumbo-wx-loc { font-size: 9px; font-weight: 300; color: var(--mut); letter-spacing: 0.24em; }

.jumbo-grid {
    flex: 1;
    display: grid;
    /* Right column widened 340->370px — the Around The Leagues text
       inside it just got noticeably bigger (see .jumbo-mini's own
       comment); the Featured board's flexible middle column easily
       absorbs the difference. */
    grid-template-columns: 420px 1fr 370px;
    gap: 12px;
    min-height: 0;
}
.jumbo-panel {
    border: 1px solid var(--glass-edge);
    /* Bumped from 14px to match the same generous "squircle" curve
       every .tile on the normal kiosk pages already uses — see
       --glass-edge's own comment above. */
    border-radius: 20px;
    background: var(--glass);
    backdrop-filter: blur(24px) saturate(160%);
    -webkit-backdrop-filter: blur(24px) saturate(160%);
    box-shadow: 0 10px 32px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.05);
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
    font-family: var(--label);
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
    /* Was 20px 20px 22px — trimmed for a third team (the Saints) now
       routinely sharing this rail; see .jumbo-rail-col's own comment. */
    padding: 13px 20px 14px;
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
.jumbo-hero-nfl { --tc: #D3BC8D; }
.jumbo-hero-ufc { --tc: #D20A0A; }
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
/* Session request: "playoff odds for each of my teams" — a compact
   suffix on the division line rather than its own row, since this
   card's vertical space is already tightly tuned (see this file's own
   padding-trim comments elsewhere on .jumbo-hero/.jumbo-form/
   .jumbo-gameline). var(--tc) is each sport's own hero accent color
   (set per .jumbo-hero-{sport} above), so this reads as a highlight,
   not routine muted text. */
.jumbo-hero-odds { color: var(--tc); font-weight: 600; letter-spacing: 0.08em; }
.jumbo-hero-rec { margin-left: auto; text-align: right; flex: 0 0 auto; padding-left: 10px; }
.jumbo-hero-rec-v { font-family: var(--label); font-size: 30px; line-height: 1; white-space: nowrap; }
.jumbo-hero-rec-l { font-size: 10px; font-weight: 300; color: var(--mut-2); letter-spacing: 0.3em; white-space: nowrap; }
.jumbo-form { display: flex; gap: 7px; align-items: center; margin-top: 9px; }  /* was 13px — see .jumbo-rail-col's own comment */
.jumbo-form-label { font-size: 12px; font-weight: 300; color: var(--mut-2); letter-spacing: 0.24em; margin-right: 3px; }
.jumbo-form i { width: 13px; height: 13px; border-radius: 50%; display: inline-block; }
.jumbo-form-w { background: var(--ok); box-shadow: 0 0 6px rgba(50,213,131,0.5); }
.jumbo-form-l { background: rgba(255,69,58,0.35); border: 1px solid rgba(255,69,58,0.5); }
.jumbo-gameline {
    /* margin-top/padding trimmed from 14px/12px 15px — see
       .jumbo-rail-col's own comment on why this rail got tighter. */
    margin-top: 9px;
    border: 1px solid var(--glass-edge);
    border-radius: 14px;
    background: rgba(8,11,17,0.7);
    backdrop-filter: blur(20px) saturate(160%);
    -webkit-backdrop-filter: blur(20px) saturate(160%);
    padding: 9px 15px;
    font-family: var(--label);
    font-size: 16px;
    color: var(--mut);
    line-height: 1.6;
}
.jumbo-gameline b { color: var(--bone); font-weight: 600; }
.jumbo-gl-score { color: var(--led); font-weight: 800; font-size: 19px; }
.jumbo-gl-cd { font-family: var(--label); color: var(--bone); font-size: 24px; letter-spacing: 0.08em; margin-left: 10px; }
/* Same "delayed instead of stuck at 0:00" fix as .jumbo-countdown-
   delayed above, sized for this compact rail chip instead of the big
   featured board. */
.jumbo-gl-cd-delayed { color: #FF9F0A; font-size: 18px; }
.jumbo-w { color: var(--ok); }
.jumbo-l { color: var(--live); }
.jumbo-offseason { border-style: dashed; color: var(--mut-2); letter-spacing: 0.28em; font-size: 13px; }
/* Session request: "for the teams that aren't currently in season,
   can we have a little countdown on their team bar" — replaces the
   plain "OFFSEASON" text with a real sentence ("Preseason opener Aug
   15 · in 20 days"), which .jumbo-offseason's own 0.28em letter-
   spacing (fine for one all-caps word) would badly reflow. */
.jumbo-offseason-countdown { letter-spacing: 0.02em; font-size: 14px; text-align: left; }
.jumbo-hero-live .jumbo-gameline { border-color: rgba(255,69,58,0.45); box-shadow: 0 0 16px rgba(255,69,58,0.1); }
/* My Teams + Division Standings share the left column as two stacked
   panels — session request moved standings out of each hero card into
   its own rotating panel at the bottom. My Teams sizes to its own
   content; standings takes whatever's left. Session report adding a
   third team (the Saints): "the standings are kinda cut off because
   we added the saints to the left bar" — with 3 hero cards (one of
   them potentially a full live/pregame card, not just a compact
   OFFSEASON line) My Teams' own natural height can genuinely exceed
   what's left for standings once flex: 0 0 auto (fixed, never shrinks)
   met a column that's now consistently tighter than it was designed
   for at 1-2 teams. My Teams can now shrink (flex-shrink: 1, was 0) if
   it truly has to, clipping its own lowest-priority (bottom-most, per
   COUNTDOWN_PRIORITY) card rather than starving standings entirely;
   standings gets a real min-height floor so it's never squeezed to
   the ~6px "may as well not exist" state this report was about. */
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
    border: 1px solid var(--glass-edge);
    border-radius: 14px;
    background: rgba(8,11,17,0.7);
    backdrop-filter: blur(20px) saturate(160%);
    -webkit-backdrop-filter: blur(20px) saturate(160%);
    overflow: hidden;
    font-family: var(--label);
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
/* Session request: "playoff odds for each of my teams" — only ever
   present on our own team's row (see pages_jumbotron._standings_rows_html's
   own comment), so this never competes with .jumbo-standings-extra for
   every OTHER row in the division. */
.jumbo-standings-odds { flex: 0 0 auto; text-align: right; color: var(--led); font-weight: 600; margin-left: 8px; }

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
    font-family: var(--label);
    font-size: 92px;
    line-height: 0.92;
    width: 0.62em;
    text-align: center;
    color: var(--bone);
    font-weight: 600;
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
.jumbo-dash { color: var(--edge-hi); font-family: var(--label); font-size: 50px; }
.jumbo-vs { font-family: var(--num); font-size: 26px; letter-spacing: 0.4em; color: var(--mut-2); padding-left: 0.4em; }
.jumbo-countdown { font-family: var(--label); font-size: 96px; color: var(--bone); letter-spacing: 0.06em; line-height: 1; }
/* Session request: "the jays game is delayed can you make it show
   delayed instead of sitting at 0:00" — swaps in for .jumbo-countdown
   once the scheduled start has passed with no live game yet (see
   _board_html's own comment). A real status word/phrase, not a
   number, so it needs a much smaller size than the 96px countdown
   digits to avoid overflowing this same slot — sized and wrapped to
   still comfortably fit MLB's own longer detail_state text ("Delayed
   Start: Rain"), not just the plain "Delayed"/"Warmup" cases. Amber
   rather than the countdown's own neutral --bone, matching this app's
   established "something needs attention" color elsewhere. */
.jumbo-countdown-delayed {
    font-family: var(--disp);
    font-size: 34px;
    font-weight: 700;
    color: #FF9F0A;
    letter-spacing: 0.04em;
    line-height: 1.2;
    text-align: center;
    max-width: 320px;
}
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
    /* Session request: "make the situation bar more visible ie bigger,
       inning, bases, count, outs" — the whole strip (inning, base
       diamond, strike%, outs) scaled up together, same proportions
       just bigger, so it reads at a glance from across the room like
       the rest of this board's own distance-readability pass already
       treats its other big numbers. */
    text-align: center;
    font-family: var(--label);
    font-size: 34px;
    letter-spacing: 0.05em;
    padding: 14px 26px 18px;
    line-height: 1.7;
}
.jumbo-situ-hot { color: var(--led); font-weight: 700; margin-right: 20px; font-size: 38px; }
.jumbo-dim { color: var(--mut-2); }
.jumbo-clockbig { font-family: var(--label); font-size: 30px; color: var(--bone); letter-spacing: 0.06em; }
/* Pregame venue/weather + probable starters (pages_jumbotron.
   _pregame_extra_html) — session request, all free data off the same
   feed already used for scoring plays. */
.jumbo-pregame-venue {
    text-align: center;
    font-family: var(--label);
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
    font-family: var(--label);
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
    font-family: var(--label);
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
    font-family: var(--label);
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
    backdrop-filter: blur(20px) saturate(160%);
    -webkit-backdrop-filter: blur(20px) saturate(160%);
    border: 1px solid var(--glass-edge);
    border-radius: 18px;
    box-shadow: 0 8px 24px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.05);
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
    font-family: var(--label);
    font-size: 52px;
    line-height: 1;
    color: var(--bone);
    letter-spacing: 0.03em;
    white-space: nowrap;
}
.jumbo-leader-big-cat {
    font-family: var(--label);
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
    font-family: var(--label);
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
    font-family: var(--label);
    font-size: 13px;
    letter-spacing: 0.18em;
    color: var(--led);
    font-weight: 700;
    text-transform: uppercase;
}
.jumbo-live-matchup-name {
    /* Same fix as jumbo-live-matchup-stat below — this was silently
       inheriting var(--disp) (Oswald at the time, condensed) at a
       forced 700, same swollen/blobby look. Session feedback: "can we
       make their name skinnier as well please i wanna be able to read
       that too." --disp is --label's own alias now (see its comment),
       so this explicit override is no longer strictly load-bearing —
       left in place since it still documents that this element is
       deliberately sized/weighted on its own, not just inheriting
       whatever the board's default happens to be. */
    font-family: var(--label);
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
       like a blob. pick a skinnier font." var(--num) was Bebas Neue at
       the time — a squat display font with no real bold weight of its
       own, so font-weight:700 on it was faking a bold and coming out
       swollen at this size. --label (see its own comment) has real
       weight steps and tabular figures, reads far slimmer for a stat
       number like this — and is what --num itself resolves to now too. */
    font-family: var(--label);
    font-size: 32px;
    font-weight: 600;
    color: var(--bone);
    line-height: 1.1;
}
/* Session request: "make those stats fire coloured or ice coloured if
   theyve been hot or cold lately... pulsing fire or pulsing ice
   colour. if its in normal range just make it white." Applies to the
   vs-pitcher line and the season OPS/ERA deltas only (sports_client's
   _vs_pitcher_heat/_batter_season_heat/_pitcher_season_heat) —
   everything else on this card stays the plain .jumbo-live-matchup-stat
   white above, including the batter's OVERALL Savant percentile, which
   gets its own continuous red/blue gradient via an inline style instead
   (see pages_jumbotron._savant_gradient_color) rather than this fixed
   hot/cold pulse. Same text-shadow-pulse pattern as .leave-headline's
   intensity tiers, just fire/ice instead of amber/red. */
/* Session feedback: "can you make the hot cold colours a little
   better?" The old cold (#5AC8FA, Apple's own systemBlue-light) sat
   too close to real team blues for comfort — this same card now shares
   the screen with team-colored gradients/win-bar fills (see
   pages_jumbotron._side_color), and a lot of MLB teams (Jays included)
   are blue. A stat reading "cold" could get misread as just team
   branding. Shifted to a distinctly electric cyan that no real team
   color is likely to land on, and the same idea for hot — the old
   #FF7A1A sat close enough to --led (#FFB300, this board's own
   dominant amber accent, on every tag/label/section header) to lose
   some of its own pop; shifted more saturated and red-leaning, further
   from amber, closer to a genuine flame. Both keep the fire/ice
   metaphor from the original request intact, just more distinct from
   everything else already using warm/cool accents on this board. */
.jumbo-live-matchup-stat-hot {
    color: #FF5A1F;
    animation: jumbo-matchup-pulse-hot 1.3s ease-in-out infinite;
}
.jumbo-live-matchup-stat-cold {
    color: #3DD9FF;
    animation: jumbo-matchup-pulse-cold 1.3s ease-in-out infinite;
}
@keyframes jumbo-matchup-pulse-hot {
    0%, 100% { text-shadow: 0 0 10px rgba(255,90,31,0.5); }
    50% { text-shadow: 0 0 22px rgba(255,90,31,0.95), 0 0 38px rgba(255,45,0,0.5); }
}
@keyframes jumbo-matchup-pulse-cold {
    0%, 100% { text-shadow: 0 0 10px rgba(61,217,255,0.5); }
    50% { text-shadow: 0 0 22px rgba(61,217,255,0.95), 0 0 38px rgba(61,217,255,0.5); }
}
.jumbo-live-matchup-stat-label {
    font-family: var(--label);
    font-size: 12px;
    letter-spacing: 0.2em;
    color: var(--led);
    font-weight: 700;
    text-transform: uppercase;
}
/* Session request: "add the full line score for the active pitchers
   below balls and strike count without making the pitchers name shift
   up" — MLB's own ready-made per-pitcher boxscore summary (e.g. "2.2
   IP, ER, 4 K, 3 BB"), appended strictly after the existing stat rows
   (see col()'s own comment in pages_jumbotron.py). A plain centered
   sentence rather than another stat-block: this is one whole line of
   text, not a value+label pair, so it doesn't try to force-fit the
   number/caption pattern the rows above use. */
.jumbo-live-matchup-line {
    margin-top: 6px;
    font-family: var(--label);
    font-size: 13px;
    color: var(--mut);
    text-align: center;
    white-space: nowrap;
}
.jumbo-live-matchup-vs {
    font-family: var(--label);
    font-size: 16px;
    font-weight: 700;
    color: var(--mut-2);
    letter-spacing: 0.1em;
    flex: 0 0 auto;
}
.jumbo-diamond { width: 84px; height: 84px; display: inline-block; vertical-align: -24px; margin: 0 22px; }
/* Session request: "make the bases react when someone gets on with a
   smooth lighting up animation" — the plain transition covers every
   state change (a runner forced out fades back to dark, same as
   lighting up fades bright), and .jumbo-base-flash layers a one-shot
   brighter pulse on top specifically for the moment a base goes from
   empty to occupied (pages_jumbotron._mlb_situation_html only adds
   that class on a genuine off->on transition, not on every rerun a
   base happens to still be on). Default animation-fill-mode (none)
   means once the 0.7s flash finishes, this rect falls back to
   whatever the plain rect.on rule below says — already the same
   var(--led) color the flash itself ends on, so there's no visible
   snap at the handoff. */
.jumbo-diamond rect { fill: #1A2230; stroke: var(--edge-hi); stroke-width: 1.5; transition: fill 0.4s ease, stroke 0.4s ease; }
.jumbo-diamond rect.on { fill: var(--led); stroke: var(--led); }
.jumbo-diamond rect.jumbo-base-flash { animation: jumbo-base-flash 0.7s ease-out; }
@keyframes jumbo-base-flash {
    0% { fill: #FFFFFF; stroke: #FFFFFF; filter: drop-shadow(0 0 6px var(--led)); }
    100% { fill: var(--led); stroke: var(--led); filter: none; }
}
/* Session request: "make counts and outs actual numbers instead of
   dots" — replaces the old ball/strike/out dot rows. */
.jumbo-situ-count, .jumbo-situ-outs {
    display: inline-block;
    font-weight: 700;
    color: var(--bone);
}
.jumbo-situ-count { margin-left: 18px; }
.jumbo-situ-outs { margin-left: 28px; }
/* Session request (carried over from the old dots): "are there
   animations for... there's a strikeout" — the count/outs number
   pulses the instant it climbs instead of just silently updating
   (pages_jumbotron._mlb_situation_html decides when that's genuine). */
.jumbo-situ-pulse { animation: jumbo-situ-pulse 0.6s ease-out; display: inline-block; }
@keyframes jumbo-situ-pulse {
    0% { transform: scale(1.35); text-shadow: 0 0 16px var(--led); }
    100% { transform: scale(1); text-shadow: none; }
}
/* Ball and strike digits get their own color and their own flash —
   session request: "make it so a ball is green and a strike is red
   and make it flash when a strike comes through and when a ball comes
   through." Same scale+glow shape as .jumbo-situ-pulse above, just
   colored per digit instead of one shared neutral pulse, so which of
   the two just happened reads at a glance. display:inline-block is a
   base rule here (not just set alongside the animation like
   .jumbo-situ-pulse does) since .jumbo-count-digit needs a stable
   layout whether or not it's actively flashing.
   (A same-evening detour turned this into a single merged strike%
   figure and back — session correction: "who wants the count shown as
   a percentage... revert the count to what it was before." The
   percentage version lives in _current_matchup_html's pitcher card
   instead now, see .jumbo-matchup-strike-pct below.) */
.jumbo-count-digit { display: inline-block; }
.jumbo-ball-flash { animation: jumbo-ball-flash 0.6s ease-out; }
.jumbo-strike-flash { animation: jumbo-strike-flash 0.6s ease-out; }
@keyframes jumbo-ball-flash {
    0% { transform: scale(1.35); color: #32D74B; text-shadow: 0 0 16px rgba(50,215,75,0.85); }
    100% { transform: scale(1); color: var(--bone); text-shadow: none; }
}
@keyframes jumbo-strike-flash {
    0% { transform: scale(1.35); color: #FF453A; text-shadow: 0 0 16px rgba(255,69,58,0.85); }
    100% { transform: scale(1); color: var(--bone); text-shadow: none; }
}

/* Batting order (pages_jumbotron._batting_order_rail_html) — session
   request, after attending a real Jays game: "the only stat they
   showed was OPS... gave me a very easy way of seeing who is the best
   hitter." Plain rows, no photos or extra stat categories beyond what
   the real ballpark board itself shows — deliberate minimalism, exactly
   what made it scannable in person. Session follow-up, with a real
   photo of Rogers Centre's own board as the reference: "make it just
   the team that's up to bat... number, player, position, and OPS...
   as close to that as possible... still legible from across the room."
   Only 9 rows now (one team, not two stacked), so each one gets real
   room — sized up well past the original two-team-stacked pass, closer
   to how big the reference board's own rows read. */
.jumbo-lineup-header {
    display: flex;
    align-items: center;
    gap: 10px;
    padding-bottom: 6px;
    margin-bottom: 6px;
    border-bottom: 1px solid var(--edge);
}
/* Higher specificity than the plain .jumbo-lineup-num/-name/-pos/-ops
   rules below (2 classes vs. 1), so the header's own small caption
   style wins there without needing a separate markup shape — same
   compound-selector trick already used elsewhere in this app
   (.prediction-row-outcome.prediction-direction-cut) for exactly this
   "shared column widths, different type scale" situation. */
.jumbo-lineup-header .jumbo-lineup-num,
.jumbo-lineup-header .jumbo-lineup-name,
.jumbo-lineup-header .jumbo-lineup-pos,
.jumbo-lineup-header .jumbo-lineup-ops {
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.08em;
    color: var(--mut-2);
}
.jumbo-lineup-row {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 7px 0;
    font-family: var(--label);
    font-size: 22px;
    border-bottom: 1px solid rgba(255,255,255,0.05);
}
.jumbo-lineup-row:last-child { border-bottom: none; }
.jumbo-lineup-num {
    flex: 0 0 30px;
    color: var(--mut-2);
    font-weight: 700;
    text-align: right;
    font-variant-numeric: tabular-nums;
}
.jumbo-lineup-name {
    flex: 1;
    min-width: 0;
    color: var(--bone);
    font-weight: 700;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.jumbo-lineup-pos { flex: 0 0 36px; color: var(--mut); font-size: 15px; text-align: center; }
.jumbo-lineup-ops {
    flex: 0 0 64px;
    color: var(--led);
    font-weight: 800;
    text-align: right;
    font-variant-numeric: tabular-nums;
}

.jumbo-sl {
    font-family: var(--label);
    font-size: 8.5px;
    letter-spacing: 0.32em;
    color: var(--led);
    text-transform: uppercase;
    margin-bottom: 7px;
}

/* Session request: "make a pre and postgame ai overview thats only
   generated once... have it do a pre and post game blurb." Same
   border-top-divider treatment as .jumbo-leaders (Current Matchup)
   right below it, so this reads as one more panel in the same stack,
   not a visually distinct callout competing for attention. */
.jumbo-blurb { border-top: 1px solid var(--edge); padding: 12px 26px 16px; }
.jumbo-blurb-text { font-size: 15px; line-height: 1.5; color: var(--bone); }

/* Last-play strip under the Current Matchup card — session request:
   "add a play badge that shows the last play from the live game feed
   and situation TOR LOGO 0-1 BOS LOGO ie: ____ grounded out to first
   directly from the live feed... below the batter pitcher matchup."
   Same border-top-divider treatment as .jumbo-leaders itself, just one
   size down since this is a supporting line, not its own section. */
.jumbo-lastplay {
    border-top: 1px solid var(--edge);
    margin-top: 10px;
    padding-top: 10px;
    text-align: center;
}
.jumbo-lastplay-score {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 10px;
    margin-bottom: 6px;
}
.jumbo-lastplay-logo {
    width: 26px;
    height: 26px;
    object-fit: contain;
}
.jumbo-lastplay-tally {
    font-family: var(--label);
    font-size: 15px;
    font-weight: 700;
    color: var(--bone);
    letter-spacing: 0.05em;
}
.jumbo-lastplay-desc {
    font-family: var(--label);
    font-size: 14px;
    font-weight: 500;
    color: var(--mut-2);
    line-height: 1.4;
    padding: 0 8px;
}

/* ---- UFC board ---- */
/* Session request: "add UFC to the jumbotron." A genuinely separate,
   simpler layout from the team-scoreboard grid above — no My Teams
   rail, no Around The Leagues, no LED score digits (none of that
   applies to a multi-bout fight card, see pages_jumbotron._ufc_
   board_html's own docstring) — just a hero panel for whichever bout
   matters most right now, and the full ordered card underneath it. */
/* Session follow-up: "I want the live fight to take up like the whole
   screen... similar to how a baseball or hockey game would look" — the
   hero row's own previous "auto" row sizing left it exactly as tall as
   its content needed, which read as small/cramped next to the full
   card list splitting the rest of the screen with it evenly. 3fr:1fr
   makes the hero panel explicitly dominant regardless of exact content
   height, the same way the team-scoreboard grid's own center column
   (see .jumbo-grid above) is always the visual anchor of that board —
   the full card list becomes a reference strip underneath it instead
   of co-equal billing. */
.jumbo-ufc-grid {
    grid-template-columns: 1fr;
    grid-template-rows: 3fr 1fr;
}
/* During "countdown" (before the card's first bout), _ufc_stats_html
   never renders (nothing's happened yet to compare — see its own
   docstring), so this panel's only children are the phase line and
   the hero VS row, neither of which grows to fill the panel's new,
   much taller 3fr share. Centered rather than left pinned to the top
   with dead space below it once .jumbo-ufc-stats (flex:1, so it
   already absorbs all real leftover space on its own) isn't there. */
.jumbo-ufc-hero-panel { justify-content: center; }
.jumbo-ufc-phase {
    flex: 0 0 auto;
    text-align: center;
    font-family: var(--num);
    font-size: 22px;
    letter-spacing: 0.1em;
    color: var(--mut);
    padding: 10px 0 0;
}
.jumbo-ufc-phase-live { color: var(--live); animation: jumbo-blink 1.4s infinite; }
.jumbo-ufc-hero {
    flex: 0 0 auto;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 56px;
    padding: 28px 20px 20px;
}
.jumbo-ufc-hero-fighter { flex: 1; text-align: center; min-width: 0; }
/* Sized up from 34px alongside the rest of this hero — session
   follow-up asked for this to read like the team-scoreboard's own big
   score digits (92px, see .jumbo-digit above), not a small caption;
   fighter names run longer than a 1-2 digit score though, so this
   lands well under that to avoid wrapping/overflow at 2-3 word names. */
.jumbo-ufc-hero-name {
    font-family: var(--disp);
    font-weight: 600;
    font-size: 56px;
    letter-spacing: 0.01em;
    line-height: 1.1;
}
.jumbo-ufc-hero-record {
    font-family: var(--num);
    font-size: 22px;
    color: var(--mut);
    margin-top: 10px;
}
.jumbo-ufc-winner .jumbo-ufc-hero-name { color: var(--ok); }
.jumbo-ufc-hero-mid { flex: 0 0 auto; text-align: center; }
.jumbo-ufc-hero-weight {
    font-size: 13px;
    font-weight: 300;
    letter-spacing: 0.2em;
    color: var(--mut-2);
    text-transform: uppercase;
}
.jumbo-ufc-hero-vs {
    font-family: var(--num);
    font-size: 40px;
    color: var(--led);
    text-shadow: 0 0 16px var(--ledglow);
    margin-top: 10px;
}
/* Knockdown callout — rare and dramatic enough (session follow-up:
   "everything" this board can honestly show) to flag on its own next
   to a fighter's record rather than bury inside the steadier volume
   stats below (see _ufc_stats_html's own docstring on why it's split
   out from the strikes/takedowns/control-time trio). */
.jumbo-ufc-kd-badge {
    display: inline-block;
    margin-left: 8px;
    padding: 2px 8px;
    border-radius: 6px;
    font-family: var(--label);
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0.05em;
    color: #0A0D12;
    background: var(--live);
}
/* Live stat comparison (pages_jumbotron._ufc_stats_html) — session
   follow-up: "live fight stats... implied odds to win if that's
   available." Same big-flanking-numbers-plus-bar shape as the team
   board's own .jumbo-wp-* win-probability bar, deliberately its own
   class family rather than reusing those directly: there's no real
   MMA win-probability model behind this (ESPN's pickcenterAvailable is
   false on every UFC bout — confirmed live, see ufc_client.
   fetch_bout_stats' own docstring), so the bar here reflects each
   fighter's actual share of real landed strikes/takedowns/control
   seconds, not a probability the way the team board's bar does. Two
   fixed accent colors (gold/blue) rather than per-side team colors —
   fighters don't have one the way a team's own color does, and ESPN's
   fighter_a/fighter_b order isn't a real red-corner/blue-corner
   assignment worth asserting. */
.jumbo-ufc-stats { flex: 1; min-height: 0; display: flex; flex-direction: column; justify-content: center; gap: 14px; padding: 4px 40px 20px; }
.jumbo-ufc-stat-row {}
.jumbo-ufc-stat-title {
    text-align: center;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.35em;
    color: var(--mut-2);
    margin-bottom: 6px;
}
.jumbo-ufc-stat-line { display: flex; align-items: center; gap: 14px; }
.jumbo-ufc-stat-value {
    font-family: var(--label);
    font-size: 22px;
    font-weight: 700;
    flex: 0 0 auto;
    min-width: 64px;
}
.jumbo-ufc-stat-value.jumbo-ufc-stat-a { text-align: right; color: var(--led); }
.jumbo-ufc-stat-value.jumbo-ufc-stat-b { color: #5AC8FA; }
.jumbo-ufc-stat-bar {
    flex: 1;
    height: 16px;
    border-radius: 6px;
    overflow: hidden;
    display: flex;
    border: 1px solid var(--edge);
}
.jumbo-ufc-stat-seg-a { background: var(--led); }
.jumbo-ufc-stat-seg-b { background: #5AC8FA; }
.jumbo-ufc-stat-labels {
    display: flex;
    justify-content: space-between;
    font-family: var(--label);
    font-size: 11px;
    font-weight: 700;
    color: var(--mut);
    margin-top: 4px;
    letter-spacing: 0.03em;
}
.jumbo-ufc-card-body { flex: 1; min-height: 0; overflow: hidden; display: flex; flex-direction: column; }
.jumbo-ufc-card-row {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 9px 16px;
    border-bottom: 1px solid var(--glass-edge);
    font-family: var(--label);
    font-size: 14px;
}
.jumbo-ufc-card-row:last-child { border-bottom: none; }
.jumbo-ufc-card-row-main { background: rgba(255,179,0,0.06); }
.jumbo-ufc-card-weight {
    flex: 0 0 120px;
    font-size: 10px;
    font-weight: 300;
    letter-spacing: 0.12em;
    color: var(--mut-2);
    text-transform: uppercase;
}
.jumbo-ufc-card-fighter { flex: 1; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.jumbo-ufc-card-fighter.jumbo-ufc-winner { color: var(--ok); font-weight: 600; }
.jumbo-ufc-card-vs { flex: 0 0 auto; color: var(--mut-2); font-size: 11px; }
.jumbo-ufc-card-status { flex: 0 0 160px; text-align: right; font-family: var(--num); font-size: 13px; color: var(--mut); }
.jumbo-ufc-live { color: var(--live); }
.jumbo-ufc-final { color: var(--mut); }
.jumbo-ufc-upcoming { color: var(--mut-2); }

/* ---- Around the leagues ---- */
.jumbo-around-body { flex: 1; min-height: 0; overflow: hidden; }
/* Session feedback: "improve the scoreboard to make it more visible
   from a distance, especially the around the league portion... I'm
   reading it from across the room." Every size in this section bumped
   roughly 25-30% (17->22px abbreviations, 26->32px scores, 11-12->13-
   14px status/leader lines, 28->34px team logos) — this panel is read
   at arm's length from a bed, not up close like a phone screen. */
.jumbo-around-league {
    font-family: var(--label);
    font-size: 14px;
    letter-spacing: 0.28em;
    color: var(--led);
    padding: 14px 18px 7px;
}
.jumbo-mini {
    display: flex;
    align-items: center;
    padding: 13px 18px;
    gap: 16px;
    border-bottom: 1px solid rgba(30,38,52,0.4);
}
.jumbo-mini-final { opacity: 0.42; }
.jumbo-mini-live { background: rgba(255,69,58,0.05); border-left: 3px solid var(--live); }
.jumbo-mini-teams { flex: 1; display: flex; flex-direction: column; gap: 7px; min-width: 0; }
.jumbo-mini-team { display: flex; align-items: center; gap: 10px; }
.jumbo-mini-team img { width: 34px; height: 34px; object-fit: contain; flex: 0 0 auto; }
.jumbo-mini-abbr { font-size: 22px; font-weight: 600; color: var(--mut); letter-spacing: 0.06em; }
.jumbo-mini-record { font-size: 13px; font-weight: 400; color: var(--mut-2); letter-spacing: 0.04em; }
.jumbo-mini-score { margin-left: auto; font-family: var(--label); font-size: 32px; line-height: 1; color: var(--bone); }
/* Session request: bring back the standout-performer line (see
   scores_client.game_leader) that used to show on the regular
   rotation's own Scores page. */
.jumbo-mini-leader {
    font-family: var(--label);
    font-size: 13px;
    color: var(--led);
    letter-spacing: 0.01em;
    margin-top: 3px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
.jumbo-mini-leader-stat { color: var(--bone); font-weight: 700; }
.jumbo-mini-status {
    font-family: var(--label);
    font-size: 14px;
    color: var(--mut-2);
    letter-spacing: 0.08em;
    text-transform: uppercase;
    text-align: right;
    flex: 0 0 auto;
    line-height: 1.5;
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
   itself (color/glow, not font — see --label's own comment on why the
   board no longer runs Bebas Neue/Oswald at all). Spelled out directly
   rather than var(--label): this overlay (app.py) renders outside
   .jumbo's own div entirely, so that custom property isn't in scope —
   same reasoning .jumbo-transition-sub below already documented. */
.jumbo-transition-in { background: #05070C; }
.jumbo-transition-brand {
    font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Helvetica Neue', sans-serif;
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
    font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Helvetica Neue', sans-serif;
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
    /* Can't use var(--label) here — this overlay (app.py) renders
       outside .jumbo's own div entirely, so that custom property isn't
       in scope. Same font stack it now points to, just spelled out. */
    font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Helvetica Neue', sans-serif;
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

/* Full-screen "out of town scoreboard" during a natural break in the
   featured game — session request: "between innings / periods can we
   go to a full screen out of town scoreboard. with a timer till the
   game resumes again." Same fixed-full-viewport approach as
   .jumbo-transition above. Reuses the sidebar Around The Leagues
   panel's own .jumbo-mini row markup (pages_jumbotron._mini_row_html)
   inside a bigger grid rather than a separate template —
   .jumbo-otc-grid-scoped overrides below just size those same rows up
   for a full-screen read. No animation-hold timing here: this is
   driven by real game state, up for exactly as long as the break
   itself lasts. (A full-screen "new pitcher" intro used to share this
   pattern at z-index 9998 — session feedback: "the pitchers toast
   showed up at the end of the 9th... way too early, the data delay
   didnt catch that... just get rid of them" — removed entirely.) */
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
    font-family: var(--label);
    font-size: 20px;
    letter-spacing: 0.32em;
    color: var(--led);
    text-transform: uppercase;
    font-weight: 700;
}
.jumbo-otc-sub { font-family: var(--label); font-size: 30px; font-weight: 700; color: var(--bone); margin-top: 8px; }
.jumbo-otc-timer-block { display: flex; flex-direction: column; align-items: center; margin: 16px 0 26px; }
.jumbo-otc-timer { font-family: var(--label); font-size: 54px; font-weight: 700; color: var(--bone); line-height: 1.1; }
.jumbo-otc-timer-label { font-family: var(--label); font-size: 13px; letter-spacing: 0.22em; color: var(--led); text-transform: uppercase; font-weight: 700; margin-top: 4px; }
.jumbo-otc-league {
    grid-column: 1 / -1;
    font-family: var(--label);
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
.jumbo-otc-grid .jumbo-mini { padding: 10px 16px; border-radius: 8px; }
.jumbo-otc-grid .jumbo-mini-abbr { font-size: 24px; }
.jumbo-otc-grid .jumbo-mini-score { font-size: 34px; }
.jumbo-otc-grid .jumbo-mini-team img { width: 36px; height: 36px; }
.jumbo-otc-grid .jumbo-mini-status { font-size: 15px; }
.jumbo-otc-grid .jumbo-mini-leader { font-size: 14px; }

/* Full-screen play-result announcement — session request: "add an
   animation that takes up the screen after every play. Single,
   Double, Triple, Home Run, Lineout, Strikout, Pop Out etc so i can
   tell what happened." z-index sits above the out-of-town overlay
   (9997, so a play result always wins if the two ever land on the
   same rerun) but below the game-mode transition curtain and control
   cluster (9999, both true top-level UI that should never be
   obscured). pointer-events: none since this is purely informational —
   never blocks the End Session button underneath, even before it
   fades.

   animation-duration here is just the fallback — pages_jumbotron.
   _play_result_overlay_html always sets it (and animation-delay)
   inline from PLAY_RESULT_HOLD_SECONDS, so this holds for as many
   reruns as it takes to fill that many seconds rather than being
   capped at whatever survives one 5s rerun cycle (session request:
   "can the animation be longer than 3 seconds?" — that's what the old
   fixed 3s version was actually bumping into). */
.jumbo-play-overlay {
    position: fixed;
    inset: 0;
    z-index: 9998;
    display: flex;
    align-items: center;
    justify-content: center;
    pointer-events: none;
    background: rgba(5,7,12,0.85);
    animation: jumbo-play-hold-fade 5s cubic-bezier(.4,0,.2,1) forwards;
}
@keyframes jumbo-play-hold-fade {
    0% { opacity: 1; }
    70% { opacity: 1; }
    100% { opacity: 0; visibility: hidden; }
}
.jumbo-play-text {
    font-family: var(--label);
    font-size: 96px;
    letter-spacing: 0.08em;
    text-align: center;
    line-height: 1.05;
    max-width: 90%;
    animation: jumbo-play-pop 0.5s cubic-bezier(.34,1.56,.64,1);
}
@keyframes jumbo-play-pop {
    0% { transform: scale(0.6); opacity: 0; }
    60% { transform: scale(1.08); opacity: 1; }
    100% { transform: scale(1); opacity: 1; }
}
/* Hit/out/neutral — same three-tone idea as the ball/strike flashes
   above (green for offense succeeding, red for an out, neutral white
   for anything not classified either way — a walk-off review, a wild
   pitch, etc.). */
.jumbo-play-overlay-hit .jumbo-play-text { color: #32D74B; text-shadow: 0 0 40px rgba(50,215,75,0.7), 0 0 8px rgba(50,215,75,0.9); }
.jumbo-play-overlay-out .jumbo-play-text { color: #FF453A; text-shadow: 0 0 40px rgba(255,69,58,0.7), 0 0 8px rgba(255,69,58,0.9); }
.jumbo-play-overlay-neutral .jumbo-play-text { color: var(--bone); text-shadow: 0 0 40px rgba(255,255,255,0.4); }

/* Bottom-left control cluster — End Session button (session request:
   "an end session button... that closes out the game session therefore
   closing the jumbotron") plus the live-data delay stepper (session
   request: "make it a setting i can adjust throughout the game").
   This app's only real interactive widgets (everything else is passive
   display) — genuine st.button()s, grouped in one
   st.container(key="jumbotron_controls") so they can be positioned and
   laid out as a single row via that container's own st-key-* class,
   rather than a bare div[data-testid="stButton"] selector (which only
   ever worked while there was exactly one button in the whole app).
   Position matches the old single-button placement — bottom-left,
   clearing the toast alert bar below (see that block's own comment),
   originally corrected from bottom-right which collided with
   Streamlit's own "Made with Streamlit" badge there. Higher z-index
   than the out-of-town-scoreboard overlay above (9997) so it's always
   reachable if that's showing (it doesn't set pointer-events:none, so
   without this it could get covered instead of just visually topped). */
.st-key-jumbotron_controls {
    position: fixed;
    left: 34px;
    bottom: 88px;
    z-index: 9999;
    width: auto !important;
    /* Streamlit's own div[data-testid="stVerticalBlock"] rule sets
       flex-direction: column at higher selector specificity than a
       plain class here can beat on its own (tag+attribute vs. one
       class) — confirmed live: without !important this cluster still
       stacked vertically, full viewport width, centered mid-screen
       instead of sitting as a row pinned bottom-left. */
    display: flex !important;
    flex-direction: row !important;
    align-items: center;
    gap: 10px;
}
/* Streamlit gives each widget's own wrapper a fixed column-style
   width by default — without this override the "−"/"+" buttons and
   the label between them stretch apart instead of sitting snug. */
.st-key-jumbotron_controls .stElementContainer {
    width: auto !important;
    flex: 0 0 auto;
}
/* The delay stepper (−/DELAY Xs/+) became its own st.fragment (see
   pages_jumbotron._delay_stepper's own comment — instant, page-
   independent responsiveness) after this cluster's layout was first
   built. Streamlit wraps a fragment's own content in an extra
   stLayoutWrapper > stVerticalBlock pair that didn't exist before and
   defaults to the same column layout the outer container's own rule
   above already had to override — confirmed live: without this, the
   stepper dropped onto its own vertical column below End Session
   instead of sitting in the same row. */
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
    background: rgba(16,22,32,0.82);
    backdrop-filter: blur(20px) saturate(160%);
    -webkit-backdrop-filter: blur(20px) saturate(160%);
    border: 1px solid var(--glass-edge);
    box-shadow: 0 6px 18px rgba(0,0,0,0.35);
    color: var(--mut);
    font-family: var(--label);
    font-size: 12px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    padding: 8px 16px;
    border-radius: 12px;
    white-space: nowrap;
}
.st-key-jumbotron_controls div[data-testid="stButton"] button:hover {
    border-color: var(--led);
    color: var(--bone);
}
/* Session report: "make it easier to click up/down on it" — the
   generic 12px/8px-16px button rule above was sized for a text label
   like "End Session," not a fast-repeat +/- tap target on a kiosk
   touchscreen. Bigger box, bigger glyph, same visual family. */
.st-key-jumbotron_delay_minus div[data-testid="stButton"] button,
.st-key-jumbotron_delay_plus div[data-testid="stButton"] button {
    padding: 14px 22px;
    font-size: 20px;
    font-weight: 700;
    line-height: 1;
}
.jumbo-delay-label {
    font-family: var(--label);
    font-size: 12px;
    letter-spacing: 0.08em;
    color: var(--mut);
    white-space: nowrap;
}
/* Session request: "make it so i can type my ideal stream delay
   please. the plus/minus boxes are finnicky" — replaced with a real
   st.number_input (see pages_jumbotron._delay_stepper's own comment):
   tapping into it brings up this touchscreen kiosk's own on-screen
   numeric keypad, letting the value be typed directly. Streamlit's own
   built-in label is already collapsed (label_visibility="collapsed")
   but still occupies a hidden row of layout height by default —
   zeroed out here so the field sits at the same compact size as the
   buttons it replaced, matching the rest of this cluster's own dark-
   glass treatment. */
.st-key-jumbotron_controls label[data-testid="stWidgetLabel"] {
    display: none;
}
.st-key-jumbotron_controls div[data-testid="stNumberInputContainer"] {
    background: rgba(16,22,32,0.82);
    backdrop-filter: blur(20px) saturate(160%);
    -webkit-backdrop-filter: blur(20px) saturate(160%);
    border: 1px solid var(--glass-edge);
    border-radius: 12px;
    box-shadow: 0 6px 18px rgba(0,0,0,0.35);
    width: 84px;
}
.st-key-jumbotron_controls input[data-testid="stNumberInputField"] {
    background: transparent;
    color: var(--bone);
    font-family: var(--label);
    font-size: 18px;
    font-weight: 700;
    text-align: center;
    padding: 12px 6px;
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
       instead of overridden. */
    .top-alert-bar, .weather-statement-bar, .leave-headline,
    .storm-headline, .game-countdown-headline {
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
    .sports-alert-bar-mlb, .sports-alert-bar-nhl, .sports-alert-bar-nfl {
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
    .ai-status-bar { display: none; }

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
