# Drive Energy Doc für Home Assistant

Ein **Tank- und Ladebuch für beliebig viele Fahrzeuge** (Verbrenner und Elektro), das sich weitgehend selbst führt:
Home Assistant erkennt das Tanken oder Laden aus den Sensoren des Autos, holt den Preis, bittet per Telegram um den Beleg,
liest den Beleg per KI und rechnet den Verbrauch aus. Alles landet in einer Liste im Seitenmenü (mit CSV- und PDF-Druck).

## Inhalt
0. [Wozu das Ganze? Der Sinn des Tankbuches](#wozu-das-ganze-der-sinn-des-tankbuches) · [Die Wege ins Buch](#die-wege-daten-ins-buch-zu-bekommen)
1. [So funktioniert es (Überblick)](#so-funktioniert-es-überblick)
2. [Wie ein Tanken erkannt wird (genau)](#wie-ein-tanken-erkannt-wird-genau)
3. [Welche Position und welcher Preis verwendet wird](#welche-position-und-welcher-preis-verwendet-wird)
4. [Beleg, Zubehör und Tacho per Nachricht](#beleg-zubehör-und-tacho-per-nachricht)
5. [Wie der Verbrauch berechnet wird](#wie-der-verbrauch-berechnet-wird)
6. [Das Panel](#das-panel)
7. [Sensoren, Ereignis und Dienste](#sensoren-ereignis-und-dienste)
8. [Installation und Einrichtung](#installation-und-einrichtung)
9. [Telegram einrichten](#telegram-einrichten) · [WhatsApp einrichten](#whatsapp-einrichten-offizielle-cloud-api-von-meta)
10. [Daten und Datenschutz](#daten-und-datenschutz)
11. [Grenzen](#grenzen) · [Tests](#tests) · [Lizenz](#lizenz)

---

## Wozu das Ganze? Der Sinn des Tankbuches

Ein Fahrtenbuch/Tankbuch beantwortet Fragen, die man sonst nur schätzt:
- **Was kostet mein Auto wirklich?** Kraftstoff bzw. Strom, dazu Zubehör (AdBlue, Öl, Wischer) – je Monat und je 12 Monate.
- **Was verbraucht es wirklich?** Voll-zu-Voll gerechnet, unabhängig vom (oft zu optimistischen) Bordcomputer; Veränderungen
  (Winterreifen, Defekt, andere Fahrweise) werden sichtbar.
- **Belege und Nachweise:** Jede Zeile kann das Foto des Bons und des Tachostandes enthalten – für Steuer, Firmenwagen,
  Garantie oder Verkauf. Liste als CSV (Excel) oder PDF zum Ausdrucken.
- **Mehrere Fahrzeuge in einem Buch**, Verbrenner und Elektro gleich behandelt, ohne Zettelwirtschaft oder Tabellen von Hand.

Der Aufwand soll dabei so klein wie möglich sein: Das Auto meldet das Tanken von selbst, du schickst höchstens noch ein Foto vom Bon.

## Die Wege, Daten ins Buch zu bekommen

| Weg | Was du tust | Was automatisch passiert |
|---|---|---|
| **1. Automatisch (Sensoren)** | nichts | Füllstand steigt → Tanken erkannt, Menge, Ort, Kilometerstand und (wenn verfügbar) Preis werden eingetragen |
| **2. Beleg-Foto per Telegram / WhatsApp / Companion** | Bon oder Zapfsäule fotografieren und dem Bot schicken | KI liest Menge/Preis/Summe/Datum, Foto wird zugeschnitten und am Eintrag gespeichert, Werte vom Beleg ersetzen die geschätzten |
| **3. Beleg als Text** | `45,93 105,13` oder `27.10. 45,93 105,13` schreiben | Werte werden dem passenden Tanken zugeordnet (ohne KI) |
| **4. Zubehör** | `+ 24,90`, `extra Öl 1 9,50`, Kurzwort `adblue` oder Foto mit Bildtext | eigener Eintrag, zählt zu den Kosten, nicht zum Verbrauch |
| **5. Tacho-Foto / `km 54210`** | Tacho fotografieren oder Text senden | Kilometerstand wird dem zeitlich passenden Tanken zugeordnet; bei Zweifeln fragt der Bot nach |
| **6. Panel** | manuellen Eintrag („+“), Eintrag bearbeiten, Fotos hochladen oder löschen | – |
| **7. Dienst** `drive_energy_doc.submit_text` | z. B. aus einer Automation oder einem Skript Text einspeisen | wie Weg 3–5 |
| **8. Import (einmalig)** | Altdaten als `config/drive_energy_doc/import/<Fahrzeugname>/entries.json` (optional mit `photos/`, `originals/`) ablegen | Einträge samt Fotos werden beim nächsten Start übernommen |

Der **Beleg hat immer Vorrang** vor dem Automatischen: Das Auto schätzt, der Bon stimmt. Alle Wege führen in dasselbe Buch;
du kannst sie beliebig mischen (z. B. automatisch erkennen lassen und nur gelegentlich den Bon schicken).

---

## So funktioniert es (Überblick)

```
Auto-Sensoren (Füllstand %, Kilometerstand, GPS)
        │
        ▼
 Erkennung: Füllstand steigt → Tanken läuft → Ruhe + Abstand → "fertig"
        │
        ├─► Preis nachschlagen (Tankstellen-Dienst, optional)
        ├─► Eintrag im Buch anlegen (Zeit, Menge, Preis, Kosten, Kilometerstand, Ort)
        └─► Nachricht per Telegram/WhatsApp/Companion-App: "Tanken erkannt – bitte Beleg senden"
                   │
                   ▼
        Foto vom Bon / Zapfsäule / Text  ─►  KI liest Menge, Preis, Summe, Datum
                   │                         (Foto wird zugeschnitten und am Eintrag gespeichert)
                   ▼
        Der Beleg gewinnt immer: seine Werte ersetzen die geschätzten
```

Jedes Fahrzeug ist ein eigener Eintrag in der Integration. Daneben gibt es einen Eintrag **„Globale Einstellungen“**
für Dinge, die für alle Fahrzeuge gleich sind (Preisquellen, Strompreis, KI-Auswahl, Telegram/WhatsApp-Zugänge).
Jedes Fahrzeug hat seine eigene Konfiguration (Sensoren, Kraftstoffart, Schwellwerte, Chat), sein eigenes Buch und eigene Sensoren.

## Wie ein Tanken erkannt wird (genau)

Die Erkennung läuft als kleiner Automat, der bei jeder Änderung des **Füllstand-Sensors** (in %) arbeitet und alle 15 Sekunden
zusätzlich die Zeit prüft. Es sind vier Zustände:

1. **Ruhe.** Es passiert nichts, solange der Füllstand gleich bleibt oder sinkt (Fahren verbraucht Kraftstoff).
2. **Kandidat.** Sobald der Füllstand **steigt**, merkt sich die Integration den Wert davor (`Füllstand von`), den Zeitpunkt und die
   **Position**. Weitere Anstiege werden zu *einem* Vorgang aufaddiert (viele Autos melden die Füllung in mehreren kleinen Schritten).
3. **Gültig.** Sobald der Gesamtzuwachs **mindestens 5 %** erreicht (einstellbar), gilt der Vorgang als echtes Tanken. Kleinere
   Schwankungen (Lagesensor, Bergfahrt, Messrauschen) werden so ignoriert. Ab hier wird der Preis geholt (siehe unten).
4. **Fertig.** Das Tanken wird abgeschlossen, wenn **beides** zutrifft:
   - der Füllstand ist **60 Sekunden lang nicht weiter gestiegen** (einstellbar), und
   - das Auto ist **mehr als 250 m vom Tankort entfernt** (einstellbar, per Luftlinie zur Startposition).

   Warum der Abstand? Der Füllstand steigt oft verzögert; wer noch an der Zapfsäule steht, soll nicht schon einen Eintrag auslösen.
   Erst wenn das Auto losgefahren ist, steht fest, dass das Tanken beendet ist. Erst dann kommt die Nachricht mit der Bitte um den Beleg.

   **Ausnahme Elektroauto:** Hier entfällt die Entfernungsbedingung (das Auto bleibt beim Laden stehen). Standard ist **10 Minuten
   Ruhe** ohne weiteren Anstieg; auch das ist einstellbar. Die Abstandsregel lässt sich auch bei Verbrennern abschalten.

**Abbruch.** Wird der Zuwachs nach 10 Minuten nicht mehr größer und nie gültig (unter der Schwelle), wird der Kandidat verworfen.
Läuft Home Assistant gerade neu an, bleibt ein angefangener Vorgang erhalten (er wird gespeichert) und wird danach weitergeführt.

**Was im Eintrag landet:** Zeitpunkt, Füllstand von/bis, daraus die Menge (Zuwachs × Tankvolumen bzw. Akkukapazität),
Kilometerstand (aus dem Tacho-Sensor, falls vorhanden), Ort und der Preis (falls verfügbar). Ein Tankvolumen wird dafür einmal
beim Fahrzeug eingetragen.

## Welche Position und welcher Preis verwendet wird

**Position:** Es zählt die **zuletzt bekannte GPS-Position des Fahrzeugs (`device_tracker`) in dem Moment, in dem der erste
Füllstand-Anstieg eintrifft**. Das Auto steht dann an der Zapfsäule. Wichtig: Meldet das Auto den neuen Füllstand erst spät, kann die
zuletzt gemeldete Position noch vom Vorweg stammen. Dann zeigt der Eintrag den falschen Ort und der Preis kommt von der falschen
Tankstelle – der Beleg korrigiert den Preis in jedem Fall.

**Preis:** Optional. Beim Übergang zu „gültig“ sucht die Integration mit der Startposition die **nächste geöffnete Tankstelle im
Umkreis von 400 m** und nimmt den Preis der gewählten Kraftstoffart (Diesel, E5, E10). Quellen:

| Land | Dienst | Schlüssel |
|---|---|---|
| Deutschland | Tankerkönig | persönlicher, kostenloser API-Schlüssel |
| Österreich | E-Control | keiner nötig |
| Frankreich | prix-carburants (data.gouv.fr) | keiner nötig |

Die Quelle richtet sich nach dem Land der Position (oder fest gewählt). Ohne jede Quelle funktioniert alles weiter; dann kommt der Preis
vom Beleg. **Elektro:** fester Preis je kWh oder ein Sensor/Helfer, der den Strompreis liefert (z. B. dynamischer Tarif).

**Der Beleg hat immer Vorrang.** Menge, Preis und Summe vom Beleg überschreiben die geschätzten Werte. Ein Eintrag ist erst dann
als „Beleg geprüft“ markiert, wenn mindestens Menge, Preis oder Summe vom Beleg kamen.

## Beleg, Zubehör und Tacho per Nachricht

Die Nachrichten laufen über **Telegram** (eigener Bot, empfohlen), **WhatsApp** (Cloud-API von Meta) oder die **Companion-App**
(Push-Nachricht; Foto-Upload dann im Panel). Pro Fahrzeug wählst du, welche Kanäle genutzt werden. Mit `?`, `h`, `help` oder `hilfe`
(auch `/help`, `/start`) zeigt der Bot alle Kommandos.

### Beleg zum Tanken
- **Foto** vom Bon oder von der Zapfsäule schicken. Die KI liest Menge, Preis, Summe, Datum und – falls sichtbar – den Kilometerstand.
  Das Foto wird **auf den Beleg zugeschnitten** (die KI nennt den Rahmen; ohne KI-Antwort greift eine einfache Erkennung hochformatiger,
  heller Papierbons). Das Original bleibt gesichert und ist im Panel einsehbar.
- **Text:** `45,93 105,13` (Menge Betrag), `45,93 2,289 105,13` (Menge Preis Betrag) oder mit Datum davor `27.10. 45,93 105,13`.
- **Weiteres Foto** zum letzten Tanken: Foto mit dem Wort `zusatz` im Bildtext.
- Ist ein Wert unplausibel oder nicht lesbar, antwortet der Bot mit einem Hinweis statt etwas Falsches zu speichern.

### Zubehör (AdBlue, Öl, Scheibenwischer …)
Alles, was Geld kostet, aber kein Kraftstoff ist. Kennwort **`+`, `e`, `x`, `extra`, `z`, `zub`** oder `zubehör`, danach optional die
Bezeichnung und die Zahlen: `+ 24,90`, `extra Öl 1 9,50`, `z Scheibenwischer 24,90`. Erlaubt sind nur Betrag, Menge Betrag oder Menge
Preis Betrag, optional mit Datum. Kurzwörter ohne Kennwort: `adblue`, `öl`, `scheibenwischer`, `scheibenwasser`, `frostschutz`.
Dasselbe als Bildtext zu einem Foto hängt den Beleg an den Eintrag. Zubehör erscheint als eigene Zeile, zählt zu den Kosten,
aber **nicht** in den Verbrauch.

### Tacho-Kilometerstand
Foto vom Tacho oder Text wie `km 54210` senden. Der Wert wird dem Tankvorgang zugeordnet, dessen Zeit der Sendezeit am nächsten liegt
(Fenster 24 Stunden). Bei großer Abweichung vom gespeicherten Stand (> 300 km), einem Wert kleiner als beim vorigen Tanken oder
einem zu alten Tankvorgang fragt der Bot nach und wartet auf deine Bestätigung (`ja`).

## Wie der Verbrauch berechnet wird

Methode **Voll-zu-Voll**: Ein Tanken zählt als „voll“, wenn der Zuwachs **mindestens 30 %** beträgt. Zwischen zwei vollen Tanken
werden alle getankten Mengen addiert und durch die gefahrenen Kilometer geteilt (Ergebnis je 100 km bzw. kWh/100 km).
Teilbetankungen zeigen daher keinen eigenen Verbrauch, fließen aber in die nächste volle Rechnung ein. Zubehör zählt nicht.
Ist über den Zuwachs nichts bekannt (z. B. von Hand angelegt), gilt das Tanken als voll. Ohne Kilometerstand gibt es keine Rechnung.

## Das Panel

Nach der Einrichtung erscheint **„Drive Energy Doc“** in der Seitenleiste:
- Liste aller Tanken/Ladungen und Zubehör je Fahrzeug, Spalten verschiebbar und in der Breite änderbar.
- Kennzeichen-Darstellung (alle europäischen Länder, EU-Ring bzw. gelb für NL/GB), Fahrzeugbild und -typ in der Kopfzeile.
- Belegfotos und Tacho-Fotos mit Vorschau beim Überfahren, Löschen mit Rückfrage; Foto-Upload.
- Bearbeiten, manueller Eintrag („+“), Ort mit kleiner Google-Maps-Verknüpfung.
- **CSV-Export** (Excel-tauglich) und **Druck/PDF** (Hoch- oder Querformat, mit oder ohne Belege).

## Sensoren, Ereignis und Dienste

Je Fahrzeug: **Status**, **letztes Tanken**, **letzter Preis**, **Verbrauch** (Ø der letzten 5, Voll-zu-Voll), **Kosten 12 Monate**.
Bei jedem erkannten Tanken wird das Ereignis `drive_energy_doc_refuel` ausgelöst (für eigene Automationen).
Dienste: `drive_energy_doc.export_csv` (schreibt `config/drive_energy_doc/<Name>.csv`), `drive_energy_doc.submit_text` (Text wie eine
Nachricht einspeisen) und `drive_energy_doc.test_message`.

## Installation und Einrichtung

**HACS:** Repository `AlphaLima/ha-drive-energy-doc` als benutzerdefiniertes Repository (Kategorie *Integration*) hinzufügen,
installieren, HA neu starten. **Manuell:** den Ordner `custom_components/drive_energy_doc` nach `config/custom_components/` kopieren,
HA neu starten.

Dann *Einstellungen → Geräte & Dienste → Integration hinzufügen → Drive Energy Doc*:

1. **Globale Einstellungen** anlegen: Preisquelle (automatisch nach Land oder fest), Tankerkönig-Schlüssel (nur für Deutschland),
   Strompreis, KI (leer = Gemini automatisch, sonst eine `ai_task`-Entität), Telegram-/WhatsApp-Zugänge.
2. **Fahrzeug hinzufügen:** Name, Energieart (Diesel/E5/E10/Elektro), **Füllstand-Sensor (in %)**, Kilometerstand-Sensor,
   `device_tracker`, Tankvolumen bzw. Akkukapazität. Optional: Kennzeichen, Land, Fahrzeugtyp, Fahrzeugbild, Telegram-Chat.
3. Schwellwerte (5 %, 60 s, 250 m) und Nachrichtenkanäle sind je Fahrzeug unter *Konfigurieren* änderbar.

Voraussetzungen: Home Assistant ab 2025.8; für das Lesen von Belegen eine `ai_task`-Integration (Gemini, OpenAI, Anthropic …).

## Telegram einrichten
1. Bot bei @BotFather anlegen, Token in den Globalen Einstellungen eintragen. Ein Token darf nur von **einem** Programm abgefragt werden
   (nicht parallel in Node-RED oder `telegram_bot`).
2. Dem Bot `/start` schreiben, er nennt die Chat-ID; diese beim Fahrzeug eintragen. Mehrere Fahrzeuge: je eigener Bot oder je eigene
   Gruppe/Chat-ID. Nachrichten aus unbekannten Chats werden nicht verarbeitet (der Bot antwortet nur mit einem Hinweis auf die Chat-ID).

## WhatsApp einrichten (offizielle Cloud API von Meta)
1. Auf developers.facebook.com eine App vom Typ „Business“ anlegen, Produkt „WhatsApp“ hinzufügen, Telefonnummer-ID und einen
   **dauerhaften** Zugriffstoken (System-User) holen. Das App-Secret steht unter App-Einstellungen → Allgemein.
2. In den Einstellungen eintragen: Token, Telefonnummern-ID, ein frei gewähltes Verify-Token, App-Secret (ohne Secret verarbeitet der Webhook nichts).
3. Im Meta-Dashboard Webhook anlegen: Callback-URL `https://<deine-öffentliche-HA-Adresse>/api/drive_energy_doc/whatsapp`, dasselbe
   Verify-Token, Feld `messages` abonnieren. HA muss dafür per HTTPS aus dem Internet erreichbar sein.
4. Beim Fahrzeug die Nummer des Fahrers eintragen (mit Landesvorwahl, ohne + und Leerzeichen); nur Nachrichten dieser Nummer werden angenommen.
5. Meldungen von sich aus erlaubt WhatsApp nur innerhalb von 24 h nach der letzten Nachricht des Fahrers. Danach nur mit freigegebener
   Vorlage: in Meta eine Vorlage (Kategorie Utility) mit einem Text wie `Drive Energy Doc: {{1}}` anlegen und ihren Namen eintragen.

## Daten und Datenschutz
- Alle Einträge und Fotos liegen **lokal** in deiner HA-Installation (`.storage` und `config/drive_energy_doc/`). Es gibt keinen Server des Autors.
- Nach außen gehen nur: die Preisabfrage (Position ≈ Tankstellen-Umkreis an den Preisdienst), Nachrichten an Telegram/WhatsApp, und Belegfotos an die
  von dir gewählte KI (`ai_task`).
- Tokens und Schlüssel stehen in der Konfiguration der Integration; teile Diagnosen oder Backups nicht ungeprüft.

## Grenzen
- Der Füllstand muss in **Prozent** vorliegen.
- Die Genauigkeit des Ortes hängt davon ab, wie schnell das Auto Füllstand und Position meldet (siehe oben).
- Die Integration ist noch jung (0.1.x); bitte Fehler als Issue melden.

## Tests
`python tests/test_detector.py`, `test_receipt.py`, `test_stats.py`, `test_plate.py` (ohne Home Assistant).

## Lizenz
MIT
