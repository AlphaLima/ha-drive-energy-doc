# Test images for a plug-in hybrid · Test-Bilder für einen Plug-in-Hybrid

**DE:** 10 zusammenpassende Vorgänge (4× Tanken, 6× Laden) für einen **Plug-in-Hybrid**, alles **frei erfundene Dummydaten** (Stationen, Adressen, Preise, Kilometerstände). Zu jedem Vorgang gibt es drei Bilder: die **Anzeige der Säule** (Zapfsäule mit Siebensegment-Display bzw. Ladesäule), den **Beleg** (Kundenbeleg bzw. Ladebeleg) und das **Tacho-Foto** mit dem Gesamt-Kilometerstand. Die Kilometerstände steigen von 12 040 auf 13 118 km, Datum, Uhrzeit, Menge, Preis und Summe passen zwischen Säule und Beleg zusammen. Die Bilder sind absichtlich schief fotografiert, teils verwackelt, mit wechselndem Licht, Knitter und leicht ausgeblichenem Papier, bleiben aber lesbar. Jede Datei trägt eine Aufnahmezeit (EXIF). Die Sollwerte stehen in `sollwerte_hybrid.csv`.

So testest du es: Fahrzeug mit **Plug-in-Hybrid** anlegen, dann die Bilder im Panel hochladen (mehrere auf einmal sind möglich) oder an den Telegram-Bot schicken. Erwartet werden 4 Kraftstoff-Einträge (l) und 6 Strom-Einträge (kWh) mit getrenntem Verbrauch. Die Dateien heißen `NN_tank_*` (Kraftstoff) bzw. `NN_lade_*` (Strom).

**EN:** 10 matching events (4 × refuelling, 6 × charging) for a **plug-in hybrid**, all **entirely fictional dummy data** (stations, addresses, prices, mileages). Each event has three pictures: the **pump or charger display**, the **receipt**, and an **odometer photo** with the total mileage. Mileage rises from 12,040 to 13,118 km, and date, time, quantity, price and total match between the display and the receipt. The pictures are deliberately taken at an angle, partly shaky, with varying light, creases and slightly faded paper, but stay readable. Every file carries a capture time (EXIF). Expected values are in `sollwerte_hybrid.csv`.

To try it: create a vehicle with **Plug-in hybrid** ticked, then upload the images in the panel (several at once is fine) or send them to the Telegram bot. You should get 4 fuel entries (l) and 6 electricity entries (kWh) with separate consumption. Files are named `NN_tank_*` (fuel) and `NN_lade_*` (electricity).

| # | Date | Type | Station | Quantity | Unit price | Total | Odometer |
|---|---|---|---|---|---|---|---|
| 01 | 02.10.2026 | Fuel E10 | Nordlicht Energie | 38.42 l | 1.759 | 67.58 | 12 040 |
| 02 | 05.10.2026 | Electricity | StromPunkt Sued | 14.2 kWh | 0.49 | 6.96 | 12 118 |
| 03 | 09.10.2026 | Electricity | LadeRiese Nord | 11.8 kWh | 0.52 | 6.14 | 12 205 |
| 04 | 14.10.2026 | Fuel E10 | Tank Express Mitte | 21.60 l | 1.789 | 38.64 | 12 390 |
| 05 | 16.10.2026 | Electricity | VoltHof Ladepark | 13.5 kWh | 0.49 | 6.62 | 12 470 |
| 06 | 20.10.2026 | Electricity | StromPunkt Sued | 12.9 kWh | 0.55 | 7.10 | 12 551 |
| 07 | 25.10.2026 | Fuel E10 | Landstrom Tankstelle | 17.90 l | 1.769 | 31.67 | 12 760 |
| 08 | 28.10.2026 | Electricity | LadeRiese Nord | 14.8 kWh | 0.52 | 7.70 | 12 843 |
| 09 | 03.11.2026 | Electricity | VoltHof Ladepark | 12.4 kWh | 0.49 | 6.08 | 12 931 |
| 10 | 08.11.2026 | Fuel E10 | Nordlicht Energie | 28.35 l | 1.779 | 50.43 | 13 118 |

## More from all over Europe · Mehr aus ganz Europa

**DE:** Zusätzlich 10 Bilder (`eu_*`): **5 Säulen-Anzeigen (LCD)** aus FR, IT, PL (Zapfsäulen) und CH, SE (Ladesäulen) sowie **5 Quittungen** aus ES, CZ, GB (Tanken) und NL, DK (Laden), jeweils in **Landessprache und Landeswährung** (EUR, PLN, CZK, GBP, DKK, CHF, SEK), mit passender Steuer und passendem Dezimalzeichen (Punkt bei GB und CH). Sie hängen **nicht** an den 10 Vorgängen oben, sondern sind einzelne Bilder, auch zum Testen der Währungsumrechnung (die App rechnet zum EZB-Tageskurs des Belegdatums in Euro um und schreibt Original und Kurs in die Notiz). Sollwerte: `sollwerte_hybrid_europa.csv`.

**EN:** 10 more pictures (`eu_*`): **5 pump or charger LCD displays** from FR, IT, PL (pumps) and CH, SE (chargers), plus **5 receipts** from ES, CZ, GB (fuel) and NL, DK (charging), each in the **local language and currency** (EUR, PLN, CZK, GBP, DKK, CHF, SEK) with the matching tax and decimal separator (dot for GB and CH). They are **not** tied to the 10 events above but stand alone, also for testing the currency conversion (the app converts to euro at the ECB daily rate of the receipt date and writes the original and the rate into the note). Expected values: `sollwerte_hybrid_europa.csv`.

| File | Country | Type | Quantity | Price | Total |
|---|---|---|---|---|---|
| `eu_lcd_01_FR_tank` | FR | Display, fuel | 41.2 l | 1.729 EUR/l | 71.23 EUR |
| `eu_lcd_02_IT_tank` | IT | Display, fuel | 33.8 l | 1.839 EUR/l | 62.16 EUR |
| `eu_lcd_03_PL_tank` | PL | Display, fuel | 29.6 l | 6.39 PLN/l | 189.14 PLN |
| `eu_lcd_04_CH_lade` | CH | Display, charging | 18.4 kWh | 0.48 CHF/kWh | 8.83 CHF |
| `eu_lcd_05_SE_lade` | SE | Display, charging | 20.1 kWh | 3.90 SEK/kWh | 78.39 SEK |
| `eu_beleg_01_ES_tank` | ES | Receipt, fuel | 36.8 l | 1.559 EUR/l | 57.37 EUR |
| `eu_beleg_02_CZ_tank` | CZ | Receipt, fuel | 30.5 l | 36.90 CZK/l | 1125.45 CZK |
| `eu_beleg_03_GB_tank` | GB | Receipt, fuel | 28.4 l | 1.469 GBP/l | 41.72 GBP |
| `eu_beleg_04_NL_lade` | NL | Receipt, charging | 17.3 kWh | 0.39 EUR/kWh | 6.75 EUR |
| `eu_beleg_05_DK_lade` | DK | Receipt, charging | 15.2 kWh | 3.25 DKK/kWh | 49.40 DKK |
