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
    margin-bottom: 1rem;
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

.weather-extras {
    display: flex;
    justify-content: flex-end;
    gap: 0.6rem;
    margin-top: 0.3rem;
}

.weather-extra {
    font-size: 0.9rem;
    font-weight: 600;
    padding: 0.15rem 0.55rem;
    border-radius: 10px;
}

.weather-rain {
    color: #5AC8FA;
    background: rgba(90,200,250,0.14);
}

.weather-uv {
    color: #FF9F0A;
    background: rgba(255,159,10,0.14);
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
    background: rgba(0,0,0,0.4);
    border: 1px solid rgba(255,255,255,0.09);
    backdrop-filter: blur(24px) saturate(1.1);
    border-radius: 16px;
    padding: 0.5rem 1.1rem;
    font-size: 1.05rem;
}

.market-pill-label { color: #8E8E93; }
.market-pill-value { font-weight: 600; }
.market-up { color: #32D74B; }
.market-down { color: #FF6961; }

.country-name {
    font-size: 1.25rem;
    color: #8E8E93;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-top: 0.25rem;
}

.fade-wrap {
    animation: fadeIn 0.9s ease;
}

@keyframes fadeIn {
    from { opacity: 0; transform: translateY(6px); }
    to { opacity: 1; transform: translateY(0); }
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

.tile {
    position: relative;
    display: flex;
    flex-direction: column;
    background: rgba(0,0,0,0.4);
    border: 1px solid rgba(255,255,255,0.09);
    backdrop-filter: blur(24px) saturate(1.1);
    border-radius: 16px;
    padding: 1.6rem 1.5rem;
    height: 100%;
    box-sizing: border-box;
}

.tile-label {
    height: 3.1em;
    overflow: hidden;
}

.severity-caption {
    height: 3.2em;
    overflow: hidden;
}

.tile-flash-bad { animation: tile-pulse-bad 1.8s ease-in-out infinite; }
.tile-flash-good { animation: tile-pulse-good 1.8s ease-in-out infinite; }
.tile-flash-neutral { animation: tile-pulse-neutral 1.8s ease-in-out infinite; }

@keyframes tile-pulse-bad {
    0%, 100% { box-shadow: 0 0 0 1px rgba(255,69,58,0.25), 0 0 0 0 rgba(255,69,58,0); }
    50% { box-shadow: 0 0 0 1px rgba(255,69,58,0.55), 0 0 22px 4px rgba(255,69,58,0.35); }
}

@keyframes tile-pulse-good {
    0%, 100% { box-shadow: 0 0 0 1px rgba(50,215,75,0.25), 0 0 0 0 rgba(50,215,75,0); }
    50% { box-shadow: 0 0 0 1px rgba(50,215,75,0.55), 0 0 22px 4px rgba(50,215,75,0.35); }
}

@keyframes tile-pulse-neutral {
    0%, 100% { box-shadow: 0 0 0 1px rgba(10,132,255,0.25), 0 0 0 0 rgba(10,132,255,0); }
    50% { box-shadow: 0 0 0 1px rgba(10,132,255,0.55), 0 0 22px 4px rgba(10,132,255,0.35); }
}

.new-badge {
    position: absolute;
    top: 0.8rem;
    right: 0.9rem;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.05em;
    color: #FFD60A;
    background: rgba(255,214,10,0.14);
    border-radius: 10px;
    padding: 0.15rem 0.5rem;
    animation: new-badge-fade 3s ease-in-out infinite;
}

@keyframes new-badge-fade {
    0%, 100% { opacity: 0.7; }
    50% { opacity: 1; }
}

.tile-label {
    font-size: 1rem;
    color: #ECECF1;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 0.45rem;
}

.tile-value {
    font-size: 2.6rem;
    font-weight: 600;
    color: #F5F5F7;
    letter-spacing: -0.01em;
}

.tile-prev {
    font-size: 0.95rem;
    color: #D6D6DC;
    margin-top: 0.25rem;
}

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
    background: rgba(0,0,0,0.55);
    backdrop-filter: blur(18px);
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
    animation: ticker-soon-fade 1.6s ease-in-out infinite;
}

@keyframes ticker-soon-fade {
    0%, 100% { opacity: 0.75; }
    50% { opacity: 1; }
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
.news-alert-bar {
    position: fixed;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 15;
    display: flex;
    align-items: center;
    gap: 1.1rem;
    padding: 0.9rem 1.5rem;
    background: linear-gradient(90deg, #7a0f10 0%, #b3181a 50%, #7a0f10 100%);
    border-top: 2px solid rgba(255,255,255,0.25);
    box-shadow: 0 -4px 24px rgba(179,20,20,0.35);
    overflow: hidden;
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
    transition: opacity 1s linear, transform 1s linear, letter-spacing 1s linear;
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
    transition: opacity 1s linear, transform 1s linear;
}

.news-alert-headline {
    font-size: 1.3rem;
    font-weight: 600;
    color: #FFFFFF;
    transition: opacity 1s linear, transform 1s linear;
}

.news-cat-fed-boc { background: rgba(191,90,242,0.9); color: #2b0f3d; }
.news-cat-data-surprise { background: rgba(90,200,250,0.9); color: #0a2c3d; }
.news-cat-earnings { background: rgba(50,215,75,0.9); color: #0b2b12; }
.news-cat-macro-shock { background: rgba(255,255,255,0.9); color: #7a0f10; }

.severity-track {
    position: relative;
    margin-top: 0.55rem;
    height: 6px;
    width: 100%;
    background: rgba(255,255,255,0.08);
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
</style>
"""


def inject():
    import streamlit as st
    st.markdown(CSS, unsafe_allow_html=True)
