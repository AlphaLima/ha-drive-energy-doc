# Changelog

## 0.1.79
Patch-Release: nur Dokumentation und Paketpflege, keine Funktionsänderung gegenüber 0.1.78.
- README: Hinweis auf erfundene Dummydaten, Länderübersicht der Preisportale, Beschreibung von Stapel-Upload, „im Zweifel weglassen“ und den neuen Dialogen, Badges.
- Testbilder: ausführliche Anleitung (DE/EN) mit Aufnahmezeit statt Dateiname und Selbsttest-Skript `tests/test_images/vergleich.py`.

## 0.1.78
- Konfigurationsdialog (Fahrzeug): Vorschau des Fahrzeugbilds (hochgeladenes Bild oder gewählte Bild-Entität) neben dem Kennzeichen, auch direkt nach dem Auswählen einer Datei.
- Im Zweifel wird ein aus einem Foto gelesener Kilometerstand weggelassen, ohne Rückfrage: passt er nicht zum Eintrag, liegt er unter dem vorigen Stand oder ergibt er einen unplausiblen Verbrauch, bleibt das Tacho-Foto als Zusatzfoto am Eintrag, der Kilometerstand bleibt leer (Beleg: Beleg wird übernommen, der Stand nicht). Nachgefragt wird nur noch bei von Hand getippten Ständen.
- Stapel-Upload: Die Fotos werden chronologisch nach Aufnahmezeit (EXIF, sonst Änderungsdatum der Datei) verarbeitet, nicht nach Dateiname oder Auswahlreihenfolge; Kameras vergeben Dateinamen beliebig.
- Robustere Kilometerstand-Erkennung: Der KI-Auftrag verlangt für Belege eine ausdrücklich beschriftete Zeile (Belegnummer, Säulen-, Kartennummer zählen nicht). Ein gelesener Stand wird gegen die Reihenfolge der Einträge geprüft (nicht unter dem vorigen, nicht über dem nächsten, höchstens 5000 km Sprung, höchstens sechs Stellen) und sonst ignoriert. Beim Start werden unmögliche, nicht von Hand gesetzte Stände aus älteren Fassungen entfernt.
- Neue Preisquellen für Kraftstoff: **Spanien** (MINETUR) und **Italien** (MIMIT Osservaprezzi), ohne Schlüssel, automatisch nach Land. Die Landesdateien werden höchstens alle 30 Minuten geladen. Spanien braucht für die Verbindung eine ältere TLS-Einstellung (nur für diese Abfrage).
- Stapel-Upload: Plausibilitätsprüfung und Rückfragen zum Kilometerstand erst am Ende (Übersicht mit Warnungen), Abbrechen-Knopf im Fortschrittsdialog, Fotos werden nach Aufnahmezeit (EXIF) zugeordnet, Fortschrittsdialog bleibt beim Neuladen erhalten.
- Ein gemerktes unlesbares Foto blockiert nicht mehr jeden weiteren Upload.
- Fotos aus dem Panel werden nach ihrer Aufnahmezeit (EXIF) zugeordnet, nicht nach dem Upload-Zeitpunkt: ein später hochgeladenes Tacho-Foto landet beim richtigen Tankvorgang. Telegram/WhatsApp entfernen EXIF, dort gilt weiter die Nachrichtenzeit. Die Testbilder tragen jetzt die Tankzeit im EXIF.
- Unlesbares Foto: Rückfrage nach dem Kilometerstand statt stilles Anhängen an den letzten Eintrag.
- Panel: großer Korrektur-/Eintrag-von-Hand-Dialog mit allen Feldern; Tacho-Rückfrage mit „Neuer Eintrag“ als Standard.
- Panel: Ergebnisdialog mit festen Antwort-Knöpfen: Nur der Text darüber scrollt, die Knöpfe bleiben immer erreichbar (auch am Handy); lange Rückfragen stehen unter dem Bild.
- Tacho-Foto mit unplausiblem Verbrauch: In der Rückfrage gibt es zusätzlich „Neuer Eintrag“ (Panel-Knopf bzw. Antwort „neu“), wenn das Foto zu keinem vorhandenen Tankvorgang gehört.
- Panel: Der Fortschrittsdialog bei mehreren Fotos zeigt alle Fotos als Leiste (fertige mit Haken, aktuelles hervorgehoben), den Zähler „(2 / 3)“ und einen Fortschrittsbalken; Vorschau und Zähler wechseln mit jedem Foto.
- Fix: Fehlermeldung beim Hochladen mehrerer Fotos kurz nacheinander (zwei gleichzeitige Uploads überschrieben sich die Antwortliste, „NoneType is not iterable“); Uploads laufen jetzt je Fahrzeug nacheinander. KI-Fehler werden mit Typ protokolliert.
- Tacho-Foto: Passt der Kilometerstand fast genau (bis 50 km) zu einem Eintrag ohne Tacho-Foto, geht er vor der Uhrzeit dorthin (auch wenn ein anderer Tankvorgang zeitlich näher liegt oder die Fotos später hochgeladen werden); so entsteht bei Beleg + Tacho im selben Stapel (z. B. später hochgeladen) kein zweiter Eintrag.
- Fix: Ein Tacho-Foto wurde nie ausgewertet, weil die KI-Auswertung ohne Menge und Betrag verworfen wurde; der gelesene Kilometerstand zählt jetzt (legt bei Foto-Betrieb sofort einen neuen Eintrag an).
- Foto, auf dem weder Beleg noch Kilometerstand lesbar ist (und noch kein Eintrag existiert): statt „Kein Tankvorgang zum Zuordnen gefunden“ merkt sich der Bot das Foto und fragt nach dem Kilometerstand als Text (im Panel mit Eingabefeld); damit wird der Eintrag mit dem Foto angelegt.
- Fix: Rückfragen kreisten, weil alte unbeantwortete Fragen (Überschreiben, Kilometerstand, Datum) stehen blieben. Ein neues Foto ersetzt jetzt offene Rückfragen, abgelaufene zählen nicht mehr, und eine beantwortete Frage räumt die übrigen ab.
- Kilometerstand vom Beleg wird bei unplausiblem Verbrauch nicht mehr stillschweigend übernommen: Der Beleg wird gespeichert, der Kilometerstand erst nach Rückfrage (im Panel mit Knöpfen „Übernehmen“ / „Abbrechen“, per Bot mit „ja“ / „nein“).
- Panel: Rückfragen haben fertige Antwort-Knöpfe (Übernehmen / Abbrechen bei Ja/Nein-Fragen wie „Beleg schon eingetragen“, „Neuer Eintrag“ bzw. „Abbrechen“ bei Datumsfragen).

## 0.1.77
- Panel: Spalten lassen sich über einen Spalten-Knopf ein- und ausblenden (pro Browser gemerkt); die Nummern-Spalte ist schmal (46 px).
- Panel: Mehrere Fotos gleichzeitig hochladen (Dateiauswahl mit Mehrfachauswahl, Verarbeitung nacheinander mit Fortschritt „(1 / 3)“, Rückfragen des Bots sofort, am Ende eine Übersicht).
- Tankvorgänge werden laufend nummeriert (Spalte „Nr.“ im Panel, in CSV und Ausdruck; älteste = 1).
- Doppelter Beleg: Gibt es zum Tag schon einen Eintrag mit Beleg, meldet der Bot das (bei gleicher Menge und Summe ausdrücklich) und fragt, ob überschrieben werden soll (ja/nein).
- Foto-Betrieb: Das zuletzt angelegte, noch unvollständige Eintrag (Tacho-Foto ohne Beleg oder Beleg ohne Kilometerstand) bleibt 6 Stunden "offen"; Beleg und Tacho-Foto gehören zusammen, egal in welcher Reihenfolge und mit welchem Datum auf dem Beleg. Kommt ein Tacho-Foto zuerst, entsteht sofort eine neue Zeile, und nach 30 Minuten fragt der Bot einmal nach dem fehlenden Beleg bzw. Foto der Zapfsäule.

## 0.1.76
Neu seit 0.1.69:
- **36 Sprachen** für Panel und Bot (alle europäischen Sprachen und Russisch), Sprache der Bot-Antworten je Fahrzeug einstellbar, Kommandos in allen Sprachen verständlich. Die Seitenleiste heißt auf Deutsch „Tankbuch“, sonst entsprechend (nach der Systemsprache).
- **Foto-Betrieb ohne Auto-Anbindung** (Flottenmanagement): Füllstand-, Kilometerstand- und GPS-Sensor sind optional; Tacho-Foto und Beleg-Foto per Telegram legen die Einträge an.
- **Tacho-Foto und Kilometerstand:** Zuordnung zum passenden Tankvorgang, Rückfrage bei groben Abweichungen und **Plausibilitätsprüfung über den Verbrauch** (Tankmenge, gefahrene km, Durchschnitt) mit Warnung und Frage, ob der Stand trotzdem übernommen werden soll.
- **Beleg per KI:** Anfrage jetzt auf Englisch (besser für andere KI-Anbieter), liest zusätzlich Tankstelle, Anschrift und Uhrzeit.
- **Panel:** Kartenansicht am Handy, kompaktere Tabelle (Uhrzeit unter dem Datum), Notiz als Symbol mit eigenem Dialog, Fotoauswahl bei mehreren Fotos, großer Foto-Knopf mit kleinem Dialog „Kamera / Foto aus der Galerie“, Warte-Dialog mit Fahrzeugbild und Lupe über dem Beleg, großes Ergebnis-Fenster nach dem Upload, Fahrzeugauswahl per Klick auf den Kopfbereich (gemerkt pro Browser), Standard-Druck im Hochformat.
- **Fehler behoben:** Foto-Upload aus dem Panel schlug mit Fehler 500 fehl (seit 0.1.66); die Verarbeitung läuft jetzt auch bei abgebrochener Verbindung weiter. Neuer Test findet undefinierte Namen.
- **Marketplace/HACS:** Kategorien im Manifest, Hassfest- und HACS-Prüfungen grün, README auf Deutsch und Englisch mit Kapiteln zu Telegram, WhatsApp und Elektrofahrzeugen.
- Konfigurieren-Menü: erst Fahrzeugdaten, dann Kommunikation, dann Tankerkennung; Kennzeichen und Land im Konfigurationsdialog.

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
