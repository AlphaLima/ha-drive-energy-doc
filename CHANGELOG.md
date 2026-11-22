# Changelog

## 0.1.75b20 (unveröffentlicht)
- Konfigurieren-Menü eines Fahrzeugs: erst Fahrzeugdaten, dann Kommunikation, dann Tankerkennung.

## 0.1.75b19 (unveröffentlicht)
- Panel: Beschriftung „Foto aus der Galerie“ jetzt auch im Panel-Code (b18 hatte nur die Übersetzungen umbenannt).

## 0.1.75b18 (unveröffentlicht)
- Panel: „Foto aus dem Archiv“ heißt jetzt „Foto aus der Galerie“.

## 0.1.75b17 (unveröffentlicht)
- Panel (Handy): Der Foto-Knopf fragt jetzt „Kamera“ oder „Foto aus der Galerie“; am PC öffnet er direkt die Dateiauswahl.

## 0.1.75b16 (unveröffentlicht)
- Panel: Im Fahrzeug-Auswahldialog steht rechts das Fahrzeugbild als kleines Bildchen.

## 0.1.75b15 (unveröffentlicht)
- Panel: Layout-Fehler im Kopfbereich behoben (Klassenname kollidierte mit dem alten Zähler-Stil).

## 0.1.75b14 (unveröffentlicht)
- Panel: Auswahlzeile der Fahrzeuge entfällt; ein Klick auf den Kopfbereich öffnet einen Auswahldialog mit allen Fahrzeugen.

## 0.1.75b13 (unveröffentlicht)
- Panel: In der Fahrzeugauswahl wählt auch ein Klick auf den Fahrzeugtyp neben dem Kennzeichen das Fahrzeug aus.

## 0.1.75b12 (unveröffentlicht)
- Panel: Fahrzeugauswahl nur noch über das Kennzeichen (angeklicktes Schild wird hervorgehoben, keine eigenen Knöpfe); Fahrzeuge ohne Kennzeichen erscheinen mit ihrem Namen.

## 0.1.75b11 (unveröffentlicht)
- Panel: Foto-Kachel heißt „Beleg / km Stand fotografieren“ (in allen Sprachen übersetzt).

## 0.1.75b10 (unveröffentlicht)
- Kennzeichen und Land sind wieder im Konfigurationsdialog (mit Schild-Vorschau); die Länderauswahl braucht keine Übersetzungsschlüssel mehr (Hassfest).
- Panel: Bei mehreren Fahrzeugen zeigt die Auswahl das Kennzeichen; ein Klick darauf wählt das Fahrzeug. Der Kennzeichen-Dialog im Panel entfällt.

## 0.1.75b9 (unveröffentlicht)
- Panel: Anzahl der Einträge und Status stehen gestapelt (Wert über Beschriftung) links neben den Knöpfen.

## 0.1.75b8 (unveröffentlicht)
- Panel: Druck-Standard ist jetzt Hochformat; der Foto-Knopf ist höher.

## 0.1.75b7 (unveröffentlicht)
- Panel: großer Foto-Knopf („Beleg fotografieren“) als Kachel neben den Kennzahlen; der Status steht jetzt in der Knopfleiste.

## 0.1.75b6 (unveröffentlicht)
- Panel: Kennzeichen-Knopf entfernt; ein Klick auf das Kennzeichen in der Kopfzeile öffnet den Kennzeichen-Dialog (ohne Kennzeichen steht dort ein Platzhalter zum Anklicken).

## 0.1.75b5 (Beta)
- Panel: Notiz hinzufügen und ändern über einen eigenen Knopf mit Textfeld-Dialog (statt Browser-Abfragen, die in der Handy-App nicht zuverlässig funktionieren).

## 0.1.75b4 (Beta)
- Hassfest: Manifest-Schlüssel sortiert, ungültige Länder-Übersetzung entfernt, `CONFIG_SCHEMA` ergänzt.

## 0.1.75b3 (Beta)
- Marketplace-Vorbereitung: Kategorien im Manifest (`vehicles_transport.cars_evs`, `energy.ev_charging`), Installationshinweis für den Marketplace.

## 0.1.75b2 (Beta)
- Kennzeichen und Land sind nicht mehr im Konfigurationsdialog, sondern nur noch im Panel einstellbar (bestehende Werte bleiben erhalten); Schild-Vorschau-Schritt entfällt.
- README: Screenshot des Kennzeichen-Dialogs.

## 0.1.75b1 (Beta)
- Mehrsprachig: Panel und Bot in 36 Sprachen (alle europäischen Sprachen und Russisch), Sprache der Bot-Antworten je Fahrzeug einstellbar, Kommandos in allen Sprachen verständlich.
- README: Hinweis auf weiteres Verbrauchsmaterial, Abschnitt Sprachen.

## 0.1.74b1 (Beta)
- README zusätzlich auf Englisch.
- Foto-Betrieb: Tacho-Foto ohne vorhandenen Eintrag legt einen neuen an; README beschreibt den Betrieb ohne Auto-Anbindung (Flottenmanagement).

## 0.1.73
- Panel: Fotoauswahl erscheint beim Überfahren des Bildes (ohne Zähler-Symbol).

## 0.1.72
- Fahrzeug: Füllstand-, Kilometerstand- und GPS-Sensor sind optional (reiner Foto-Betrieb); Belege ohne passenden Eintrag legen dann automatisch einen neuen an.

## 0.1.71
- Panel: bei mehreren Fotos Auswahl per Hover/Klick, sichtbare Trennlinien an den Spaltenüberschriften (zum Verschieben der Breite).

## 0.1.70
- Panel (PC): kompaktere Tabelle, Uhrzeit unter dem Datum, Adresse und GPS in einer Zeile.

## 0.1.69
- Panel: Notiz als Symbol, Text per Hover (Tooltip) oder Klick (Popup).

## 0.1.68
- Panel (Handy): noch kompaktere Karten, Uhrzeit unter dem Datum.

## 0.1.67
- Panel: kompakte Kartenansicht der Liste auf schmalen Bildschirmen (Handy).

## 0.1.66
- Erste öffentliche Version: Tank-/Ladebuch für mehrere Fahrzeuge, automatische Erkennung, Preisquellen, Telegram/WhatsApp-Belege per KI, Zubehör, Tacho-Foto, Panel mit CSV/PDF, Kennzeichen-Darstellung.
