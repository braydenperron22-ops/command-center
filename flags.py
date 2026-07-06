"""Inline SVG flags — emoji flags don't render on Windows (shows 'US'/'CA'
letter codes instead of the actual flag), so these are drawn directly.

Preloaded broadly (not just the handful actually in use right now) so the
dynamic Conflicts page never has to wait on a flag being added — whatever
country gets detected in the news already has one ready.
"""


def _hstripes(*colors: str) -> str:
    """Equal horizontal bands, top to bottom."""
    n = len(colors)
    h = 16 / n
    rects = "".join(f'<rect y="{i * h:.2f}" width="24" height="{h:.2f}" fill="{c}"/>' for i, c in enumerate(colors))
    return f'<svg viewBox="0 0 24 16" xmlns="http://www.w3.org/2000/svg">{rects}</svg>'


def _vstripes(*colors: str) -> str:
    """Equal vertical bands, left to right."""
    n = len(colors)
    w = 24 / n
    rects = "".join(f'<rect x="{i * w:.2f}" width="{w:.2f}" height="16" fill="{c}"/>' for i, c in enumerate(colors))
    return f'<svg viewBox="0 0 24 16" xmlns="http://www.w3.org/2000/svg">{rects}</svg>'


US_FLAG = """<svg viewBox="0 0 24 16" xmlns="http://www.w3.org/2000/svg">
<rect width="24" height="16" fill="#B22234"/>
<g fill="#FFFFFF">
<rect y="1.23" width="24" height="1.23"/>
<rect y="3.69" width="24" height="1.23"/>
<rect y="6.15" width="24" height="1.23"/>
<rect y="8.62" width="24" height="1.23"/>
<rect y="11.08" width="24" height="1.23"/>
<rect y="13.54" width="24" height="1.23"/>
</g>
<rect width="10" height="8.62" fill="#3C3B6E"/>
</svg>"""

CA_FLAG = """<svg viewBox="0 0 24 16" xmlns="http://www.w3.org/2000/svg">
<rect width="24" height="16" fill="#FFFFFF"/>
<rect width="6" height="16" fill="#FF0000"/>
<rect x="18" width="6" height="16" fill="#FF0000"/>
<path fill="#FF0000" d="M12 2.5l0.9 1.9 1.9-0.9-0.4 2.1 2.1 0.3-1.5 1.5 1.1 1.8-2 -0.4 0.2 2-1.6-1.2v2.4h-0.7v-2.4l-1.6 1.2 0.2-2-2 0.4 1.1-1.8-1.5-1.5 2.1-0.3-0.4-2.1 1.9 0.9z"/>
</svg>"""

RU_FLAG = _hstripes("#FFFFFF", "#0039A6", "#D52B1E")
UA_FLAG = _hstripes("#005BBB", "#FFD500")

IL_FLAG = """<svg viewBox="0 0 24 16" xmlns="http://www.w3.org/2000/svg">
<rect width="24" height="16" fill="#FFFFFF"/>
<rect y="1.8" width="24" height="2.2" fill="#0038B8"/>
<rect y="12" width="24" height="2.2" fill="#0038B8"/>
<path fill="none" stroke="#0038B8" stroke-width="0.9" d="M12 5.2l2.6 4.5H9.4z"/>
<path fill="none" stroke="#0038B8" stroke-width="0.9" d="M12 10.8L9.4 6.3h5.2z"/>
</svg>"""

PS_FLAG = """<svg viewBox="0 0 24 16" xmlns="http://www.w3.org/2000/svg">
<rect width="24" height="5.33" fill="#000000"/>
<rect y="5.33" width="24" height="5.33" fill="#FFFFFF"/>
<rect y="10.67" width="24" height="5.33" fill="#007A3D"/>
<path fill="#CE1126" d="M0 0L8 8L0 16Z"/>
</svg>"""

SD_FLAG = """<svg viewBox="0 0 24 16" xmlns="http://www.w3.org/2000/svg">
<rect width="24" height="5.33" fill="#D21034"/>
<rect y="5.33" width="24" height="5.33" fill="#FFFFFF"/>
<rect y="10.67" width="24" height="5.33" fill="#000000"/>
<path fill="#007229" d="M0 0L9 8L0 16Z"/>
</svg>"""

MM_FLAG = """<svg viewBox="0 0 24 16" xmlns="http://www.w3.org/2000/svg">
<rect width="24" height="5.33" fill="#FECB00"/>
<rect y="5.33" width="24" height="5.33" fill="#34B233"/>
<rect y="10.67" width="24" height="5.33" fill="#EA2839"/>
<path fill="#FFFFFF" d="M12 5.5l1 2.7 2.9 0-2.3 1.7 0.9 2.7-2.5-1.7-2.5 1.7 0.9-2.7-2.3-1.7 2.9 0z"/>
</svg>"""

GB_FLAG = """<svg viewBox="0 0 24 16" xmlns="http://www.w3.org/2000/svg">
<rect width="24" height="16" fill="#00247D"/>
<path stroke="#FFFFFF" stroke-width="2.6" d="M0 0L24 16M24 0L0 16"/>
<path stroke="#CF142B" stroke-width="1.3" d="M0 0L24 16M24 0L0 16"/>
<rect x="10" width="4" height="16" fill="#FFFFFF"/>
<rect y="6" width="24" height="4" fill="#FFFFFF"/>
<rect x="10.8" width="2.4" height="16" fill="#CF142B"/>
<rect y="6.8" width="24" height="2.4" fill="#CF142B"/>
</svg>"""

FR_FLAG = _vstripes("#0055A4", "#FFFFFF", "#EF4135")
DE_FLAG = _hstripes("#000000", "#DD0000", "#FFCE00")

CN_FLAG = """<svg viewBox="0 0 24 16" xmlns="http://www.w3.org/2000/svg">
<rect width="24" height="16" fill="#DE2910"/>
<g fill="#FFDE00">
<path d="M5 2.5l0.7 2.1h2.2l-1.8 1.3 0.7 2.1-1.8-1.3-1.8 1.3 0.7-2.1-1.8-1.3h2.2z"/>
<circle cx="9.5" cy="1.8" r="0.5"/>
<circle cx="10.8" cy="3.2" r="0.5"/>
<circle cx="10.8" cy="5.2" r="0.5"/>
<circle cx="9.5" cy="6.4" r="0.5"/>
</g>
</svg>"""

IN_FLAG = """<svg viewBox="0 0 24 16" xmlns="http://www.w3.org/2000/svg">
<rect width="24" height="5.33" fill="#FF9933"/>
<rect y="5.33" width="24" height="5.33" fill="#FFFFFF"/>
<rect y="10.67" width="24" height="5.33" fill="#138808"/>
<circle cx="12" cy="8" r="1.8" fill="none" stroke="#000080" stroke-width="0.4"/>
</svg>"""

JP_FLAG = """<svg viewBox="0 0 24 16" xmlns="http://www.w3.org/2000/svg">
<rect width="24" height="16" fill="#FFFFFF"/>
<circle cx="12" cy="8" r="4.2" fill="#BC002D"/>
</svg>"""

SY_FLAG = """<svg viewBox="0 0 24 16" xmlns="http://www.w3.org/2000/svg">
<rect width="24" height="5.33" fill="#CE1126"/>
<rect y="5.33" width="24" height="5.33" fill="#FFFFFF"/>
<rect y="10.67" width="24" height="5.33" fill="#000000"/>
<g fill="#007A3D"><path d="M9 6.5l0.5 1.5h1.6l-1.3 0.9 0.5 1.5-1.3-0.9-1.3 0.9 0.5-1.5-1.3-0.9h1.6z"/><path d="M15 6.5l0.5 1.5h1.6l-1.3 0.9 0.5 1.5-1.3-0.9-1.3 0.9 0.5-1.5-1.3-0.9h1.6z"/></g>
</svg>"""

IQ_FLAG = _hstripes("#CE1126", "#FFFFFF", "#000000")
IR_FLAG = _hstripes("#239F40", "#FFFFFF", "#DA0000")
YE_FLAG = _hstripes("#CE1126", "#FFFFFF", "#000000")

LB_FLAG = """<svg viewBox="0 0 24 16" xmlns="http://www.w3.org/2000/svg">
<rect width="24" height="4" fill="#EE161F"/>
<rect y="4" width="24" height="8" fill="#FFFFFF"/>
<rect y="12" width="24" height="4" fill="#EE161F"/>
<path fill="#00A651" d="M12 6l1.4 3.4h-2.8z"/>
<rect x="10.8" y="9.4" width="2.4" height="1" fill="#00A651"/>
</svg>"""

SA_FLAG = """<svg viewBox="0 0 24 16" xmlns="http://www.w3.org/2000/svg">
<rect width="24" height="16" fill="#006C35"/>
<rect x="4" y="7" width="14" height="0.9" fill="#FFFFFF"/>
</svg>"""

TR_FLAG = """<svg viewBox="0 0 24 16" xmlns="http://www.w3.org/2000/svg">
<rect width="24" height="16" fill="#E30A17"/>
<circle cx="9.5" cy="8" r="3.4" fill="#FFFFFF"/>
<circle cx="10.6" cy="8" r="2.8" fill="#E30A17"/>
<path fill="#FFFFFF" d="M14 8l1.9-0.6-1.2 1.6 0-2 1.2 1.6z"/>
</svg>"""

SS_FLAG = """<svg viewBox="0 0 24 16" xmlns="http://www.w3.org/2000/svg">
<rect width="24" height="5.33" fill="#000000"/>
<rect y="5.33" width="24" height="5.33" fill="#FFFFFF"/>
<rect y="10.67" width="24" height="5.33" fill="#078930"/>
<path fill="#DA121A" d="M0 5.33h24v5.33H0z" opacity="0.001"/>
<rect y="6.8" width="24" height="2.4" fill="#DA121A"/>
<path fill="#0F47AF" d="M0 0L9 8L0 16Z"/>
<path fill="#FCDD09" d="M2.5 8l1-2.6 1 2.6-1 2.6z"/>
</svg>"""

ET_FLAG = """<svg viewBox="0 0 24 16" xmlns="http://www.w3.org/2000/svg">
<rect width="24" height="5.33" fill="#078930"/>
<rect y="5.33" width="24" height="5.33" fill="#FCDD09"/>
<rect y="10.67" width="24" height="5.33" fill="#DA121A"/>
<circle cx="12" cy="8" r="2.6" fill="#0F47AF"/>
</svg>"""

SO_FLAG = """<svg viewBox="0 0 24 16" xmlns="http://www.w3.org/2000/svg">
<rect width="24" height="16" fill="#4189DD"/>
<path fill="#FFFFFF" d="M12 5l0.9 2.8h2.9l-2.3 1.7 0.9 2.8-2.4-1.7-2.4 1.7 0.9-2.8-2.3-1.7h2.9z"/>
</svg>"""

CD_FLAG = """<svg viewBox="0 0 24 16" xmlns="http://www.w3.org/2000/svg">
<rect width="24" height="16" fill="#007FFF"/>
<path fill="#F7D618" d="M0 16L24 0v3.5L3.5 16z"/>
<path fill="#CE1021" d="M0 16L24 0v2L2.5 16z"/>
<path fill="#F7D618" d="M4 3l0.6 1.9h2l-1.6 1.2 0.6 1.9-1.6-1.2-1.6 1.2 0.6-1.9-1.6-1.2h2z"/>
</svg>"""

ML_FLAG = _vstripes("#14B53A", "#FCD116", "#CE1126")
NE_FLAG = """<svg viewBox="0 0 24 16" xmlns="http://www.w3.org/2000/svg">
<rect width="24" height="5.33" fill="#E05206"/>
<rect y="5.33" width="24" height="5.33" fill="#FFFFFF"/>
<rect y="10.67" width="24" height="5.33" fill="#0DB02B"/>
<circle cx="12" cy="8" r="1.8" fill="#E05206"/>
</svg>"""

NG_FLAG = _vstripes("#008751", "#FFFFFF", "#008751")

LY_FLAG = """<svg viewBox="0 0 24 16" xmlns="http://www.w3.org/2000/svg">
<rect width="24" height="4" fill="#E70013"/>
<rect y="4" width="24" height="8" fill="#000000"/>
<rect y="12" width="24" height="4" fill="#239E46"/>
<path fill="#FFFFFF" d="M11 6.8l1.9 4.6h-2z"/>
</svg>"""

TD_FLAG = _vstripes("#002664", "#FECB00", "#C60C30")

CF_FLAG = """<svg viewBox="0 0 24 16" xmlns="http://www.w3.org/2000/svg">
<rect width="24" height="4" fill="#003082"/>
<rect y="4" width="24" height="4" fill="#FFFFFF"/>
<rect y="8" width="24" height="4" fill="#289728"/>
<rect y="12" width="24" height="4" fill="#FFCE00"/>
<rect x="10.8" width="2.4" height="16" fill="#D21034"/>
<path fill="#FFCE00" d="M4 1.5l0.5 1.5h1.6l-1.3 0.9 0.5 1.5-1.3-0.9-1.3 0.9 0.5-1.5-1.3-0.9h1.6z"/>
</svg>"""

MZ_FLAG = """<svg viewBox="0 0 24 16" xmlns="http://www.w3.org/2000/svg">
<rect width="24" height="16" fill="#FFFFFF"/>
<rect width="24" height="5.33" fill="#009739"/>
<rect y="10.67" width="24" height="5.33" fill="#000000"/>
<path fill="#CE1126" d="M0 0L10 8L0 16Z"/>
<path fill="#FCD116" d="M2 6.3l0.6 1.9h2l-1.6 1.1 0.6 1.9-1.6-1.1-1.6 1.1 0.6-1.9-1.6-1.1h2z"/>
</svg>"""

CM_FLAG = """<svg viewBox="0 0 24 16" xmlns="http://www.w3.org/2000/svg">
<rect width="24" height="16" fill="#007A5E"/>
<rect x="8" width="8" height="16" fill="#CE1126"/>
<rect x="16" width="8" height="16" fill="#FCD116"/>
<path fill="#FCD116" d="M12 6l0.9 2.6h2.7l-2.2 1.6 0.8 2.6-2.2-1.6-2.2 1.6 0.8-2.6-2.2-1.6h2.7z"/>
</svg>"""

AF_FLAG = """<svg viewBox="0 0 24 16" xmlns="http://www.w3.org/2000/svg">
<rect width="24" height="16" fill="#FFFFFF"/>
<circle cx="12" cy="8" r="2.6" fill="none" stroke="#000000" stroke-width="0.6"/>
</svg>"""

PK_FLAG = """<svg viewBox="0 0 24 16" xmlns="http://www.w3.org/2000/svg">
<rect width="24" height="16" fill="#01411C"/>
<rect width="6" height="16" fill="#FFFFFF"/>
<circle cx="16" cy="8" r="3.2" fill="#FFFFFF"/>
<circle cx="17.3" cy="8" r="2.6" fill="#01411C"/>
<path fill="#FFFFFF" d="M20 8l1.9-0.6-1.2 1.6 0-2 1.2 1.6z"/>
</svg>"""

KP_FLAG = """<svg viewBox="0 0 24 16" xmlns="http://www.w3.org/2000/svg">
<rect width="24" height="16" fill="#024FA2"/>
<rect y="2.2" width="24" height="11.6" fill="#FFFFFF"/>
<rect y="3.2" width="24" height="9.6" fill="#ED1C27"/>
<circle cx="7" cy="8" r="2.2" fill="#FFFFFF"/>
<path fill="#ED1C27" d="M7 6.3l0.6 1.7h1.8l-1.5 1 0.6 1.7-1.5-1-1.5 1 0.6-1.7-1.5-1h1.8z"/>
</svg>"""

KR_FLAG = """<svg viewBox="0 0 24 16" xmlns="http://www.w3.org/2000/svg">
<rect width="24" height="16" fill="#FFFFFF"/>
<circle cx="12" cy="8" r="3.2" fill="#CD2E3A"/>
<path fill="#0047A0" d="M12 4.8a3.2 3.2 0 0 0 0 6.4 1.6 1.6 0 0 1 0-3.2 1.6 1.6 0 0 0 0-3.2z"/>
</svg>"""

TW_FLAG = """<svg viewBox="0 0 24 16" xmlns="http://www.w3.org/2000/svg">
<rect width="24" height="16" fill="#FE0000"/>
<rect width="12" height="8" fill="#000095"/>
<circle cx="6" cy="4" r="2" fill="#FFFFFF"/>
</svg>"""

PH_FLAG = """<svg viewBox="0 0 24 16" xmlns="http://www.w3.org/2000/svg">
<rect width="24" height="8" fill="#0038A8"/>
<rect y="8" width="24" height="8" fill="#CE1126"/>
<path fill="#FFFFFF" d="M0 0L9 8L0 16Z"/>
<circle cx="3" cy="8" r="1.4" fill="#FCD116"/>
</svg>"""

PL_FLAG = _hstripes("#FFFFFF", "#DC143C")

GE_FLAG = """<svg viewBox="0 0 24 16" xmlns="http://www.w3.org/2000/svg">
<rect width="24" height="16" fill="#FFFFFF"/>
<rect x="10.8" width="2.4" height="16" fill="#FF0000"/>
<rect y="6.8" width="24" height="2.4" fill="#FF0000"/>
</svg>"""

AM_FLAG = _hstripes("#D90012", "#0033A0", "#F2A800")
AZ_FLAG = _hstripes("#00B5E2", "#EF3340", "#00AF66")

RS_FLAG = _hstripes("#C6363C", "#0C4076", "#FFFFFF")

XK_FLAG = """<svg viewBox="0 0 24 16" xmlns="http://www.w3.org/2000/svg">
<rect width="24" height="16" fill="#244AA5"/>
<path fill="#FFFFFF" d="M9 5l0.4 1.2h1.3l-1 0.8 0.4 1.2-1.1-0.8-1.1 0.8 0.4-1.2-1-0.8h1.3z"/>
<path fill="#FFFFFF" d="M13 5l0.4 1.2h1.3l-1 0.8 0.4 1.2-1.1-0.8-1.1 0.8 0.4-1.2-1-0.8h1.3z"/>
</svg>"""

VE_FLAG = _hstripes("#FFCC00", "#00247D", "#CF142B")

CO_FLAG = """<svg viewBox="0 0 24 16" xmlns="http://www.w3.org/2000/svg">
<rect width="24" height="8" fill="#FCD116"/>
<rect y="8" width="24" height="4" fill="#003893"/>
<rect y="12" width="24" height="4" fill="#CE1126"/>
</svg>"""

MX_FLAG = """<svg viewBox="0 0 24 16" xmlns="http://www.w3.org/2000/svg">
<rect width="8" height="16" fill="#006847"/>
<rect x="8" width="8" height="16" fill="#FFFFFF"/>
<rect x="16" width="8" height="16" fill="#CE1126"/>
<circle cx="12" cy="8" r="1.6" fill="#006847"/>
</svg>"""

HT_FLAG = _hstripes("#00209F", "#D21034")

EC_FLAG = """<svg viewBox="0 0 24 16" xmlns="http://www.w3.org/2000/svg">
<rect width="24" height="8" fill="#FFDD00"/>
<rect y="8" width="24" height="4" fill="#034EA2"/>
<rect y="12" width="24" height="4" fill="#ED1C24"/>
</svg>"""

FLAGS = {
    "us": US_FLAG, "ca": CA_FLAG, "ru": RU_FLAG, "ua": UA_FLAG,
    "il": IL_FLAG, "ps": PS_FLAG, "sd": SD_FLAG, "mm": MM_FLAG,
    "gb": GB_FLAG, "fr": FR_FLAG, "de": DE_FLAG, "cn": CN_FLAG,
    "in": IN_FLAG, "jp": JP_FLAG, "sy": SY_FLAG, "iq": IQ_FLAG,
    "ir": IR_FLAG, "ye": YE_FLAG, "lb": LB_FLAG, "sa": SA_FLAG,
    "tr": TR_FLAG, "ss": SS_FLAG, "et": ET_FLAG, "so": SO_FLAG,
    "cd": CD_FLAG, "ml": ML_FLAG, "ne": NE_FLAG, "ng": NG_FLAG,
    "ly": LY_FLAG, "td": TD_FLAG, "cf": CF_FLAG, "mz": MZ_FLAG,
    "cm": CM_FLAG, "af": AF_FLAG, "pk": PK_FLAG, "kp": KP_FLAG,
    "kr": KR_FLAG, "tw": TW_FLAG, "ph": PH_FLAG, "pl": PL_FLAG,
    "ge": GE_FLAG, "am": AM_FLAG, "az": AZ_FLAG, "rs": RS_FLAG,
    "xk": XK_FLAG, "ve": VE_FLAG, "co": CO_FLAG, "mx": MX_FLAG,
    "ht": HT_FLAG, "ec": EC_FLAG,
}


def flag_for(country: str) -> str:
    return FLAGS[country]
