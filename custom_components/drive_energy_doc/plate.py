"""Kennzeichen als SVG (für die Vorschau in den Dialogen). Reine Funktionen, ohne Home-Assistant-Abhängigkeit.

Je Land gibt es die typischen Merkmale: Farbe des Schilds und der Schrift, Länderstreifen mit Europa-Ring oder Flagge, Plaketten und Wappen zwischen den Teilen
(Deutschland, Österreich, Belgien), die Schreibweise (Schweiz „SG·197 052“, Großbritannien „AB12 EHJ“, Belgien „1-ABC-003“) und die Schweizer Flagge und das Kantonswappen.
"""

from __future__ import annotations

import math
import re
from xml.sax.saxutils import escape

YELLOW = {"NL", "GB", "LU"}   # gelbes Schild
NO_STRIP = {"CH", "US", "LI", "RU"}  # ohne blauen Länderstreifen
RED_TEXT = {"BE": "#b01c2e"}   # rote Schrift (Belgien mit rotem Rand)
BORDER = {"BE": "#b01c2e", "DK": "#c8102e"}   # roter Rand (Belgien, Dänemark)
SILVER = {"DK"}   # dünner silberner Sicherheitsstreifen hinter dem blauen Streifen
SPLIT = {"BE": "char", "DE": "token", "AT": "token", "IT": "token", "HR": "token", "SK": "token", "SI": "token", "LI": "token"}   # nach diesem Teil sitzen Plaketten bzw. das Wappen
INSERT_W = {"BE": 24, "DE": 26, "AT": 26, "IT": 22, "HR": 26, "SK": 28, "SI": 26, "LI": 26}
RIGHT_STRIP = {"IT", "FR"}   # zweiter blauer Streifen rechts (Italien: Jahr im goldenen Kreis, Provinz)
STRIP_COLOR = {"AL": "#b8141b"}   # Streifen in Landesfarbe statt Blau (Albanien)
FLAG_STRIP = {"GB": "uk", "NO": "no", "UA": "ua", "RS": "rs"}   # Flagge im Streifen statt des Europa-Rings
REGION_BOX = {"RU"}   # Regionsnummer in eigenem Feld rechts (mit Kürzel und Flagge)
EU = {"AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE"}  # Europa-Ring (12 Sterne) im Streifen
EXAMPLES = {
    "AL": "AA 123 AA", "AD": "AB 1234", "AT": "W 12345 A", "BY": "1234 AB-7", "BE": "1-ABC-123", "BA": "A12-E-345", "BG": "CA 1234 AB",
    "HR": "ZG 1234-AB", "CY": "ABC 123", "CZ": "1AB 2345", "DK": "AF 54554", "EE": "123 ABC", "FI": "ABC-123", "FR": "AB-123-CD",
    "DE": "B-AB 1234", "GR": "ABC-1234", "HU": "ABC-123", "IS": "ABC 12", "IE": "191-D-12345", "IT": "AB 123CD", "XK": "01-123-AB",
    "LV": "AB-1234", "LI": "FL 12345", "LT": "ABC 123", "LU": "AB 1234", "MT": "ABC 123", "MD": "C AB 123", "MC": "MC 1234",
    "ME": "PG 123-45", "NL": "AB-123-C", "MK": "SK 1234 AB", "NO": "AB 12345", "PL": "WA 12345", "PT": "12-AB-34", "RO": "B 123 ABC",
    "RU": "A123BC 77", "SM": "A 1234", "RS": "BG 123-AB", "SK": "BA-123AB", "SI": "LJ AB-123", "ES": "1234 BCD", "SE": "ABC 123",
    "CH": "ZH 123 456", "TR": "34 ABC 123", "UA": "AA 1234 BB", "GB": "AB12 CDE", "VA": "SCV 1234", "US": "ABC-1234",
}


# Länder außerhalb Europas: (Länderkennung am Fahrzeug, Name, Beispiel) und Aussehen des Schilds (Grund, Schrift, Randfarbe, Streifen links mit Kürzel, Band oben mit Text)
# Nach dem Gedächtnis gezeichnet, vereinfacht (Schriftzeichen wie Kanji, Hangul oder Thai fehlen).
_W = "#ffffff"
_K = "#111111"
_B = "#1f3f8f"
WORLD = {
    "CA": ("CDN", "Kanada", "ABCD 123", {"fg": _B}),
    "MX": ("MEX", "Mexiko", "ABC-12-34", {}),
    "BR": ("BR", "Brasilien", "ABC1D23", {"top": ("BRASIL", "#003399")}),
    "AR": ("RA", "Argentinien", "AB 123 CD", {"top": ("ARGENTINA", "#2a6ebb")}),
    "CL": ("RCH", "Chile", "BBCD 12", {}),
    "CO": ("CO", "Kolumbien", "ABC 123", {"bg": "#f7c600"}),
    "PE": ("PE", "Peru", "ABC-123", {}),
    "VE": ("YV", "Venezuela", "AB 123 CD", {}),
    "UY": ("ROU", "Uruguay", "ABC 1234", {}),
    "EC": ("EC", "Ecuador", "ABC-1234", {}),
    "JP": ("J", "Japan", "300 A 12-34", {"fg": "#1b7a3d", "border": "#1b7a3d"}),
    "CN": ("CHN", "China", "A 12345", {"bg": "#1f4fb5", "fg": "#ffffff", "border": "#e8e8e8"}),
    "KR": ("ROK", "Südkorea", "12 A 3456", {}),
    "IN": ("IND", "Indien", "MH 12 AB 1234", {"strip": "#1a3a8c"}),
    "ID": ("RI", "Indonesien", "B 1234 ABC", {"bg": _K, "fg": "#ffffff", "border": "#d0d0d0"}),
    "MY": ("MAL", "Malaysia", "WXY 1234", {"bg": _K, "fg": "#ffffff", "border": "#d0d0d0"}),
    "SG": ("SGP", "Singapur", "SBA 1234 A", {"bg": _K, "fg": "#ffffff", "border": "#d0d0d0"}),
    "TH": ("T", "Thailand", "1AB 1234", {}),
    "VN": ("VN", "Vietnam", "30A-123.45", {}),
    "PH": ("RP", "Philippinen", "ABC 1234", {}),
    "HK": ("HK", "Hongkong", "AB 1234", {"bg": "#f7c600"}),
    "TW": ("RC", "Taiwan", "ABC-1234", {}),
    "PK": ("PK", "Pakistan", "ABC-123", {}),
    "BD": ("BD", "Bangladesch", "DHAKA 12-3456", {}),
    "LK": ("CL", "Sri Lanka", "CAB-1234", {"bg": "#f7c600"}),
    "IL": ("IL", "Israel", "12-345-67", {"bg": "#f7c600", "strip": "#0a3a9a"}),
    "SA": ("KSA", "Saudi-Arabien", "ABC 1234", {}),
    "AE": ("UAE", "Vereinigte Arabische Emirate", "A 12345", {}),
    "QA": ("Q", "Katar", "123456", {"bg": "#7b1d3a", "fg": "#ffffff", "border": "#e8e8e8"}),
    "KW": ("KWT", "Kuwait", "12 3456", {}),
    "IR": ("IR", "Iran", "12 A 345 67", {"strip": "#0b5ca8"}),
    "IQ": ("IRQ", "Irak", "12345 A", {}),
    "JO": ("HKJ", "Jordanien", "12-34567", {}),
    "KZ": ("KZ", "Kasachstan", "123 ABC 02", {"strip": "#00a3b7"}),
    "UZ": ("UZ", "Usbekistan", "01 A 123 BC", {"strip": "#1a3a8c"}),
    "GE": ("GE", "Georgien", "AB-123-CD", {"strip": "#1a3a8c"}),
    "AM": ("AM", "Armenien", "12 AB 345", {"strip": "#1a3a8c"}),
    "AZ": ("AZ", "Aserbaidschan", "10-AB-123", {"strip": "#1a3a8c"}),
    "ZA": ("ZA", "Südafrika", "CA 123-456", {}),
    "EG": ("ET", "Ägypten", "ABC 1234", {}),
    "MA": ("MA", "Marokko", "12345-A-6", {}),
    "TN": ("TN", "Tunesien", "123 TUN 4567", {}),
    "DZ": ("DZ", "Algerien", "12345 123 16", {}),
    "NG": ("WAN", "Nigeria", "ABC-123 DE", {}),
    "KE": ("EAK", "Kenia", "KAA 123A", {"bg": "#f7c600"}),
    "GH": ("GH", "Ghana", "GR 1234-20", {}),
    "ET": ("ETH", "Äthiopien", "A 12345", {}),
    "TZ": ("EAT", "Tansania", "T 123 ABC", {}),
    "SN": ("SN", "Senegal", "AB-123-CD", {}),
    "AU": ("AUS", "Australien", "ABC 123", {"fg": _B}),
    "NZ": ("NZ", "Neuseeland", "ABC123", {}),
}
WORLD_CODES = {cc: v[0] for cc, v in WORLD.items()}
WORLD_NAMES = {cc: v[1] for cc, v in WORLD.items()}
EXAMPLES.update({cc: v[2] for cc, v in WORLD.items()})


def clean_text(text: str | None) -> str:
    """Nur Buchstaben, Ziffern, Leerzeichen, Punkt und Bindestrich, höchstens 14 Zeichen."""
    return re.sub(r"[^A-Za-z0-9ÄÖÜäöüß .\-]", "", text or "").strip().upper()[:14]


GENERIC_FORMATS = {   # Land: (Muster ohne Trennzeichen, Schreibweise)
    "SE": (r"([A-Z]{3})(\d{3})", "{0} {1}"), "NO": (r"([A-Z]{2})(\d{4,5})", "{0} {1}"), "DK": (r"([A-Z]{2})(\d{5})", "{0} {1}"),
    "FI": (r"([A-Z]{3})(\d{3})", "{0}-{1}"), "HU": (r"([A-Z]{3})(\d{3})", "{0}-{1}"), "PT": (r"(\d{2})([A-Z]{2})(\d{2})", "{0}-{1}-{2}"),
    "CZ": (r"(\d[A-Z]{2})(\d{4})", "{0} {1}"), "SK": (r"([A-Z]{2})(\d{3}[A-Z]{2})", "{0}-{1}"), "HR": (r"([A-Z]{2})(\d{3,4})([A-Z]{2})", "{0} {1}-{2}"),
    "BG": (r"([A-Z]{1,2})(\d{4})([A-Z]{2})", "{0} {1} {2}"), "LU": (r"([A-Z]{2})(\d{4})", "{0} {1}"), "EE": (r"(\d{3})([A-Z]{3})", "{0} {1}"),
    "LT": (r"([A-Z]{3})(\d{3})", "{0} {1}"), "RU": (r"([A-Z]\d{3}[A-Z]{2})(\d{2,3})", "{0} {1}"),
}


def format_text(country: str, text: str) -> str:
    """Schreibweise des Landes: Schweiz „SG·197 052“ (Kanton, Punkt, Nummer in Dreiergruppen), Großbritannien „AB12 EHJ“, Belgien „1-ABC-003“, Frankreich „AB-123-CD“, Italien „AB 123CD“ mit Wappen und zweitem Streifen, Spanien „1234 BCD“."""
    t = re.sub(r"[ .\-·]", "", text)
    if country == "CH":
        m = re.fullmatch(r"([A-Z]{2})(\d{1,6})", t)
        if m:
            d = m.group(2)
            groups = []
            while d:
                groups.insert(0, d[-3:])
                d = d[:-3]
            return f"{m.group(1)}·{' '.join(groups)}"
    elif country == "GB":
        if re.fullmatch(r"[A-Z]{2}\d{2}[A-Z]{3}", t):
            return f"{t[:4]} {t[4:]}"
    elif country == "BE":
        m = re.fullmatch(r"(\d)([A-Z]{3})(\d{3})", t)
        if m:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    elif country == "FR":
        m = re.fullmatch(r"([A-Z]{2})(\d{3})([A-Z]{2})", t)
        if m:
            return "-".join(m.groups())
    elif country == "IT":
        m = re.fullmatch(r"([A-Z]{2})(\d{3})([A-Z]{2})", t)
        if m:
            return f"{m.group(1)} {m.group(2)}{m.group(3)}"   # „AA 111AA“, in der Mitte das Staatswappen
    elif country == "ES":
        m = re.fullmatch(r"(\d{4})([A-Z]{3})", t)
        if m:
            return " ".join(m.groups())
    else:
        spec = GENERIC_FORMATS.get(country)
        if spec:
            m = re.fullmatch(spec[0], t)
            if m:
                return spec[1].format(*m.groups())
    return text


def _star(cx: float, cy: float, outer: float, inner: float, fill: str) -> str:
    pts = []
    for j in range(10):
        b = math.radians(j * 36 - 90)
        rad = outer if j % 2 == 0 else inner
        pts.append(f"{cx + rad * math.cos(b):.2f},{cy + rad * math.sin(b):.2f}")
    return f'<polygon points="{" ".join(pts)}" fill="{fill}"/>'


def _union_jack(x: float, y: float, w: float, h: float) -> str:
    """Flagge des Vereinigten Königreichs (ohne Clip-Pfad: das verschachtelte SVG beschneidet selbst)."""
    return (
        f'<svg x="{x}" y="{y}" width="{w}" height="{h}" viewBox="0 0 60 30" preserveAspectRatio="none">'
        '<rect width="60" height="30" fill="#012169"/>'
        '<path d="M0 0L60 30M60 0L0 30" stroke="#fff" stroke-width="6"/>'
        '<path d="M0 0L60 30M60 0L0 30" stroke="#c8102e" stroke-width="2"/>'
        '<path d="M30 0V30M0 15H60" stroke="#fff" stroke-width="10"/>'
        '<path d="M30 0V30M0 15H60" stroke="#c8102e" stroke-width="6"/></svg>'
    )


def _flag(name: str, x: float, y: float, w: float, h: float) -> str:
    """Kleine Flagge im Länderstreifen."""
    head = f'<svg x="{x}" y="{y}" width="{w}" height="{h}" viewBox="0 0 22 16" preserveAspectRatio="none">'
    if name == "uk":
        return _union_jack(x, y, w, h)
    if name == "no":
        return head + '<rect width="22" height="16" fill="#ba0c2f"/><rect x="6" width="4" height="16" fill="#fff"/><rect y="6" width="22" height="4" fill="#fff"/><rect x="7" width="2" height="16" fill="#00205b"/><rect y="7" width="22" height="2" fill="#00205b"/></svg>'
    if name == "ua":
        return head + '<rect width="22" height="8" fill="#0057b7"/><rect y="8" width="22" height="8" fill="#ffd700"/></svg>'
    if name == "rs":
        return head + '<rect width="22" height="5.4" fill="#c6363c"/><rect y="5.3" width="22" height="5.4" fill="#0c4076"/><rect y="10.6" width="22" height="5.4" fill="#fff"/></svg>'
    return ""


def _swiss_flag(x: float, y: float) -> str:
    """Schweizer Flagge als kleines Schild links auf dem Kennzeichen."""
    return (
        f'<rect x="{x}" y="{y}" width="22" height="26" rx="3" fill="#da291c"/>'
        f'<rect x="{x + 9}" y="{y + 5}" width="4" height="16" fill="#fff"/><rect x="{x + 3}" y="{y + 11}" width="16" height="4" fill="#fff"/>'
    )


def _canton_shield(x: float, y: float) -> str:
    """Kantonswappen rechts (neutrales Schild; das echte Wappen hängt vom Kanton ab)."""
    return (
        f'<path d="M{x} {y}h22v15c0 7-5 11-11 13-6-2-11-6-11-13z" fill="#e3e3e3" stroke="#444" stroke-width="1.6"/>'
        f'<path d="M{x + 11} {y + 4}v17" stroke="#6a6a6a" stroke-width="1.6"/>'
    )


def _insert(country: str, x: float, h: int) -> str:
    """Plaketten bzw. Wappen zwischen den Teilen des Kennzeichens."""
    if country == "DE":   # oben Wappen der Zulassungsstelle, unten Prüfplakette
        return (
            f'<circle cx="{x + 13}" cy="14" r="7" fill="#d9d9d9" stroke="#111" stroke-width="1.2"/><circle cx="{x + 13}" cy="14" r="2.6" fill="#555"/>'
            f'<circle cx="{x + 13}" cy="31.5" r="6" fill="#f2b705" stroke="#111" stroke-width="1.2"/>'
        )
    if country == "HR":   # Wappen Kroatiens: rot-weißes Schachbrett
        cells = "".join(f'<rect x="{x + 5 + i * 4}" y="{11 + j * 4}" width="4" height="4" fill="{"#d71920" if (i + j) % 2 == 0 else "#fff"}"/>' for i in range(4) for j in range(5))
        return cells + f'<rect x="{x + 5}" y="11" width="16" height="20" fill="none" stroke="#111" stroke-width="1.2"/>'
    if country == "SK":   # Wappen der Slowakei im blauen Kreis
        return (
            f'<circle cx="{x + 14}" cy="22" r="10" fill="#1c3f94"/><rect x="{x + 9.5}" y="15.5" width="9" height="11" rx="1.5" fill="#d71920"/>'
            f'<rect x="{x + 13.2}" y="17" width="1.6" height="9" fill="#fff"/><rect x="{x + 11}" y="19.5" width="6" height="1.4" fill="#fff"/><rect x="{x + 11.6}" y="22.4" width="4.8" height="1.4" fill="#fff"/>'
        )
    if country == "SI":   # Wappen Sloweniens: blauer Schild mit Berg
        return (
            f'<path d="M{x + 5} 9h16v13c0 6-4 9-8 11-4-2-8-5-8-11z" fill="#1c3f94" stroke="#111" stroke-width="1.2"/>'
            f'<path d="M{x + 8} 21l3.5-6 2.5 3.5 2-3.5 3 6z" fill="#fff"/><path d="M{x + 8.5} 25h9" stroke="#d71920" stroke-width="1.6"/>'
        )
    if country == "LI":   # Wappen Liechtensteins: blau-rot
        return (
            f'<path d="M{x + 5} 9h16v13c0 6-4 9-8 11-4-2-8-5-8-11z" fill="#d71920" stroke="#111" stroke-width="1.2"/>'
            f'<path d="M{x + 5.6} 9.6h14.8v8.2H{x + 5.6}z" fill="#1c3f94"/><circle cx="{x + 13}" cy="14" r="2.4" fill="#f2c200"/>'
        )
    if country == "IT":   # kleines Staatswappen zwischen Buchstaben und Ziffern
        return f'<circle cx="{x + 11}" cy="22" r="5.5" fill="none" stroke="#111" stroke-width="1.3"/><circle cx="{x + 11}" cy="22" r="2.2" fill="#111"/>'
    if country == "AT":   # Bundesland-Wappen (rot-weiß-rot)
        return (
            f'<rect x="{x + 5}" y="9" width="16" height="9" fill="#c8102e"/><rect x="{x + 5}" y="18" width="16" height="8" fill="#fff"/><rect x="{x + 5}" y="26" width="16" height="9" fill="#c8102e"/>'
            f'<rect x="{x + 5}" y="9" width="16" height="26" fill="none" stroke="#111" stroke-width="1.2"/>'
        )
    if country == "BE":   # kleines Wappen und Plakette in Rot
        red = RED_TEXT["BE"]
        return (
            f'<circle cx="{x + 12}" cy="14" r="6.5" fill="none" stroke="{red}" stroke-width="1.6"/>'
            f'<text x="{x + 12}" y="17.5" text-anchor="middle" font-family="Arial,Helvetica,sans-serif" font-weight="700" font-size="9" fill="{red}">V</text>'
            f'<rect x="{x + 6}" y="25" width="12" height="10" fill="#f3f3f3" stroke="#999" stroke-width="1"/>'
        )
    return ""


def _split(country: str, text: str) -> tuple[str, str]:
    """Text vor und nach der Stelle, an der Plaketten oder das Wappen sitzen (ohne Einfügestelle: alles in einem Teil)."""
    mode = SPLIT.get(country)
    if mode == "char" and len(text) > 1:
        return text[0], text[1:]
    if mode == "token":
        m = re.match(r"^([A-ZÄÖÜ]{1,3})[ \-]+(.+)$", text)
        if m:
            return m.group(1), m.group(2)
    return text, ""


def svg(code: str, country: str, text: str) -> str:
    country = (country or "DE").upper()
    text = clean_text(text) or EXAMPLES.get(country, "ABC 123")
    text = format_text(country, text)
    code = re.sub(r"[^A-Z]", "", (code or "").upper())[:4]
    wd = WORLD.get(country, (None, None, None, {}))[3] if country in WORLD else None
    strip = (28 if wd.get("strip") else 0) if wd is not None else (0 if country in NO_STRIP else 28)
    top = wd.get("top") if wd else None
    ch = country == "CH"
    left = 34 if ch else 0    # Schweizer Flagge links
    right = 34 if ch else 0   # Kantonswappen rechts
    pad = 14 if strip else (8 if ch else 16)
    silver = 6 if country in SILVER else 0
    rstrip = 28 if country in RIGHT_STRIP else 0
    cw = 17 if ch else 16
    head, tail = _split(country, text)
    region = ""
    if country in REGION_BOX and " " in text:
        head, region = text.rsplit(" ", 1)
        tail = ""
    ins = INSERT_W.get(country, 0) if tail else 0
    rbox = 52 if region else 0
    tw_head = max(18, len(head) * cw) if tail else max(40, len(head) * cw)
    tw_tail = max(18, len(tail) * cw) if tail else 0
    w = strip + silver + left + pad + tw_head + ins + tw_tail + (6 if tail else 0) + right + rstrip + rbox + 14
    h, r = 44, 7
    bg = "#f7c600" if country in YELLOW else "#ffffff"
    border = BORDER.get(country, "#111")
    fg = RED_TEXT.get(country, "#111")
    if wd is not None:
        bg, fg, border = wd.get("bg", bg), wd.get("fg", fg), wd.get("border", "#111")
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
        f'<rect x="1.5" y="1.5" width="{w - 3}" height="{h - 3}" rx="{r}" fill="{bg}" stroke="{border}" stroke-width="3"/>',
    ]
    if strip:
        ring = country in EU and wd is None
        fl = FLAG_STRIP.get(country)
        flag = bool(fl)
        parts.append(f'<path d="M{r + 1.5} 1.5H{strip + 1.5}V{h - 1.5}H{r + 1.5}a{r} {r} 0 0 1-{r}-{r}V{r + 1.5}a{r} {r} 0 0 1 {r}-{r}z" fill="{"#0a3a9a" if fl == "uk" else (wd.get("strip") if wd else None) or STRIP_COLOR.get(country, "#003399")}"/>')
        if flag:   # Flagge über der Länderkennung
            parts.append(_flag(fl, 4.5, 8, 21, 13))
        elif ring:  # Europa-Ring: zwölf fünfzackige gelbe Sterne im Kreis über der Länderkennung
            rcx, rcy = strip / 2 + 1.5, 13.5
            for k in range(12):
                a = math.radians(k * 30 - 90)
                parts.append(_star(rcx + 7.4 * math.cos(a), rcy + 7.4 * math.sin(a), 2.2, 0.9, "#ffcc00"))
        low = ring or flag
        parts.append(f'<text x="{strip / 2 + 1.5}" y="{36 if low else 29}" text-anchor="middle" font-family="Arial,Helvetica,sans-serif" font-weight="{700 if flag else 400}" font-size="{12 if len(code) == 1 else (10 if len(code) == 2 else 8)}" fill="#fff">{escape(code)}</text>')
    if top:   # Band oben (Mercosur-Schilder: Brasilien, Argentinien) mit Ländername
        parts.append(f'<path d="M{r + 1.5} 1.5H{w - r - 1.5}a{r} {r} 0 0 1 {r} {r}V13H1.5V{r + 1.5}a{r} {r} 0 0 1 {r}-{r}z" fill="{top[1]}"/>')
        parts.append(f'<text x="{w / 2}" y="10.5" text-anchor="middle" font-family="Arial,Helvetica,sans-serif" font-weight="700" font-size="8" fill="#fff">{escape(top[0])}</text>')
    if rstrip:   # rechter Streifen: Jahr im goldenen Kreis und Provinz (Platzhalter „00“ und „AA“)
        rx = w - 1.5 - rstrip
        parts.append(f'<path d="M{rx} 1.5H{w - r - 1.5}a{r} {r} 0 0 1 {r} {r}V{h - r - 1.5}a{r} {r} 0 0 1-{r} {r}H{rx}z" fill="#003399"/>')
        if country == "IT":
            parts.append(f'<circle cx="{rx + rstrip / 2}" cy="15" r="9" fill="none" stroke="#f0b400" stroke-width="1.6"/>')
            parts.append(f'<text x="{rx + rstrip / 2}" y="19" text-anchor="middle" font-family="Arial,Helvetica,sans-serif" font-weight="700" font-size="11" fill="#f0b400">00</text>')
            parts.append(f'<text x="{rx + rstrip / 2}" y="38" text-anchor="middle" font-family="Arial,Helvetica,sans-serif" font-weight="700" font-size="14" fill="#fff">AA</text>')
        else:   # Frankreich: Regionswappen (Platzhalter) und Departementnummer
            parts.append(f'<rect x="{rx + rstrip / 2 - 6}" y="8" width="12" height="9" rx="2" fill="#fff" opacity="0.9"/>')
            parts.append(f'<text x="{rx + rstrip / 2}" y="35" text-anchor="middle" font-family="Arial,Helvetica,sans-serif" font-weight="700" font-size="14" fill="#fff">00</text>')
    if region:   # Russland: Trennlinie, Regionsnummer, „RUS“ und kleine Flagge
        bx = w - 1.5 - rbox
        parts.append(f'<rect x="{bx}" y="6" width="2" height="{h - 12}" fill="#111"/>')
        parts.append(f'<text x="{bx + rbox / 2 + 1}" y="27" text-anchor="middle" font-family="Arial,Helvetica,sans-serif" font-weight="700" font-size="20" fill="#111">{escape(region)}</text>')
        parts.append(f'<text x="{bx + 12}" y="38" text-anchor="middle" font-family="Arial,Helvetica,sans-serif" font-weight="700" font-size="8" fill="#111">RUS</text>')
        parts.append(f'<rect x="{bx + 20}" y="31" width="14" height="2.4" fill="#fff" stroke="#999" stroke-width="0.4"/><rect x="{bx + 20}" y="33.4" width="14" height="2.4" fill="#0039a6"/><rect x="{bx + 20}" y="35.8" width="14" height="2.4" fill="#d52b1e"/>')
    if silver:   # silberner Streifen mit leichtem Verlauf
        parts.append(f'<rect x="{strip + 1.5}" y="1.5" width="{silver}" height="{h - 3}" fill="#c9ccd2"/><rect x="{strip + 1.5 + silver / 2}" y="1.5" width="1" height="{h - 3}" fill="#e6e8ec"/>')
    if ch:
        parts.append(_swiss_flag(6, 9))
        parts.append(_canton_shield(w - 6 - 22 - 8, 8))
    fsize = 26 if country == "GB" else (21 if top else 24)
    x0 = strip + silver + left + pad
    txt = f'font-family="Arial,Helvetica,sans-serif" font-weight="700" font-size="{fsize}" fill="{fg}" stroke="{fg}" stroke-width="1.0" stroke-linejoin="round"'
    parts.append(f'<text x="{x0}" y="{36 if top else 31}" {txt} textLength="{tw_head}" lengthAdjust="spacing">{escape(head).replace("·", "&#183;")}</text>')
    if tail:
        parts.append(_insert(country, x0 + tw_head + 3, h))
        parts.append(f'<text x="{x0 + tw_head + ins + 6}" y="31" {txt} textLength="{tw_tail}" lengthAdjust="spacing">{escape(tail)}</text>')
    parts.append("</svg>")
    return "".join(parts)
