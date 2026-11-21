# Drive Energy Doc für Home Assistant

Tank-/Ladebuch für **beliebig viele Fahrzeuge** (Verbrenner und Elektro). Einmal globale Einstellungen (Preisquellen, Strompreis, KI), dann je Fahrzeug ein Eintrag mit Kraftstoffart, Sensoren und Telegram.

## Was es tut
- **Tankvorgang automatisch erkennen** aus Füllstand (%), Kilometerstand und GPS:
  - Anstiege werden zu *einem* Vorgang addiert; er zählt erst ab **5 % Gesamtzuwachs** (einstellbar).
  - Ende: **60 s ohne Zuwachs und mehr als 250 m vom Tankort entfernt** (einstellbar). Bei Elektro entfällt die Entfernung, Standard 10 min Ruhe.
- **Spritpreis** über Tankerkönig (nächste Tankstelle ≤ 400 m, Preis zum Zeitpunkt des Tankens); Elektro: fester oder per Entität gelesener Strompreis.
- **Telegram je Fahrzeug** (eigener Bot oder eigener Chat): Meldung nach dem Tanken mit Bitte um Beleg. Antwort als Foto (Bon oder Zapfsäule) oder Text `45,93 105,13` / `45,93 2,289 105,13` / mit Datum `27.10. 45,93 105,13`. `zusatz` im Bildtext = weiteres Foto zum letzten Tankvorgang. **Zubehör** (AdBlue, Öl, Scheibenwischer …): Kennwort **`+`, `e`, `x`, `extra`, `z`, `zub`** oder `zubehör`, danach optional die Bezeichnung und die Zahlen, z. B. `+ 24,90`, `extra Öl 1 9,50` oder `z Scheibenwischer 24,90` (nur Betrag, Menge Betrag oder Menge Preis Betrag, optional Datum). Dasselbe als Bildtext zu einem Foto hängt den Beleg an den Eintrag. Für häufige Fälle gibt es Kurzwörter ohne Kennwort: `adblue`, `öl`, `scheibenwischer`, `scheibenwasser`, `frostschutz`. Im Panel mit „+“ (Art = Bezeichnung des Zubehörs). Zubehör erscheint als eigener Eintrag, zählt zu den Kosten, aber nicht in den Verbrauch.
- **Hilfe in der Nachricht:** `?`, `h`, `help` oder `hilfe` (auch `/help`, `/start`) listet alle Kommandos auf.
- **Beleg lesen per KI** über eine beliebige HA-`ai_task`-Entität (Gemini, OpenAI, Anthropic …); das Foto wird auf den Beleg zugeschnitten, das Original bleibt gesichert.
- **Panel „Drive Energy Doc“** in der Seitenleiste: Liste, Belegfotos, Bearbeiten, manueller Eintrag, **CSV-Export** (Excel-tauglich).
- Sensoren je Fahrzeug: Status, letztes Tanken, letzter Preis, Verbrauch (Ø letzte 5, Voll-zu-Voll), Kosten 12 Monate. Event `drive_energy_doc_refuel` bei jedem erkannten Tanken.
- Dienste: `drive_energy_doc.export_csv` (schreibt `config/drive_energy_doc/<Name>.csv`), `drive_energy_doc.submit_text`.

## Installation
**HACS:** Repository `AlphaLima/ha-drive-energy-doc` als benutzerdefiniertes Repository (Kategorie Integration) hinzufügen, installieren, HA neu starten. **Manuell:** `custom_components/drive_energy_doc` nach `config/custom_components/` kopieren, HA neu starten, *Einstellungen → Geräte & Dienste → Integration hinzufügen → Drive Energy Doc*. Zuerst „Globale Einstellungen“ anlegen (Preisquelle automatisch nach Land oder fest, Tankerkönig-Schlüssel nur für DE, Strompreis, KI – leer = Gemini automatisch), danach je Fahrzeug „Fahrzeug hinzufügen“. Die Preisquellen gelten für alle Fahrzeuge; pro Fahrzeug wird nur Diesel/E5/E10/Elektro gewählt. Ohne jede Preisquelle genügt der Beleg.

## Telegram einrichten
1. Bot bei @BotFather anlegen, Token eintragen. Ein Token darf nur von **einem** Programm abgefragt werden (nicht parallel in Node-RED oder `telegram_bot`).
2. Dem Bot `/start` schreiben, er nennt die Chat-ID; diese beim Fahrzeug eintragen. Mehrere Fahrzeuge: je eigener Bot oder je eigene Gruppe/Chat-ID.

## WhatsApp einrichten (offizielle Cloud API von Meta)
1. Auf developers.facebook.com eine App vom Typ „Business“ anlegen, Produkt „WhatsApp“ hinzufügen, Telefonnummer-ID und einen **dauerhaften** Zugriffstoken (System-User) holen. Das App-Secret steht unter App-Einstellungen → Allgemein.
2. In den Drive Energy Doc-Einstellungen eintragen: Token, Telefonnummern-ID, ein frei gewähltes Verify-Token, App-Secret (ohne Secret verarbeitet der Webhook nichts).
3. Im Meta-Dashboard Webhook anlegen: Callback-URL `https://<deine-öffentliche-HA-Adresse>/api/drive_energy_doc/whatsapp`, dasselbe Verify-Token, Feld `messages` abonnieren. HA muss dafür per HTTPS aus dem Internet erreichbar sein.
4. Beim Fahrzeug die Nummer des Fahrers eintragen (mit Landesvorwahl, ohne + und Leerzeichen); nur Nachrichten dieser Nummer werden angenommen.
5. Meldungen von sich aus (Tankvorgang erkannt) erlaubt WhatsApp nur innerhalb von 24 h nach der letzten Nachricht des Fahrers. Danach nur mit freigegebener Vorlage: in Meta eine Vorlage (Kategorie Utility) mit einem Text wie `Drive Energy Doc: {{1}}` anlegen und ihren Namen in den Einstellungen eintragen. Ohne Vorlage kommt die Meldung nur im offenen Fenster an.


## Tacho-Foto
Ein Foto des Tachos (oder Text wie `km 123456`) wird gelesen und dem Tankvorgang zugeordnet, der zur Sendezeit am besten passt (Fenster 24 h); bei Abweichung oder unplausiblem Wert fragt die Integration nach.

## Grenzen
Füllstand muss in % vorliegen. Die Integration ist noch jung (0.1.x); bitte Fehler als Issue melden.

## Tests
`python tests/test_detector.py`, `test_receipt.py`, `test_stats.py`, `test_plate.py` (ohne Home Assistant).

## Lizenz
MIT
