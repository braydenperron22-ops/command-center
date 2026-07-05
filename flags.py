"""Inline SVG flags — emoji flags don't render on Windows (shows 'US'/'CA'
letter codes instead of the actual flag), so these are drawn directly."""

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

FLAGS = {"us": US_FLAG, "ca": CA_FLAG}


def flag_for(country: str) -> str:
    return FLAGS[country]
