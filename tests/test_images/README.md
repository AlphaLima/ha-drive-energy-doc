# Testbilder / Test images

**Deutsch** · [English below](#english)

## Deutsch

20 **frei erfundene** Foto-Paare zum Ausprobieren von Drive Energy Doc. Es sind keine echten Belege, Orte, Tankstellen, Kennzeichen oder Kilometerstände.
Die Bilder wurden mit einem Skript gezeichnet und danach wie Handyfotos verfremdet (Perspektive, Licht, Unschärfe, Rauschen, Spiegelungen).

### Was ist drin

- `NN_beleg.jpg`: ein Tankbeleg (Kundenbeleg einer Tankstelle) mit Station, Anschrift, Datum, Uhrzeit, Menge, Preis und Summe.
- `NN_tacho.jpg`: ein Foto des Kombiinstruments mit dem Kilometerzähler. Beide Fotos eines Paares (gleiche Nummer) gehören zu **einem** Tankvorgang.
- `sollwerte.csv` (Nr. 1 bis 10) und `sollwerte_11-20.csv` (Nr. 11 bis 20): die richtigen Werte zu jedem Paar. Spalten: Nummer, Datum, Uhrzeit, Station, Ort, Kraftstoff, Menge, Einheit, Preis pro Einheit, Summe, `km_tacho` (Stand auf dem Tacho-Foto), `km_beleg` (Stand auf dem Beleg, leer = steht nicht auf dem Beleg), Lesbarkeit von Beleg und Tacho, Hinweis zur Aufnahme.
- Ein Benzin-Auto (Super E10, etwa 7 l/100 km). Datum und Kilometerstand steigen von Nr. 1 bis Nr. 20: **26.08.2026 bis 30.10.2026**, **61 240 bis 71 704 km**. Alle Termine liegen in der Vergangenheit.

### Aufnahmezeit (EXIF) statt Dateiname

Dateinamen sagen nichts: Kameras vergeben sie beliebig, und die Zuordnung darf sich nicht darauf verlassen. Deshalb tragen alle 40 Bilder die **Aufnahmezeit im EXIF** (`DateTimeOriginal`): beim Beleg die Zeit auf dem Beleg, beim Tacho-Foto **3 Minuten davor**. Es sind keine Geodaten und keine Gerätedaten enthalten. Die Nummern `NN` im Dateinamen dienen nur dir zum Sortieren.

Das Panel verarbeitet mehrere Fotos **chronologisch nach Aufnahmezeit** (ohne EXIF nach Änderungsdatum der Datei), egal wie die Dateien heißen oder in welcher Reihenfolge du sie auswählst. Bilder, die über Telegram oder WhatsApp kommen, verlieren ihr EXIF; dort gilt die Zeit der Nachricht, schicke solche Paare also zeitnah.

### Die Paare

Lesbarkeit: gut, mittel, schwer, sehr schwer (Beleg / Tacho).

| Nr. | Datum, Uhrzeit | Station | Kraftstoff | Menge | €/Einheit | Summe € | km Tacho | km Beleg | Lesbarkeit | Hinweis |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 26.08.2026 07:42 | Nordring Energie | Super E10 | 42,18 l | 1,879 | 79,26 | 61240 | 61228 | gut / gut | Frontal, gutes Licht |
| 2 | 30.08.2026 18:15 | Rheintal Tank GmbH | Super E10 | 38,64 l | 1,859 | 71,83 | 61834 | 61809 | gut / gut | leicht gedreht, weicher Schatten |
| 3 | 03.09.2026 12:03 | Autohof Wesel Sued | Super E10 | 44,05 l | 1,899 | 83,65 | 62386 | 62378 | mittel / mittel | starke Perspektive von der Seite, Blendung im Tacho |
| 4 | 06.09.2026 21:47 | Delta Tankstelle | Super E10 | 35,72 l | 1,919 | 68,55 | 62989 | 62958 | schwer / schwer | Nachtaufnahme, dunkel, starkes Rauschen |
| 5 | 10.09.2026 09:20 | Markt Energie | Super E10 | 40,30 l | 1,869 | 75,32 | 63499 | 63495 | mittel / schwer | Bewegungsunschaerfe |
| 6 | 13.09.2026 16:31 | Grenzland Tank | Super E10 | 43,86 l | 1,889 | 82,85 | 64059 | 64041 | mittel / mittel | Beleg zerknittert, Spiegelungen im Tacho |
| 7 | 15.09.2026 10:26 | Eifel Energie | Motoroel 5W-30 1 l | 1,00 l | 11,990 | 11,99 | 64199 | – | gut / gut | Kassenbon fuer 1 l Motoroel (Zubehoer, ohne Kilometerstand), Tacho zeigt den Stand beim Kauf |
| 8 | 18.09.2026 13:58 | Eifel Energie | Super E10 | 41,55 l | 1,909 | 79,32 | 64668 | 64628 | schwer / mittel | Beleg klein im Bild, Tacho unten angeschnitten |
| 9 | 21.09.2026 19:12 | Sonnenhof Tank | Super E10 | 39,20 l | 1,899 | 74,44 | 65253 | 65238 | schwer / schwer | Ueberbelichtung durch Gegenlicht |
| 10 | 24.09.2026 06:55 | Fruehschicht Tank 24 | Super E10 | 45,10 l | 1,939 | 87,45 | 65813 | 65791 | schwer / schwer | Thermodruck verblasst und Beleg quer, Tacho dunkel und schief |
| 11 | 28.09.2026 08:12 | Nordring Energie | Super E10 | 42,60 l | 1,929 | 82,18 | 66448 | – | gut / mittel | Spiegelungsstreifen ueber dem km-Zaehler, leichte Unschaerfe |
| 12 | 01.10.2026 17:48 | Rheintal Tank GmbH | Super E10 | 39,85 l | 1,899 | 75,68 | 67056 | – | mittel / schwer | dunkel, starkes Rauschen, deutliche Unschaerfe |
| 13 | 05.10.2026 12:30 | Autohof Wesel Sued | Super E10 | 44,90 l | 1,869 | 83,92 | 67609 | – | mittel / schwer | extremer Winkel, Bokeh, Lenkrad verdeckt Teile |
| 14 | 08.10.2026 20:05 | Delta Tankstelle | Super E10 | 36,20 l | 1,889 | 68,38 | 68241 | – | schwer / schwer | lange Bewegungsunschaerfe, Beleg dunkel und verrauscht |
| 15 | 12.10.2026 09:40 | Markt Energie | Super E10 | 41,75 l | 1,859 | 77,61 | 68766 | – | gut / schwer | beschlagene Scheibe: milchig, kontrastarm |
| 16 | 15.10.2026 15:22 | Grenzland Tank | Super E10 | 43,30 l | 1,919 | 83,09 | 69346 | – | mittel / schwer | Instrument klein im Bild (Entfernung), verrauscht |
| 17 | 19.10.2026 11:05 | Sonnenhof Tank | Super E10 | 38,40 l | 1,899 | 72,92 | 69956 | – | schwer / schwer | Gegenlicht, Spiegelung der Windschutzscheibe, ueberbelichtet |
| 18 | 22.10.2026 16:50 | Eifel Energie | Super E10 | 45,00 l | 1,879 | 84,56 | 70505 | – | schwer / sehr schwer | Nacht, nur Hintergrundbeleuchtung, sehr dunkel |
| 19 | 26.10.2026 08:25 | Fruehschicht Tank 24 | Super E10 | 40,15 l | 1,909 | 76,65 | 71130 | – | mittel / sehr schwer | stark gedreht, angeschnitten, unscharf |
| 20 | 30.10.2026 18:30 | Autohof Wesel Sued | Super E10 | 42,85 l | 1,929 | 82,66 | 71704 | – | schwer / sehr schwer | Kombination aus Unschaerfe, Beschlag, Spiegelung und wenig Licht |

- **Nr. 1 bis 10:** Der Beleg nennt einen **Kilometerstand**, der leicht vom Tacho abweicht (der Tacho wurde kurz davor fotografiert). Die Lesbarkeit reicht von gut bis schwer.
- **Nr. 11 bis 20:** Der Beleg hat **keinen** Kilometerstand. Der Stand steht nur auf dem Tacho-Foto, und diese Fotos sind deutlich schlechter lesbar (Spiegelung, Beschlag, Bewegungsunschärfe, Nacht).
- **Nr. 7** ist kein Tanken: ein Kassenbon über 1 Liter Motoröl (Zubehör). Beim einzelnen Senden dazu die Bildunterschrift `öl` angeben; im Stapel ohne Bildunterschrift wird daraus ein Eintrag mit „1,00 l“, den du von Hand als Zubehör korrigierst.

### So testest du

1. **Alles auf einmal:** im Panel den Foto-Knopf drücken und alle 40 Bilder auswählen. Sie werden nach Aufnahmezeit sortiert und nacheinander gelesen. Der Fortschrittsdialog zeigt alle Fotos, **Abbrechen** stoppt den Stapel. Am Ende kommt eine Übersicht mit Warnungen.
2. **Paarweise:** ein Tacho-Foto und den Beleg dazu, in beliebiger Reihenfolge. Der erste legt den Eintrag an, der zweite schließt sich an.
3. **Per Telegram oder WhatsApp:** Paare **der Reihe nach** und zeitnah senden (EXIF fehlt dort).
4. **Vorher leeren:** am besten mit einem Fahrzeug ohne Einträge testen, sonst mischen sich die Testdaten mit echten.

### Selbsttest mit Auswertung

Damit du das Ergebnis nicht Zeile für Zeile nachrechnen musst, liegt `vergleich.py` bei (nur Python, keine Zusatzpakete):

1. Alle Testbilder wie oben hochladen.
2. Im Panel den **CSV-Export** herunterladen.
3. Im Ordner `tests/test_images` ausführen: `python vergleich.py export.csv`

Das Skript ordnet jedes Paar über das Datum zu und prüft Menge, Preis und Summe. Beim Kilometerstand unterscheidet es **ok** (Tacho- oder Belegstand), **leer** (zulässig, im Zweifel wird er weggelassen) und **FALSCH** (der eigentliche Fehler). Am Ende steht „BESTANDEN“, wenn kein falscher Wert und kein fehlender Eintrag gefunden wurde.

### Was du erwarten darfst

- **20 Einträge** (der Ölbon als eigener Eintrag), nach Datum sortiert und nummeriert, mit Station, Menge, Preis und Summe vom Beleg.
- **Kilometerstand:** bei Nr. 1 bis 10 vom Beleg oder Tacho, bei Nr. 11 bis 20 nur vom Tacho. Ist das Tacho-Foto nicht sicher lesbar (vor allem Nr. 12 bis 20), bleibt der Kilometerstand **leer**. Das ist gewollt: **im Zweifel wird der Stand weggelassen** und nicht geraten. Ein *falscher* Stand wäre der Fehler, ein leerer nicht.
- **Keine Rückfragen mitten im Stapel.** Auffälligkeiten (z. B. ein unplausibler Verbrauch) stehen am Ende in der Übersicht.
- Die Verbrauchswerte (l/100 km) liegen bei etwa 5,7 bis 8,2 (so sind die Testdaten gebaut), sobald zwei Kilometerstände nebeneinander bekannt sind.

Die Bilder dürfen frei verwendet werden (Lizenz wie das Projekt, MIT).

## English

20 **entirely fictional** photo pairs for trying out Drive Energy Doc. No real receipts, places, stations, plates or odometer readings.
The images were drawn by a script and then degraded like phone photos (perspective, light, blur, noise, reflections).

### What is in it

- `NN_beleg.jpg`: a fuel receipt (customer copy) with station, address, date, time, quantity, price and total.
- `NN_tacho.jpg`: a photo of the instrument cluster with the odometer. Both photos of a pair (same number) belong to **one** refuelling.
- `sollwerte.csv` (no. 1 to 10) and `sollwerte_11-20.csv` (no. 11 to 20): the correct values for each pair. Columns: number, date, time, station, place, fuel, quantity, unit, price per unit, total, `km_tacho` (reading on the odometer photo), `km_beleg` (reading on the receipt, empty = not printed), readability of receipt and odometer, note on the shot.
- One petrol car (Super E10, about 7 l/100 km). Date and mileage increase from no. 1 to no. 20: **26 Aug 2026 to 30 Oct 2026**, **61,240 to 71,704 km**. All dates are in the past.

### Capture time (EXIF) instead of file name

File names say nothing: cameras assign them arbitrarily, and the matching must not rely on them. All 40 images therefore carry the **capture time in EXIF** (`DateTimeOriginal`): for the receipt the time printed on it, for the odometer photo **3 minutes earlier**. There is no geodata and no device data. The numbers `NN` in the file names are only there to help you sort.

The panel processes several photos **chronologically by capture time** (without EXIF by the file's modified date), whatever the files are called and in whatever order you select them. Images that arrive via Telegram or WhatsApp lose their EXIF; there the time of the message counts, so send such pairs promptly.

### The pairs

Readability: good, medium, hard, very hard (receipt / odometer).

| No. | Date, time | Station | Fuel | Quantity | Price/unit | Total € | km odometer | km receipt | Readability |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 26.08.2026 07:42 | Nordring Energie | Super E10 | 42,18 l | 1,879 | 79,26 | 61240 | 61228 | good / good |
| 2 | 30.08.2026 18:15 | Rheintal Tank GmbH | Super E10 | 38,64 l | 1,859 | 71,83 | 61834 | 61809 | good / good |
| 3 | 03.09.2026 12:03 | Autohof Wesel Sued | Super E10 | 44,05 l | 1,899 | 83,65 | 62386 | 62378 | medium / medium |
| 4 | 06.09.2026 21:47 | Delta Tankstelle | Super E10 | 35,72 l | 1,919 | 68,55 | 62989 | 62958 | hard / hard |
| 5 | 10.09.2026 09:20 | Markt Energie | Super E10 | 40,30 l | 1,869 | 75,32 | 63499 | 63495 | medium / hard |
| 6 | 13.09.2026 16:31 | Grenzland Tank | Super E10 | 43,86 l | 1,889 | 82,85 | 64059 | 64041 | medium / medium |
| 7 | 15.09.2026 10:26 | Eifel Energie | Motoroel 5W-30 1 l | 1,00 l | 11,990 | 11,99 | 64199 | – | good / good |
| 8 | 18.09.2026 13:58 | Eifel Energie | Super E10 | 41,55 l | 1,909 | 79,32 | 64668 | 64628 | hard / medium |
| 9 | 21.09.2026 19:12 | Sonnenhof Tank | Super E10 | 39,20 l | 1,899 | 74,44 | 65253 | 65238 | hard / hard |
| 10 | 24.09.2026 06:55 | Fruehschicht Tank 24 | Super E10 | 45,10 l | 1,939 | 87,45 | 65813 | 65791 | hard / hard |
| 11 | 28.09.2026 08:12 | Nordring Energie | Super E10 | 42,60 l | 1,929 | 82,18 | 66448 | – | good / medium |
| 12 | 01.10.2026 17:48 | Rheintal Tank GmbH | Super E10 | 39,85 l | 1,899 | 75,68 | 67056 | – | medium / hard |
| 13 | 05.10.2026 12:30 | Autohof Wesel Sued | Super E10 | 44,90 l | 1,869 | 83,92 | 67609 | – | medium / hard |
| 14 | 08.10.2026 20:05 | Delta Tankstelle | Super E10 | 36,20 l | 1,889 | 68,38 | 68241 | – | hard / hard |
| 15 | 12.10.2026 09:40 | Markt Energie | Super E10 | 41,75 l | 1,859 | 77,61 | 68766 | – | good / hard |
| 16 | 15.10.2026 15:22 | Grenzland Tank | Super E10 | 43,30 l | 1,919 | 83,09 | 69346 | – | medium / hard |
| 17 | 19.10.2026 11:05 | Sonnenhof Tank | Super E10 | 38,40 l | 1,899 | 72,92 | 69956 | – | hard / hard |
| 18 | 22.10.2026 16:50 | Eifel Energie | Super E10 | 45,00 l | 1,879 | 84,56 | 70505 | – | hard / very hard |
| 19 | 26.10.2026 08:25 | Fruehschicht Tank 24 | Super E10 | 40,15 l | 1,909 | 76,65 | 71130 | – | medium / very hard |
| 20 | 30.10.2026 18:30 | Autohof Wesel Sued | Super E10 | 42,85 l | 1,929 | 82,66 | 71704 | – | hard / very hard |

- **No. 1 to 10:** the receipt shows a **mileage** that differs slightly from the odometer (the odometer was photographed shortly before). Readability ranges from good to hard.
- **No. 11 to 20:** the receipt has **no** mileage. The reading is only on the odometer photo, and those photos are much harder to read (glare, fogged glass, motion blur, night).
- **No. 7** is not a refuelling: a shop receipt for 1 litre of engine oil (accessory). When sending it alone, add the caption `oil`; in a batch without a caption it becomes an entry with "1.00 l" that you correct by hand as an accessory.

### How to test

1. **All at once:** press the photo button in the panel and select all 40 images. They are sorted by capture time and read one after the other. The progress dialog shows all photos, **Cancel** stops the batch. A summary with warnings follows.
2. **Pair by pair:** an odometer photo and its receipt, in any order. The first one creates the entry, the second joins it.
3. **Via Telegram or WhatsApp:** send pairs **in order** and promptly (EXIF is missing there).
4. **Empty it first:** best test with a vehicle that has no entries, otherwise test and real data mix.

### Self-test with evaluation

So you do not have to check the result line by line, `vergleich.py` is included (plain Python, no extra packages):

1. Upload all test images as described above.
2. Download the **CSV export** in the panel.
3. Run in the folder `tests/test_images`: `python vergleich.py export.csv`

The script matches each pair by date and checks quantity, price and total. For the mileage it distinguishes **ok** (odometer or receipt reading), **leer** (empty, allowed: when in doubt it is left out) and **FALSCH** (wrong, the actual failure). At the end it says "BESTANDEN" (passed) if no wrong value and no missing entry was found.

### What to expect

- **20 entries** (the oil receipt as an entry of its own), sorted by date and numbered, with station, quantity, price and total from the receipt.
- **Mileage:** for no. 1 to 10 from the receipt or odometer, for no. 11 to 20 from the odometer only. If the odometer photo cannot be read with certainty (mostly no. 12 to 20), the mileage stays **empty**. That is intended: **when in doubt the reading is left out** instead of being guessed. A *wrong* reading would be the failure, an empty one is not.
- **No follow-up questions in the middle of a batch.** Oddities (for example an implausible consumption) are listed in the summary at the end.
- Consumption (l/100 km) should be around 5.7 to 8.2 (that is how the test data is built) once two mileage readings are known next to each other.

The images are free to use (same licence as the project, MIT).
