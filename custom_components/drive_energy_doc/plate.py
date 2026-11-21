"""Kennzeichen als SVG (für die Vorschau in den Dialogen). Reine Funktionen, ohne Home-Assistant-Abhängigkeit."""

from __future__ import annotations

import math
import re
from xml.sax.saxutils import escape

YELLOW = {"NL", "GB"}   # gelbes Schild
NO_STRIP = {"CH", "US"}  # ohne blauen Länderstreifen
EU = {"AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE"}  # Europa-Ring (12 Sterne) im Streifen
EXAMPLES = {
    "AL": "AA 123 AA", "AD": "AB 1234", "AT": "W 12345 A", "BY": "1234 AB-7", "BE": "1-ABC-123", "BA": "A12-E-345", "BG": "CA 1234 AB",
    "HR": "ZG 1234-AB", "CY": "ABC 123", "CZ": "1AB 2345", "DK": "AB 12 345", "EE": "123 ABC", "FI": "ABC-123", "FR": "AB-123-CD",
    "DE": "B-AB 1234", "GR": "ABC-1234", "HU": "ABC-123", "IS": "ABC 12", "IE": "191-D-12345", "IT": "AB 123 CD", "XK": "01-123-AB",
    "LV": "AB-1234", "LI": "FL 12345", "LT": "ABC 123", "LU": "AB 1234", "MT": "ABC 123", "MD": "C AB 123", "MC": "MC 1234",
    "ME": "PG 123-45", "NL": "AB-123-C", "MK": "SK 1234 AB", "NO": "AB 12345", "PL": "WA 12345", "PT": "12-AB-34", "RO": "B 123 ABC",
    "RU": "A123BC 77", "SM": "A 1234", "RS": "BG 123-AB", "SK": "BA-123AB", "SI": "LJ AB-123", "ES": "1234 BCD", "SE": "ABC 123",
    "CH": "ZH 123456", "TR": "34 ABC 123", "UA": "AA 1234 BB", "GB": "AB12 CDE", "VA": "SCV 1234", "US": "ABC-1234",
}


def clean_text(text: str | None) -> str:
    """Nur Buchstaben, Ziffern, Leerzeichen, Punkt und Bindestrich, höchstens 14 Zeichen."""
    return re.sub(r"[^A-Za-z0-9ÄÖÜäöüß .\-]", "", text or "").strip().upper()[:14]


def svg(code: str, country: str, text: str) -> str:
    country = (country or "DE").upper()
    text = clean_text(text) or EXAMPLES.get(country, "ABC 123")
    code = re.sub(r"[^A-Z]", "", (code or "").upper())[:4]
    strip = 0 if country in NO_STRIP else 28
    pad = 14 if strip else 16
    tw = max(40, len(text) * 16)
    w = strip + pad + tw + 14
    h, r = 44, 7
    bg = "#f7c600" if country in YELLOW else "#ffffff"
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
        f'<rect x="1.5" y="1.5" width="{w - 3}" height="{h - 3}" rx="{r}" fill="{bg}" stroke="#111" stroke-width="3"/>',
    ]
    if strip:
        ring = country in EU
        parts.append(f'<path d="M{r + 1.5} 1.5H{strip + 1.5}V{h - 1.5}H{r + 1.5}a{r} {r} 0 0 1-{r}-{r}V{r + 1.5}a{r} {r} 0 0 1 {r}-{r}z" fill="#003399"/>')
        if ring:  # Europa-Ring: zwölf fünfzackige gelbe Sterne im Kreis über der Länderkennung
            rcx, rcy = strip / 2 + 1.5, 13.5
            for k in range(12):
                a = math.radians(k * 30 - 90)
                sx, sy = rcx + 7.4 * math.cos(a), rcy + 7.4 * math.sin(a)
                pts = []
                for j in range(10):
                    b = math.radians(j * 36 - 90)
                    rad = 2.2 if j % 2 == 0 else 0.9
                    pts.append(f"{sx + rad * math.cos(b):.2f},{sy + rad * math.sin(b):.2f}")
                parts.append(f'<polygon points="{" ".join(pts)}" fill="#ffcc00"/>')
        parts.append(f'<text x="{strip / 2 + 1.5}" y="{36 if ring else 29}" text-anchor="middle" font-family="Arial,Helvetica,sans-serif" font-weight="400" font-size="{12 if len(code) == 1 else (10 if len(code) == 2 else 8)}" fill="#fff">{escape(code)}</text>')
    parts.append(
        f'<text x="{strip + pad}" y="31" font-family="Arial,Helvetica,sans-serif" font-weight="700" font-size="24" '
        f'textLength="{tw}" lengthAdjust="spacing" fill="#111" stroke="#111" stroke-width="1.0" stroke-linejoin="round">{escape(text)}</text>'
    )
    parts.append("</svg>")
    return "".join(parts)
