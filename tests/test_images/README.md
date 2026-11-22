# Testbilder / Test images

**Deutsch:** 20 frei erfundene Foto-Paare zum Ausprobieren (keine echten Belege, Orte oder Kilometerstände). `NN_beleg.jpg` und `NN_tacho.jpg` gehören zusammen. Es ist ein Benzin-Auto (Super E10, ca. 7 l/100 km); Datum und Kilometerstand steigen von Nr. 1 bis Nr. 20.

- **Nr. 1 bis 10** (`sollwerte.csv`): Belege mit Datum, Uhrzeit und einem leicht abweichenden Kilometerstand (bei Nr. 7 ein Kassenbon über 1 l Motoröl, ohne Kilometerstand, am besten mit der Bildunterschrift `öl` senden). Die Lesbarkeit reicht von gut bis schwer (Winkel, Licht, Unschärfe, Nacht, Gegenlicht, Knitter, verblasst).
- **Nr. 11 bis 20** (`sollwerte_11-20.csv`): Belege **ohne** Kilometerstand, die Tacho-Fotos sind deutlich schlechter lesbar (Spiegelung, Beschlag, Bewegungsunschärfe, Nacht).
- Die richtigen Werte stehen in den CSV-Dateien (`km_tacho` = Stand auf dem Tacho-Foto, `km_beleg` = Stand auf dem Beleg).

**Test:** erst das Tacho-Foto, dann den Beleg an den Bot oder über den Foto-Knopf im Panel schicken (oder umgekehrt). Die Zuordnung läuft über die Uhrzeit der Nachricht; am besten die Paare der Reihe nach senden.

**English:** 20 entirely fictional photo pairs for trying things out (no real receipts, places or odometer readings). `NN_beleg.jpg` (receipt) and `NN_tacho.jpg` (odometer) belong together. One petrol car (Super E10, about 7 l/100 km); date and mileage increase from no. 1 to no. 20.

- **No. 1 to 10** (`sollwerte.csv`): receipts with date, time and a slightly different odometer reading (no. 7 is a shop receipt for 1 l of engine oil without mileage; send it with the caption `oil`). Readability ranges from good to hard.
- **No. 11 to 20** (`sollwerte_11-20.csv`): receipts **without** a mileage, with clearly worse odometer photos (glare, fogged glass, motion blur, night).
- The correct values are in the CSV files (`km_tacho` = reading on the odometer photo, `km_beleg` = reading on the receipt).

**Test:** send the odometer photo first, then the receipt (or the other way round) to the bot or via the photo button in the panel. The photos carry the date and time of the refuelling in their EXIF data (odometer photo 3 minutes before the receipt time). Photos uploaded via the panel are matched by this capture time, so they can be sent in any order and on any day; photos sent via Telegram or WhatsApp lose their EXIF data and are matched by the time of the message, so send those pairs in order.
