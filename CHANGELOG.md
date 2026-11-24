# Changelog

## 0.1.81 (24.11.2026)
- Kraftstoffsorte je Tankeintrag: Im Bearbeiten-Dialog neben **Art** das Feld **Kraftstoffart** (Benziner: Super E10, E5, 95, 98, LPG; Diesel: Diesel, Diesel Premium). Die KI liest die Sorte vom Beleg oder der Säule, die Liste zeigt sie unter der Menge.
- Kraftstoffart Autogas (LPG) wählbar; Preise kommen dort vom Beleg (die Preisdienste kennen LPG nicht). Der Bearbeiten-Dialog ist kompakter; die Währungsauswahl steht neben dem Preis und nur, wenn die Währung nicht erkannt wurde.
- Währung ohne Erkennung, weitere Stufen: Fehlt die Position des Fahrzeugs (oder ist der Beleg nicht von heute), wird der Aufnahmeort aus den Foto-Metadaten (EXIF-GPS) genommen; Messenger entfernen ihn meist, ein als Datei gesendetes oder im Panel hochgeladenes Foto behält ihn. Gelingt auch das nicht, steht in der Notiz eine Warnung („Land nicht ermittelbar: Werte als Euro angenommen“). Im Bearbeiten-Dialog gibt es bei Belegen mit Umrechnung oder Warnung ein Feld **Währung des Belegs** mit **Umrechnen**: Betrag und Preis werden aus den Originalwerten zum Tageskurs neu berechnet, die Notiz wird ersetzt.
- Fremdwährung ohne erkannte Währung: Nennt der Beleg keine Währung, wird das Land aus der GPS-Position des Fahrzeugs bestimmt (Rückwärtssuche über OpenStreetMap/Nominatim, nur die auf 0,1° gerundete Position wird gesendet), die Landeswährung angenommen und zum Tageskurs umgerechnet. Die Notiz sagt dann „Keine Währung erkannt, Landeswährung X angenommen (Land)“. Nur bei Belegen von heute; im Euroraum oder ohne Position bleibt alles wie bisher. Umrechnungshinweise stehen nie doppelt in der Notiz.
- Telegram-Alben: Mehrere Fotos in einer Nachricht (Säule, Tacho, Beleg) gelten als ein Vorgang. Der Bot wartet 3 Sekunden auf das letzte Foto, liest sie der Reihe nach ein, fragt dazwischen nicht nach und schickt am Ende eine gemeinsame Antwort samt Plausibilitätsprüfung.
- Display und Beleg desselben Vorgangs: Ein gerade angelegter Eintrag (letzte 6 Stunden) und ein neues Foto mit gleichem Preis je Einheit, einmal ohne Station (Säulen-Display), einmal mit Station (Beleg), gehören zusammen, auch wenn Menge und Betrag wegen eines unscharf gelesenen Displays abweichen: Der Beleg ersetzt die Werte, ein Display-Foto nach dem Beleg hängt nur als Foto an. Zwei Einträge mit demselben Kilometerstand und derselben Energieart tragen ein Warndreieck („doppelt“).
- Warnungen quittieren: Ein Klick auf ein Warndreieck oder Fragezeichen in der Liste zeigt die Erklärung mit **Quittieren**. Danach ist die Warnung ausgeblendet, solange der Hinweis genau derselbe bleibt; ändert sich ein Wert, erscheint sie wieder. Alle Spalten mit demselben Hinweis werden zusammen quittiert.
- Tacho-Foto abgelehnt: Ein Eintrag, dessen Datum nur der Upload-Zeitpunkt ist (aus Säulen-Foto und Tacho angelegt), zählt bei der Reihenfolge der Kilometerstände nicht mehr als „späterer“ Eintrag. Wird ein von der KI gelesener Stand doch als unplausibel verworfen, sagt der Bot den Wert und den Grund („passt nicht zur Reihenfolge der Einträge“) statt „nichts lesbar“, das Panel zeigt es im Dialog, und das Log enthält eine Warnung.
- Liste: Zwei Einträge derselben Energieart mit gleicher Menge und gleichem Betrag (sehr wahrscheinlich derselbe Beleg zweimal) tragen beide ein **Warndreieck** in Menge, Preis und Betrag; der Tooltip nennt die Nummer des anderen Eintrags.
- Beleg nach Säule und Tacho: Kommt zu einem gerade erst angelegten Eintrag (innerhalb von 6 Stunden, z. B. aus Säulen-Foto und Tacho) derselbe Beleg mit gleicher Menge und gleichem Betrag, wird er diesem Eintrag zugeordnet: Datum, Uhrzeit, Station und Preis vom Beleg gelten, es entsteht kein zweiter Eintrag. Bei älteren Einträgen wird wie bisher nachgefragt.
- Plug-in-Hybrid: Plausibilitätsprüfung berücksichtigt den Wechsel von Benzin und Strom: kein Warndreieck für den Verbrauch einzelner Einträge, keine Verbrauchsprüfung der Kilometerstände auf Fotos, stattdessen der gemeinsame Verbrauch ab 300 km, nur zu hohe Werte (über 60 kWh/100 km) werden gemeldet.
- Liste: unplausible Werte tragen ein **Warndreieck** (Menge × Preis passt nicht zum Betrag, ungewöhnlicher Preis, Menge über Tank/Akku, Kilometerstand unter dem vorigen oder mehr als 5000 km darüber, ungewöhnlicher Verbrauch), fehlende Angaben ein **Fragezeichen** (Menge, Betrag, Kilometerstand; bei Zubehör Betrag und Kilometerstand). Die Erklärung steht im Tooltip. Zubehör bekommt den zuletzt bekannten Kilometerstand (grau, kursiv), ein Tacho-Foto direkt danach ersetzt ihn; wie beim Tanken.
- Fehlerhaft gelesene Beleg-Werte werden repariert: Fehlt bei einem Säulen-Display der Dezimalpunkt oder ist genau ein Wert falsch gelesen (z. B. Menge 2,6 statt 21,60), rechnet die App ihn aus den beiden anderen aus, wenn es dafür genau eine übliche Erklärung gibt.
- KI: Funktioniert mit Claude (Anthropic) genauso wie mit Gemini. Die Meldung bei Überlastung nennt keinen Anbieter mehr, erkennt auch Claude (529) und „entity_not_found“ kurz nach dem HA-Start und versucht es mehrmals. Existiert die in den globalen Einstellungen gewählte KI-Aufgabe nicht mehr, weicht die Integration mit einer Log-Warnung auf eine andere aus.
- Doppelte Belege: Schickt man denselben Beleg noch einmal (gleiche Menge und gleicher Betrag, mit Datum am selben Tag, ohne Datum wie bei einem Säulen-Display innerhalb von 3 Tagen), legt die App keinen zweiten Eintrag an, sondern fragt nach: „ja“ ordnet das Foto dem vorhandenen Eintrag zu, „nein“ verwirft es. Zubehör ist ausgenommen.
- Tacho-Foto vor dem Beleg: Liegt der Kilometerstand mehr als 50 km über dem des zeitlich nächsten Eintrags (der schon einen eigenen Stand hat), legt die App einen neuen Eintrag an und ordnet den Beleg danach diesem zu, statt den Tacho als Zusatzfoto am vorigen Eintrag abzulegen (reiner Foto-Betrieb).
- Panel live: Trifft im Hintergrund ein Foto ein (Telegram, WhatsApp), erscheint oben „Foto wird gelesen …“, danach die Antwort des Bots als Meldung am unteren Rand, die Liste wird sofort aktualisiert und springt zur neuen Zeile. Bisher dauerte es bis zu einer Minute.
- Telegram-Einrichtung: Hinweis, dass der Bot in einer Gruppe **zum Administrator** gemacht werden muss, wenn Fotos nicht ankommen (README Englisch und Deutsch). Die Tacho-Testbilder im Ordner `test_images_hybrid` sind besser lesbar (große Kilometeranzeige ohne Geister-Segmente).
- Konfiguration: Die Akku-Felder (Ladestand in %, Akkugröße in kWh) erscheinen nur noch in einem eigenen Schritt, wenn „Plug-in-Hybrid“ angekreuzt ist; wird das Häkchen entfernt, verschwinden sie. Behoben: das geplante Neu-Einlesen der Fotos wurde aus dem falschen Thread gestartet.
- Testbilder für den Plug-in-Hybrid in `tests/test_images_hybrid/`: 10 zusammenpassende Vorgänge (Zapfsäule oder Ladesäule, Beleg, Tacho-Foto, schief und teils verwackelt) plus 10 Bilder aus ganz Europa in Landessprache und -währung.
- Neuer Fahrzeugtyp **Plug-in-Hybrid** (Häkchen beim Fahrzeug): Kraftstoff (l) und Strom (kWh) in einer Liste, Ladebelege werden von der KI erkannt, Verbrauch getrennt je Energieart (l/100 km und kWh/100 km), zweiter Sensor „Stromverbrauch“, Auswahl „Strom“ im Bearbeiten-Dialog. Automatische Ladeerkennung über einen zweiten Sensor (Akku-Ladestand in %, Akkugröße in kWh) neben der Tank-Erkennung; Rekuperation wird nicht als Laden gezählt (Bewegung über 200 m per GPS oder 1 km per Kilometerstand), auch beim reinen Elektroauto.
- Liste: Notiz und Art (Zubehör) erscheinen beim Darüberfahren mit der Maus als Blase mit dem vollständigen Text (am Handy per Tippen); der Browser-Tooltip am Symbol entfällt.
- Fotos: sprechende Dateinamen wie `2026-10-15_1240_Oel_Cerpaci-stanice-Zlaty-Lan.jpg` (Datum, Art, Händler) statt zufälliger Namen, auch in `originals/`. Vorhandene Fotos werden beim ersten Start einmalig umbenannt und die Einträge angepasst.
- Fotos: stärker komprimiert (Zuschnitt max. 1400 px / Qualität 80, Original max. 1800 px / Qualität 82, progressives JPEG). Vorhandene größere Dateien werden einmalig verkleinert, wenn das mindestens 20 % spart.
- KI überlastet (Google 503): bis zu vier Versuche mit Pause, dann deutliche Warnung statt „nichts lesbar“; es wird nichts gespeichert.
- Bearbeiten-Dialog: Auswahl „Art“ (Kraftstoff/Strom oder Zubehör / Verbrauchsmaterial), auch nachträglich umstellbar (z. B. ein Ölbon, der als Tanken gelesen wurde); bei Zubehör erscheinen Bezeichnung und Einheit.
- Verbrauchsmaterial: Kategorie-Auswahl mit AdBlue, Öl, Scheibenreiniger und Waschen (füllt Bezeichnung und Einheit vor) und „Sonstiges“ zum freien Eintragen. Verbrauchsmaterial fließt nicht in den Verbrauch ein.
- Kilometerstand: feste Rangfolge der Quellen. 1. Entität des Autos, 2. Foto vom Tacho, 3. Stand auf der Quittung (oft von Hand eingetragen, daher nie vor den anderen). Ein von Hand gesetzter Stand gewinnt immer. Der Sensorwert gilt nur, wenn der Eintrag zeitlich zum Anlegen passt (sonst Belege, die später hochgeladen werden, mit dem falschen aktuellen Stand).
- „Eintrag von Hand“: Das Kamera-Symbol liest ein Foto per KI und trägt die gefundenen Werte in den offenen Dialog ein (Datum, Menge, Preis, Betrag, Kilometerstand, Notiz). Erst „Speichern“ legt den Eintrag mit dem Foto an. Liefert das Foto keine Daten, fragt ein Dialog, ob es trotzdem zur Dokumentation behalten oder verworfen wird. Der Foto-Button im Bearbeiten-Dialog fragt immer nach Kamera oder Galerie; das Notiz-Symbol in der Liste entfällt (die Notiz steht im Dialog). Ein neuer Eintrag von Hand beginnt mit „Zubehör / Sonstiges“.
- Unlesbares Foto (normaler Upload): Rückfrage mit „Nur Dokumentation“ (Eintrag ohne Zahlen, zählt nicht in den Verbrauch) oder „Löschen“.
- Fremdwährung: Belege in anderen Währungen (CHF, PLN, CZK, GBP, SEK, DKK …) werden zum EZB-Tageskurs des Belegdatums (frankfurter.dev) in Euro umgerechnet. Originalbetrag, -währung und Kurs stehen in der Notiz. Ist kein Kurs abrufbar, bleiben die Werte unverändert und die Notiz warnt.
- Handy: Der Eintragsdialog öffnet ohne Tastatur, zeigt Mengen und Preise zweispaltig und passt sich der Bildschirmtastatur an.
- Testbilder `tests/test_images_zubehoer/`: 13 Dummy-Belege für Verbrauchsmaterial von Tankstellen und Autoteile-Händlern aus ganz Europa.

## 0.1.80
- Panel: Die Liste lässt sich per Klick auf jede Spaltenüberschrift sortieren (erster Klick aufsteigend ▲, jeder weitere wechselt auf absteigend ▼); leere Werte stehen immer unten, die Wahl wird pro Browser gemerkt, ein Doppelklick auf einen Spaltenteiler setzt sie zurück. Standard ohne Wahl: Datum absteigend, der neueste Eintrag steht oben und trägt die höchste Nummer. Wie im Device und Entity Inventory.
- Dokumentation: Kapitel „KI für die Belegerkennung einrichten“ (AI Task, Gemini, Links zu Home Assistant) und ein Beispiel-Ausdruck (Liste und Belege, als Bild und PDF).

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
