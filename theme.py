"""Apple-style dark glass CSS injected once at app start."""

CSS = """
<style>
#MainMenu, header, footer { visibility: hidden; }
.block-container {
    padding-top: 1.4rem;
    padding-bottom: 3.2rem;
    max-width: 1300px;
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
    margin-bottom: 0.6rem;
}

.hero-weather {
    text-align: right;
}

.weather-condition {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 0.4rem;
}

.clock {
    font-size: 2.6rem;
    font-weight: 600;
    letter-spacing: -0.02em;
    color: #F5F5F7;
    line-height: 1.1;
}

.date-sub {
    font-size: 1rem;
    color: #8E8E93;
    font-weight: 400;
}

.weather-icon svg {
    width: 2rem;
    height: 2rem;
    display: block;
    vertical-align: middle;
}

.flag-badge {
    font-size: 1.9rem;
    transition: opacity 0.6s ease;
}

.market-pill {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    margin-top: 0.5rem;
    background: rgba(0,0,0,0.4);
    border: 1px solid rgba(255,255,255,0.09);
    backdrop-filter: blur(24px) saturate(1.1);
    border-radius: 16px;
    padding: 0.35rem 0.85rem;
    font-size: 0.8rem;
}

.market-pill-label { color: #8E8E93; }
.market-pill-value { font-weight: 600; }
.market-up { color: #32D74B; }
.market-down { color: #FF6961; }

.country-name {
    font-size: 0.9rem;
    color: #8E8E93;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-top: 0.15rem;
}

.fade-wrap {
    animation: fadeIn 0.9s ease;
}

@keyframes fadeIn {
    from { opacity: 0; transform: translateY(6px); }
    to { opacity: 1; transform: translateY(0); }
}

.tile {
    position: relative;
    background: rgba(0,0,0,0.4);
    border: 1px solid rgba(255,255,255,0.09);
    backdrop-filter: blur(24px) saturate(1.1);
    border-radius: 16px;
    padding: 0.95rem 1rem;
    height: 100%;
}

.tile-flash-hot { animation: tile-pulse-hot 1.8s ease-in-out infinite; }
.tile-flash-cool { animation: tile-pulse-cool 1.8s ease-in-out infinite; }

@keyframes tile-pulse-hot {
    0%, 100% { box-shadow: 0 0 0 1px rgba(255,69,58,0.25), 0 0 0 0 rgba(255,69,58,0); }
    50% { box-shadow: 0 0 0 1px rgba(255,69,58,0.55), 0 0 22px 4px rgba(255,69,58,0.35); }
}

@keyframes tile-pulse-cool {
    0%, 100% { box-shadow: 0 0 0 1px rgba(10,132,255,0.25), 0 0 0 0 rgba(10,132,255,0); }
    50% { box-shadow: 0 0 0 1px rgba(10,132,255,0.55), 0 0 22px 4px rgba(10,132,255,0.35); }
}

.new-badge {
    position: absolute;
    top: 0.6rem;
    right: 0.7rem;
    font-size: 0.58rem;
    font-weight: 700;
    letter-spacing: 0.05em;
    color: #FFD60A;
    background: rgba(255,214,10,0.14);
    border-radius: 8px;
    padding: 0.12rem 0.4rem;
    animation: new-badge-fade 3s ease-in-out infinite;
}

@keyframes new-badge-fade {
    0%, 100% { opacity: 0.7; }
    50% { opacity: 1; }
}

.tile-label {
    font-size: 0.72rem;
    color: #8E8E93;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 0.3rem;
}

.tile-value {
    font-size: 1.6rem;
    font-weight: 600;
    color: #F5F5F7;
    letter-spacing: -0.01em;
}

.tile-prev {
    font-size: 0.72rem;
    color: #6E6E73;
    margin-top: 0.15rem;
}

.badge {
    display: inline-block;
    margin-top: 0.5rem;
    padding: 0.12rem 0.55rem;
    border-radius: 10px;
    font-size: 0.68rem;
    font-weight: 600;
    letter-spacing: 0.03em;
    text-transform: uppercase;
}

.badge-hot { background: rgba(255,69,58,0.18); color: #FF6961; }
.badge-cool { background: rgba(10,132,255,0.18); color: #5AC8FA; }
.badge-inline { background: rgba(255,255,255,0.08); color: #AEAEB2; }

.ticker-bar {
    position: fixed;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 10;
    background: rgba(0,0,0,0.55);
    backdrop-filter: blur(18px);
    border-top: 1px solid rgba(255,255,255,0.08);
    padding: 0.5rem 0;
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
    font-size: 0.8rem;
    color: #C7C7CC;
    padding: 0 0.6rem;
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
   ticker whenever a strictly-filtered alert is active. */
.news-alert-bar {
    position: fixed;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 15;
    display: flex;
    align-items: center;
    gap: 0.9rem;
    padding: 0.65rem 1.2rem;
    border-top: 1px solid rgba(255,255,255,0.15);
    backdrop-filter: blur(18px);
    animation: news-bar-in 0.5s ease, news-bar-pulse 2.4s ease-in-out infinite 0.5s;
}

@keyframes news-bar-in {
    from { transform: translateY(100%); }
    to { transform: translateY(0); }
}

@keyframes news-bar-pulse {
    0%, 100% { filter: brightness(1); }
    50% { filter: brightness(1.18); }
}

.news-alert-tag {
    flex-shrink: 0;
    font-size: 0.72rem;
    font-weight: 800;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    background: rgba(0,0,0,0.35);
    border-radius: 8px;
    padding: 0.25rem 0.6rem;
}

.news-alert-headline {
    font-size: 0.95rem;
    font-weight: 600;
    color: #FFFFFF;
}

.news-cat-fed-boc { background: rgba(191,90,242,0.85); color: #2b0f3d; }
.news-cat-data-surprise { background: rgba(90,200,250,0.85); color: #0a2c3d; }
.news-cat-earnings { background: rgba(50,215,75,0.85); color: #0b2b12; }
.news-cat-macro-shock { background: rgba(255,105,97,0.9); color: #3d0b08; }

.severity-track {
    position: relative;
    margin-top: 0.4rem;
    height: 4px;
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

.severity-fill-hot { background: #FF6961; }
.severity-fill-cool { background: #5AC8FA; }
.severity-fill-inline { background: #AEAEB2; }

.severity-caption {
    margin-top: 0.3rem;
    font-size: 0.65rem;
    color: #6E6E73;
}
</style>
"""


def inject():
    import streamlit as st
    st.markdown(CSS, unsafe_allow_html=True)
