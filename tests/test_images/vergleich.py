#!/usr/bin/env python3
"""Vergleicht den CSV-Export von Drive Energy Doc mit den Sollwerten der Testbilder.

Aufruf:   python vergleich.py export.csv
          (der Export: Panel, Knopf „CSV“; die Sollwerte liegen in sollwerte.csv und sollwerte_11-20.csv neben diesem Skript)

Compares the CSV export of Drive Energy Doc with the expected values of the test images.
Usage:    python vergleich.py export.csv

Gezählt wird je Paar (Zuordnung über das Datum):
  Menge, Preis, Summe  -> müssen stimmen (Toleranz 0,01)
  Kilometerstand       -> ok (Tacho- oder Belegstand), leer (zulässig: im Zweifel wird der Stand weggelassen) oder FALSCH (der eigentliche Fehler)
Nur Standardbibliothek, getestet mit Python 3.9+.
"""
import csv
import pathlib
import sys

HERE = pathlib.Path(__file__).parent
# Spalten des Exports (Reihenfolge ist in allen Sprachen gleich, nur die Kopfzeile wird übersetzt)
C_NR, C_DATE, C_TIME, C_KM, C_QTY, C_PRICE, C_TOTAL = 0, 5, 6, 7, 14, 16, 17


def num(s):
    s = (s or "").strip().replace(" ", "")
    if not s:
        return None
    if "," in s and "." in s:   # 1.234,5 oder 1,234.5
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    else:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def read_csv(path, delimiter=";"):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.reader(fh, delimiter=delimiter))


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    export = read_csv(argv[1])[1:]
    by_date = {}
    for r in export:
        if len(r) > C_TOTAL:
            by_date.setdefault(r[C_DATE].strip(), []).append(r)
    expected = []
    for f in ("sollwerte.csv", "sollwerte_11-20.csv"):
        with open(HERE / f, encoding="utf-8-sig", newline="") as fh:
            expected += list(csv.DictReader(fh, delimiter=";"))

    ok = missing = bad_km = empty_km = bad_other = 0
    print(f"{'Nr':>2} {'Datum':10}  Menge  Preis  Summe  km")
    for e in expected:
        rows = by_date.get(e["datum"])
        nr = int(e["nr"])
        if not rows:
            print(f"{nr:>2} {e['datum']:10}  FEHLT (kein Eintrag an diesem Tag)")
            missing += 1
            continue
        r = rows[0]
        q, p, t, km = num(r[C_QTY]), num(r[C_PRICE]), num(r[C_TOTAL]), num(r[C_KM])
        eq, ep, et = num(e["menge"]), num(e["preis_pro_einheit"]), num(e["summe_eur"])
        good = {num(e["km_tacho"]), num(e.get("km_beleg"))} - {None}
        m = lambda a, b: "ok" if a is not None and abs(a - b) <= 0.011 else "FALSCH"   # noqa: E731
        cq, cp, ct = m(q, eq), m(p, ep), m(t, et)
        if km is None:
            ck = "leer"
            empty_km += 1
        elif km in good:
            ck = "ok"
        else:
            ck = f"FALSCH ({km:.0f})"
            bad_km += 1
        bad_other += sum(1 for c in (cq, cp, ct) if c != "ok")
        if cq == cp == ct == "ok" and not ck.startswith("FALSCH"):
            ok += 1
        print(f"{nr:>2} {e['datum']:10}  {cq:5}  {cp:5}  {ct:5}  {ck}")

    n = len(expected)
    print()
    print(f"Paare: {n} | vollständig richtig: {ok} | ohne Eintrag: {missing} | Kilometerstand leer (zulässig): {empty_km} | Kilometerstand FALSCH: {bad_km} | falsche Menge/Preis/Summe: {bad_other}")
    print("Ergebnis:", "BESTANDEN (kein falscher Wert)" if not (bad_km or bad_other or missing) else "Auffälligkeiten, siehe Zeilen oben")
    return 0 if not (bad_km or bad_other or missing) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
