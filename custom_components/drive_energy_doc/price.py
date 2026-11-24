"""Spritpreis-Anbieter. Alles optional: ohne Anbieter reicht der Beleg.

Ohne Schlüssel: Österreich (E-Control), Frankreich (prix-carburants, data.gouv), Spanien (MINETUR), Italien (MIMIT Osservaprezzi).
Mit persönlichem, kostenlosem Schlüssel: Deutschland (Tankerkönig). Weitere Länder: Anbieter in PROVIDERS ergänzen.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import math
import ssl
import time
from typing import Any

from aiohttp import ClientError, ClientTimeout

from .const import STATION_RADIUS_KM

_LOGGER = logging.getLogger(__name__)
UA = {"User-Agent": "HomeAssistant-Drive Energy Doc/0.1"}
TO = ClientTimeout(total=20)


CACHE_TTL = 1800   # Spanien und Italien liefern ganze Landesdateien (einige MB): höchstens alle 30 Minuten laden
_CACHE: dict[str, tuple[float, list]] = {}


def _km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p = math.pi / 180
    a = 0.5 - math.cos((lat2 - lat1) * p) / 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * (1 - math.cos((lon2 - lon1) * p)) / 2
    return 12742 * math.asin(math.sqrt(a))


def _num(x) -> float | None:
    try:
        v = float(str(x).replace(",", ".").strip())
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def _nearest(stations: list[dict], lat: float, lon: float, fuel: str) -> dict[str, Any] | None:
    """Nächste Station im Umkreis, die für die Kraftstoffart einen Preis hat."""
    best, best_d = None, STATION_RADIUS_KM
    for st in stations:
        if st["prices"].get(fuel) is None:
            continue
        d = _km(lat, lon, st["lat"], st["lon"])
        if d <= best_d:
            best, best_d = st, d
    if not best:
        return None
    return {"station_id": best["id"], "station": best["brand"], "unit_price": best["prices"][fuel], "address": best["address"]}


def _parse_es(raw: bytes) -> list[dict]:
    out = []
    for s in json.loads(raw).get("ListaEESSPrecio") or []:
        lat, lon = _num(str(s.get("Latitud", "")).replace("-", "")), _num(str(s.get("Longitud (WGS84)", "")).replace("-", ""))
        if lat is None or lon is None:
            continue
        lon = -lon if str(s.get("Longitud (WGS84)", "")).strip().startswith("-") else lon
        lat = -lat if str(s.get("Latitud", "")).strip().startswith("-") else lat
        e5, e10 = _num(s.get("Precio Gasolina 95 E5")), _num(s.get("Precio Gasolina 95 E10"))
        out.append({"id": str(s.get("IDEESS")), "lat": lat, "lon": lon, "brand": (s.get("Rótulo") or "").strip() or None,
                    "address": ", ".join(x for x in ((s.get("Dirección") or "").strip(), f"{s.get('C.P.') or ''} {(s.get('Localidad') or '').strip()}".strip()) if x),
                    "prices": {"diesel": _num(s.get("Precio Gasoleo A")), "e5": e5 or e10, "e10": e10 or e5}})
    return out


def _es_ssl() -> ssl.SSLContext:
    """TLS für den Server des spanischen Ministeriums: er akzeptiert nur ältere Verschlüsselung (Sicherheitsstufe 1). Gilt nur für diese Abfrage öffentlicher Preisdaten."""
    ctx = ssl.create_default_context()
    ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
    return ctx


async def _minetur_es(session, key, lat, lon, fuel):
    """Spanien: Ministerium (MINETUR/MITECO), alle Tankstellen als JSON, stündlich aktualisiert; hier nach Koordinaten gefiltert."""
    now = time.time()
    cached = _CACHE.get("es")
    if not cached or now - cached[0] > CACHE_TTL:
        url = "https://sedeaplicaciones.minetur.gob.es/ServiciosRESTCarburantes/PreciosCarburantes/EstacionesTerrestres/"
        ctx = await asyncio.get_running_loop().run_in_executor(None, _es_ssl)
        async with session.get(url, timeout=ClientTimeout(total=90), headers={"User-Agent": "Mozilla/5.0 (compatible; HomeAssistant)", "Accept": "application/json"}, ssl=ctx) as r:
            raw = await r.read()
        _CACHE["es"] = cached = (now, await asyncio.get_running_loop().run_in_executor(None, _parse_es, raw))
    return _nearest(cached[1], lat, lon, fuel)


def _parse_it(anag: str, prices: str) -> list[dict]:
    info = {}
    for row in csv.reader(io.StringIO(anag), delimiter="|"):
        if len(row) < 10 or not row[0].strip().isdigit():
            continue
        la, lo = _num(row[8]), _num(row[9])
        if la is None or lo is None:
            continue
        info[row[0]] = {"id": row[0], "lat": la, "lon": lo, "brand": (row[2] or "").strip() or None,
                        "address": ", ".join(x for x in ((row[5] or "").strip(), f"{(row[6] or '').strip()} ({(row[7] or '').strip()})") if x), "prices": {}, "_self": {}}
    for row in csv.reader(io.StringIO(prices), delimiter="|"):
        if len(row) < 4 or row[0] not in info:
            continue
        kind = {"Benzina": "petrol", "Gasolio": "diesel"}.get(row[1].strip())
        price = _num(row[2])
        if not kind or price is None:
            continue
        st = info[row[0]]
        selfservice = row[3].strip() == "1"
        # Self-Service-Preis bevorzugen (gängige Zahlweise), sonst der Preis mit Bedienung
        if selfservice or kind not in st["_self"]:
            st["prices"][kind] = price
            if selfservice:
                st["_self"][kind] = True
    out = []
    for st in info.values():
        st["prices"] = {"diesel": st["prices"].get("diesel"), "e5": st["prices"].get("petrol"), "e10": st["prices"].get("petrol")}
        if any(st["prices"].values()):
            out.append(st)
    return out


async def _mimit_it(session, key, lat, lon, fuel):
    """Italien: MIMIT Osservaprezzi (Open Data, CSV): Stationsliste und Preise; hier nach Koordinaten gefiltert."""
    now = time.time()
    cached = _CACHE.get("it")
    if not cached or now - cached[0] > CACHE_TTL:
        base = "https://www.mimit.gov.it/images/exportCSV/"
        texts = []
        for name in ("anagrafica_impianti_attivi.csv", "prezzo_alle_8.csv"):
            async with session.get(base + name, timeout=ClientTimeout(total=90), headers=UA) as r:
                texts.append((await r.read()).decode("utf-8", "replace"))
        _CACHE["it"] = cached = (now, await asyncio.get_running_loop().run_in_executor(None, _parse_it, texts[0], texts[1]))
    return _nearest(cached[1], lat, lon, fuel)


async def _tankerkoenig(session, key, lat, lon, fuel):
    if not key:
        return None
    params = {"lat": lat, "lng": lon, "rad": 2, "sort": "dist", "type": fuel, "apikey": key}
    async with session.get("https://creativecommons.tankerkoenig.de/json/list.php", params=params, timeout=TO, headers=UA) as r:
        data = await r.json(content_type=None)
    if not data.get("ok"):
        _LOGGER.warning("Tankerkönig-Fehler: %s", data.get("message"))
        return None
    for st in data.get("stations") or []:
        if st.get("price") and st.get("dist", 99) <= STATION_RADIUS_KM:
            street = f"{st.get('street') or ''} {st.get('houseNumber') or ''}".strip()
            return {"station_id": st.get("id"), "station": st.get("brand") or st.get("name"), "unit_price": float(st["price"]),
                    "address": ", ".join(x for x in (street, f"{st.get('postCode') or ''} {st.get('place') or ''}".strip()) if x)}
    return None


async def _econtrol_at(session, key, lat, lon, fuel):
    ft = "DIE" if fuel == "diesel" else "SUP"
    params = {"latitude": lat, "longitude": lon, "fuelType": ft, "includeClosed": "false"}
    async with session.get("https://api.e-control.at/sprit/1.0/search/gas-stations/by-address", params=params, timeout=TO, headers=UA) as r:
        data = await r.json(content_type=None)
    for st in data or []:
        price = next((p["amount"] for p in st.get("prices", []) if p.get("fuelType") == ft and p.get("amount")), None)
        if price and st.get("distance", 99) <= STATION_RADIUS_KM:
            loc = st.get("location") or {}
            return {"station_id": str(st.get("id")), "station": st.get("name"), "unit_price": float(price),
                    "address": ", ".join(x for x in (loc.get("address"), f"{loc.get('postalCode') or ''} {loc.get('city') or ''}".strip()) if x)}
    return None


async def _prix_fr(session, key, lat, lon, fuel):
    field = {"diesel": "gazole_prix", "e5": "sp95_prix", "e10": "e10_prix"}[fuel]
    point = f"geom'POINT({lon} {lat})'"
    params = {"where": f"within_distance(geom, {point}, {int(STATION_RADIUS_KM * 1000)}m) AND {field} IS NOT NULL", "order_by": f"distance(geom, {point})", "limit": 1,
              "select": f"id,adresse,ville,cp,{field}"}
    url = "https://data.economie.gouv.fr/api/explore/v2.1/catalog/datasets/prix-des-carburants-en-france-flux-instantane-v2/records"
    async with session.get(url, params=params, timeout=TO, headers=UA) as r:
        data = await r.json(content_type=None)
    for st in data.get("results") or []:
        return {"station_id": str(st["id"]), "station": None, "unit_price": float(st[field]), "address": f"{st.get('adresse') or ''}, {st.get('cp') or ''} {st.get('ville') or ''}".strip(", ")}
    return None


PROVIDERS = {"tankerkoenig": _tankerkoenig, "econtrol_at": _econtrol_at, "prix_fr": _prix_fr, "minetur_es": _minetur_es, "mimit_it": _mimit_it}
BY_COUNTRY = {"DE": "tankerkoenig", "AT": "econtrol_at", "FR": "prix_fr", "ES": "minetur_es", "IT": "mimit_it"}


def resolve_provider(setting: str | None, country: str | None, key: str | None) -> str | None:
    if setting in PROVIDERS:
        return setting
    if setting == "none":
        return None
    prov = BY_COUNTRY.get((country or "").upper())  # "auto"
    return None if prov == "tankerkoenig" and not key else prov


async def lookup(session, provider: str | None, key: str | None, lat: float, lon: float, fuel: str) -> dict[str, Any] | None:
    if not provider or fuel not in ("diesel", "e5", "e10"):   # Autogas (LPG) u. a.: die Preisdienste kennen nur diese Sorten, der Preis kommt dann vom Beleg
        return None
    try:
        return await PROVIDERS[provider](session, key, lat, lon, fuel)
    except (ClientError, TimeoutError, ValueError, KeyError) as err:
        _LOGGER.warning("Preisabfrage (%s) fehlgeschlagen: %s", provider, err)
        return None
