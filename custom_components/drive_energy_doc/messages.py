"""Mehrsprachige Texte (Bot-Antworten, Panel) und Kommando-Stichwörter.

Ein Wörterbuch je Sprache liegt in ``frontend/i18n/<sprache>.json``. Schlüssel ist der deutsche Text (Deutsch braucht daher
keine Datei); fehlt ein Eintrag, wird Englisch und zuletzt der deutsche Text genommen. Platzhalter sind ``{0}``, ``{1}`` …
Spezielle Schlüssel ``kw.*`` enthalten Stichwörter (durch ``|`` getrennt). Für das Erkennen von Kommandos zählen die Stichwörter
ALLER Sprachen zusammen, ein Fahrer kann also in seiner Sprache schreiben, egal in welcher Sprache der Bot antwortet.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

_LOGGER = logging.getLogger(__name__)
DIR = Path(__file__).parent / "frontend" / "i18n"
_CACHE: dict[str, dict[str, str]] = {}

# Eingebaute Stichwörter (Deutsch und Englisch), gelten immer
_BUILTIN = {
    "help": "?|h|help|hilfe|/help|/hilfe|/start",
    "extra": "zubehör|zubehoer|zub|extra|z|e|x|accessory|acc",
    "yes": "ja|j|yes|y|ok",
    "no": "nein|n|no",
    "new": "neu|new",
    "photo": "zusatz|additional",
    "doc": "doku|dokumentation|nur dokumentation|doc|documentation",
    "del": "löschen|loeschen|delete|del",
    "km": "km|kilometer|kilometerstand|tacho|odometer|mileage|miles|mi",
    "items": "adblue=AdBlue=l|ad blue=AdBlue=l|ad-blue=AdBlue=l|motoröl=Motoröl=l|motoroel=Motoröl=l|öl=Öl=l|oel=Öl=l|oil=Oil=l|"
             "engine oil=Engine oil=l|scheibenwischer=Scheibenwischer|wischer=Scheibenwischer|wipers=Wipers|"
             "scheibenwasser=Scheibenwasser=l|washer fluid=Washer fluid=l|frostschutz=Frostschutz=l|antifreeze=Antifreeze=l",
}


def preload() -> None:
    """Alle Wörterbücher einlesen (blockierend: im Executor aufrufen)."""
    if not DIR.is_dir():
        return
    for f in DIR.glob("*.json"):
        try:
            _CACHE[f.stem] = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError) as err:
            _LOGGER.warning("Sprachdatei %s nicht lesbar: %s", f.name, err)


def languages() -> list[str]:
    """Verfügbare Sprachcodes (Deutsch ist immer dabei)."""
    return sorted({"de", *_CACHE})


_ALIAS = {"no": "nb", "nn": "nb", "sh": "hr", "iw": "he"}


def base(lang: str | None) -> str:
    code = (lang or "en").lower().replace("_", "-").split("-")[0]
    return _ALIAS.get(code, code)


def tr(lang: str | None, key: str, *args) -> str:
    """Text in der Sprache ``lang``; ``{0}``, ``{1}`` … werden durch ``args`` ersetzt."""
    code = base(lang)
    text = None
    if code != "de":
        text = (_CACHE.get(code) or {}).get(key) or (_CACHE.get("en") or {}).get(key)
    text = text or key
    for i, a in enumerate(args):
        text = text.replace("{%d}" % i, str(a))
    return text


def _all(kind: str) -> list[str]:
    out = [s for s in _BUILTIN.get(kind, "").split("|") if s]
    for d in _CACHE.values():
        out += [s.strip() for s in (d.get("kw." + kind) or "").split("|") if s.strip()]
    return out


def keywords(kind: str) -> set[str]:
    """Stichwörter (klein geschrieben) aus allen Sprachen."""
    return {s.lower() for s in _all(kind)}


def items() -> dict[str, tuple[str, str]]:
    """Kurzwörter für Zubehör: Wort -> (Anzeigename, Einheit)."""
    out: dict[str, tuple[str, str]] = {}
    for entry in _all("items"):
        parts = entry.split("=")
        if len(parts) >= 2 and parts[0].strip():
            out[parts[0].strip().lower()] = (parts[1].strip(), parts[2].strip() if len(parts) > 2 else "")
    return out


def decimal(lang: str | None) -> str:
    """Dezimaltrenner der Sprache (Standard Komma)."""
    code = base(lang)
    if code == "de":
        return ","
    return ((_CACHE.get(code) or {}).get("kw.decimal") or ("." if code == "en" else ",")).strip() or ","


# Name des Panels in der Seitenleiste (Home Assistant erlaubt dort nur einen Text für alle Benutzer: es gilt die Systemsprache)
PANEL_TITLE = {
    "de": "Tankbuch", "en": "Fuel log", "fr": "Carnet de carburant", "es": "Registro de repostajes", "it": "Registro rifornimenti", "nl": "Tankboekje",
    "pt": "Registo de abastecimentos", "pl": "Dziennik tankowań", "cs": "Kniha tankování", "sk": "Kniha tankovania", "sl": "Dnevnik točenja",
    "hr": "Dnevnik točenja", "sr": "Дневник точења", "bs": "Dnevnik točenja", "mk": "Дневник на полнење", "bg": "Дневник на зареждането",
    "uk": "Журнал заправок", "be": "Журнал запраўкі", "ru": "Журнал заправок", "ro": "Jurnal alimentări", "hu": "Tankolási napló",
    "el": "Ημερολόγιο καυσίμων", "tr": "Yakıt defteri", "sq": "Ditari i karburantit", "lt": "Degalų žurnalas", "lv": "Degvielas žurnāls",
    "et": "Tankimispäevik", "fi": "Tankkauspäiväkirja", "sv": "Tankbok", "da": "Tankbog", "nb": "Tankbok", "is": "Eldsneytisbók",
    "ga": "Dialann breosla", "mt": "Reġistru tal-fuel", "lb": "Tankbuch", "ca": "Registre de combustible",
}


def panel_title(lang: str | None) -> str:
    """Seitenleisten-Name in der Sprache ``lang`` (Standard Englisch)."""
    return PANEL_TITLE.get(base(lang), PANEL_TITLE["en"])
