"""Bloomberg-terminal-style full institutional view of BRDN. Session
request: "make a shortcut for p on the dashboard... bring up the full
institutional analysis on my stock in a Bloomberg terminal style, kinda
like the Jumbotron, but for a Bloomberg terminal." A full-screen
takeover, same shape as pages_jumbotron.py — app.py suppresses the
normal hero row/chrome for this page the exact same way it does for
the jumbotron (see app.py's own _terminal_active) — reached via the 'p'
hotkey or the 'S' screen picker, deliberately not part of the normal
PAGES rotation (same "hidden unless asked for" treatment jumbotron/
maintenance already get).

Deliberately its own distinct visual language, not a reskin of
pages_brayden_index.py's normal glass-card layout: black terminal
background, monospace type, amber labels, dense multi-panel grid, hard
borders instead of soft blur — the same "look like a different,
purpose-built instrument" contrast the jumbotron already has against
the rest of this app. Every number here is read straight from
brayden_index's own already-computed state (current()/history()/
last_report()/report_history()/track_record_summary()/employment_
report()/quarterly_report_status()) — no new computation of its own,
same cheap read-only contract pages_brayden_index.render() already has.
A "raw signal feed" panel (brayden_index.current_signals(), the actual
fact sheet the AI reasons from) was tried and cut — see the comment
where it used to sit for why: it re-ran the ENTIRE live fact-gathering
pipeline (real network calls) on every page view, turning a page meant
to feel instant into a 60-100s+ load, confirmed live."""

import html
from datetime import datetime

import streamlit as st

import brayden_index
import tiles

# Bloomberg's own real signature palette — black, amber labels, a
# brighter green/red than this app's normal market-up/market-down
# (#32D74B/#FF6961) since a terminal reads as more clinical/saturated
# than this app's usual soft glass-card look. Scoped entirely inside
# .brdn-terminal (theme.py) so nothing else in the app is touched.
_CHART_COLOR = {"good": "#00FF7F", "bad": "#FF3B30"}


def _fmt_time(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%m/%d %H:%M")


def _catalyst_line(c: dict) -> str:
    cls = "up" if c["direction"] == "bullish" else "down"
    arrow = "▲" if c["direction"] == "bullish" else "▼"
    mag = c["magnitude"].upper()
    label = html.escape(c["label"])
    note = html.escape(c.get("note", ""))
    note_html = f'<div class="brdn-terminal-dim">{note}</div>' if note else ""
    return (
        f'<div class="brdn-terminal-row">'
        f'<span class="{cls}">{arrow} {label}</span>'
        f'<span class="brdn-terminal-tag">{mag}</span>'
        f'</div>{note_html}'
    )


def _history_line(e: dict) -> str:
    pct = e["pct_change"]
    cls = "up" if pct > 0 else "down" if pct < 0 else ""
    sign = "+" if pct >= 0 else ""
    catalysts = e.get("catalysts") or []
    label = html.escape(catalysts[0]["label"]) if catalysts else "no named catalysts"
    return (
        f'<div class="brdn-terminal-row">'
        f'<span class="brdn-terminal-dim">{_fmt_time(e["ts"])}</span>'
        f'<span>{label}</span>'
        f'<span class="{cls}">{sign}{pct:.2f}%</span>'
        f'</div>'
    )


def render(now: datetime) -> None:
    data = brayden_index.current()
    price_history = brayden_index.history()
    report = brayden_index.last_report()
    expectations = brayden_index.expectations()
    entries = brayden_index.report_history(limit=10)
    stats = brayden_index.track_record_summary(limit=10)
    employment = brayden_index.employment_report()
    q_status = brayden_index.quarterly_report_status(now)
    next_report = brayden_index.next_report_due(now.date())
    reprice = brayden_index.next_reprice_estimate()

    tone = data["tone"]
    dir_class = "up" if tone == "good" else "down" if tone == "bad" else ""
    arrow = "▲" if tone == "good" else "▼" if tone == "bad" else "●"
    sign = "+" if data["change"] >= 0 else ""
    cycle_pct = data["cycle_pct_change"]
    cycle_class = "up" if cycle_pct > 0 else "down" if cycle_pct < 0 else ""
    cycle_sign = "+" if cycle_pct >= 0 else ""

    st.markdown('<div class="brdn-terminal">', unsafe_allow_html=True)

    st.markdown(
        f'<div class="brdn-terminal-header">'
        f'<span class="brdn-terminal-ticker">BRDN &lt;EQUITY&gt;</span>'
        f'<span class="brdn-terminal-price {dir_class}">${data["price"]:.2f}</span>'
        f'<span class="{dir_class}">{arrow} {sign}${abs(data["change"]):.2f} ({sign}{data["pct_change"]:.2f}%) TODAY</span>'
        f'<span class="brdn-terminal-tag">{html.escape(data["sentiment"]).upper()}</span>'
        f'<span class="brdn-terminal-dim brdn-terminal-clock">{now.strftime("%Y-%m-%d %H:%M:%S")} LCL · '
        f'NEXT REPRICE ~{int(reprice["seconds_until"] // 60)}M</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns([1, 1.4, 1])
    with col1:
        rows = [
            ("DAY OPEN", f'${data["day_open_price"]:.2f}'),
            ("LAST CYCLE", f'<span class="{cycle_class}">{cycle_sign}{cycle_pct:.2f}%</span>'),
            ("NET DRIFT (10C)", f'<span class="{"up" if stats and stats["net_drift_pct"] > 0 else "down" if stats and stats["net_drift_pct"] < 0 else ""}">'
             f'{"+" if stats and stats["net_drift_pct"] >= 0 else ""}{stats["net_drift_pct"]:.2f}%</span>' if stats else "N/A"),
            ("BULL/BEAR/FLAT", f'{stats["bullish_n"]}/{stats["bearish_n"]}/{stats["flat_n"]}' if stats else "N/A"),
            ("Q REPORT", "ON FILE" if q_status["filed_this_quarter"] else "OUTSTANDING"),
        ]
        row_html = "".join(
            f'<div class="brdn-terminal-row"><span class="brdn-terminal-dim">{label}</span><span>{value}</span></div>'
            for label, value in rows
        )
        st.markdown(
            f'<div class="brdn-terminal-panel"><div class="brdn-terminal-label">SNAPSHOT</div>{row_html}</div>',
            unsafe_allow_html=True,
        )
    with col2:
        sparkline_html = ""
        if len(price_history) >= 2:
            trend_tone = "good" if price_history[-1] >= price_history[0] else "bad"
            sparkline_html = tiles.sparkline_svg(
                price_history, trend_tone, width=640, height=140,
                color=_CHART_COLOR.get(trend_tone), stroke_width=2.5,
            )
        st.markdown(
            f'<div class="brdn-terminal-panel"><div class="brdn-terminal-label">PRICE HISTORY</div>'
            f'<div class="brdn-chart-wrap">{sparkline_html}</div></div>',
            unsafe_allow_html=True,
        )
    with col3:
        emp_lines = []
        if employment:
            tag = "BASELINE" if employment.get("is_baseline") else "FILED"
            emp_lines.append(f'<div class="brdn-terminal-row"><span class="brdn-terminal-dim">{employment["quarter_label"]}</span><span class="brdn-terminal-tag">{tag}</span></div>')
            emp_lines.append(f'<div class="brdn-terminal-dim brdn-terminal-wrap">{html.escape(employment["summary"][:220])}</div>')
        else:
            emp_lines.append('<div class="brdn-terminal-dim">No employment report on file.</div>')
        if next_report:
            emp_lines.append(
                f'<div class="brdn-terminal-row" style="margin-top:0.5rem;">'
                f'<span class="brdn-terminal-dim">NEXT Q REPORT</span>'
                f'<span>{next_report["quarter_label"]} · {next_report["days_until"]}D</span></div>'
            )
        st.markdown(
            f'<div class="brdn-terminal-panel"><div class="brdn-terminal-label">EMPLOYMENT FILE</div>{"".join(emp_lines)}</div>',
            unsafe_allow_html=True,
        )

    col4, col5 = st.columns([1, 1])
    with col4:
        catalysts = (report or {}).get("catalysts") or []
        cat_html = "".join(_catalyst_line(c) for c in catalysts) or '<div class="brdn-terminal-dim">No named catalysts this cycle.</div>'
        st.markdown(
            f'<div class="brdn-terminal-panel"><div class="brdn-terminal-label">WHY BRDN MOVED</div>{cat_html}</div>',
            unsafe_allow_html=True,
        )
    with col5:
        commentary = html.escape((report or {}).get("commentary", "")) or "—"
        expectations_html = html.escape(expectations) or "—"
        st.markdown(
            f'<div class="brdn-terminal-panel"><div class="brdn-terminal-label">ANALYST COMMENTARY</div>'
            f'<div class="brdn-terminal-quote">"{commentary}"</div>'
            f'<div class="brdn-terminal-label" style="margin-top:0.6rem;">PRICED-IN EXPECTATIONS</div>'
            f'<div class="brdn-terminal-dim brdn-terminal-wrap">{expectations_html}</div></div>',
            unsafe_allow_html=True,
        )

    # Session incident: a "RAW SIGNAL FEED" panel here used to call
    # brayden_index.current_signals() — which re-runs the ENTIRE fact-
    # gathering pipeline (portfolio, two real TomTom calls via commute
    # status, a live email IMAP fetch measured at ~16s alone, market
    # data, road conditions...) fresh, live, on every single page view.
    # Every other BRDN page view is explicitly a cheap, no-network read
    # of already-computed state (see pages_brayden_index.py's own
    # module docstring) — this broke that contract and made a hotkey-
    # triggered page that should feel instant take 60-100s+ to render,
    # confirmed live (timed each real call locally: commute_status
    # alone ~7s, email alone ~16s). Cut entirely rather than cached —
    # the transparency idea was nice but not worth that cost for a page
    # meant to be instant; the normal BRDN page's own "what the market
    # believes" section already covers the same spirit far more
    # cheaply.
    rows_html = "".join(_history_line(e) for e in reversed(entries)) or '<div class="brdn-terminal-dim">No cycle history yet.</div>'
    st.markdown(
        f'<div class="brdn-terminal-panel"><div class="brdn-terminal-label">TRACK RECORD (LAST {len(entries)})</div>{rows_html}</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="brdn-terminal-footer">SIMULATED INSTRUMENT — FOR ENTERTAINMENT ONLY — NOT A REAL SECURITY — '
        'PRESS P TO EXIT</div></div>',
        unsafe_allow_html=True,
    )
