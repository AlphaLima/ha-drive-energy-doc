"""Spritpreis-Anbieter. Alles optional: ohne Anbieter reicht der Beleg.

Ohne Schlüssel: Österreich (E-Control), Frankreich (prix-carburants, data.gouv). Mit persönlichem,
kostenlosem Schlüssel: Deutschland (Tankerkönig). Weitere Länder: Anbieter in PROVIDERS ergänzen.
"""

from __future__ import annotations

import logging
from typing import Any

from aiohttp import ClientError, ClientTimeout

from .const import STATION_RADIUS_KM

_LOGGER = logging.getLogger(__name__)
UA = {"User-Agent": "HomeAssistant-Drive Energy Doc/0.1"}
TO = ClientTimeout(total=20)


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


PROVIDERS = {"tankerkoenig": _tankerkoenig, "econtrol_at": _econtrol_at, "prix_fr": _prix_fr}
BY_COUNTRY = {"DE": "tankerkoenig", "AT": "econtrol_at", "FR": "prix_fr"}


def resolve_provider(setting: str | None, country: str | None, key: str | None) -> str | None:
    if setting in PROVIDERS:
        return setting
    if setting == "none":
        return None
    prov = BY_COUNTRY.get((country or "").upper())  # "auto"
    return None if prov == "tankerkoenig" and not key else prov


async def lookup(session, provider: str | None, key: str | None, lat: float, lon: float, fuel: str) -> dict[str, Any] | None:
    if not provider:
        return None
    try:
        return await PROVIDERS[provider](session, key, lat, lon, fuel)
    except (ClientError, TimeoutError, ValueError, KeyError) as err:
        _LOGGER.warning("Preisabfrage (%s) fehlgeschlagen: %s", provider, err)
        return None
