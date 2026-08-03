# Faktenübersicht für die Ergebniskapitel

Stand 2026-08-03. Alle Zahlen sind aus der Live-Datenbank und den Laufprotokollen
gerechnet, nicht geschätzt. Jede Zahl hat unten eine Quellenangabe, damit du sie
im Zweifel nachrechnen kannst.

Das hier ist **Material, kein Text.** Die Formulierungen musst du selbst schreiben.

---

## 1. Datenbasis

| | Wert |
|---|---|
| Signale gesamt (90 Tage) | 3361 |
| davon System A (masfactory) | 1008 |
| davon System B (hermes) | 2335 |
| davon manuell kuratiert | 16 |
| Läufe gesamt | 261 |
| Akteure | 40 |
| Erhebungszeitraum | 2026-05-04 bis 2026-08-02 |

**Wichtig für die Interpretation:** Die Monate Mai und Juni enthalten
Duplikate. Bis zur Korrektur v0.4.36 hat System A denselben Fund jede Nacht neu
gespeichert, weil der Duplikat-Schlüssel auf einem Textfeld beruhte, das das
Sprachmodell jedes Mal anders formulierte.

| Monat | System A: Zeilen | davon eigenständig | Aufblähung |
|---|---|---|---|
| Mai | 253 | 52 | 4.9-fach |
| Juni | 491 | 82 | 6.0-fach |
| Juli | 259 | 259 | 1.0-fach |

**Empfehlung: Für alle Mengenvergleiche nur Juli verwenden.** Das ist der erste
saubere Monat und der einzige vollständige.

---

## 2. Die vier Kennzahlen

### 2.1 Überschneidung der Systeme (inter-system agreement)

| | Wert |
|---|---|
| Macro-Jaccard | **0.043** |
| Gewichteter Jaccard | 0.039 |
| Akteure, die beide Systeme abgedeckt haben | 39 von 40 |

**Was das heisst:** Von allem, was die beiden Systeme zusammen gefunden haben,
haben sie nur rund 4 Prozent gemeinsam gefunden. Bei gleicher Aufgabe, gleicher
Akteursliste, gleichem Sprachmodell und gleicher Suchmaschine.

Das ist deine stärkste Einzelzahl. Sie sagt: **Die Architektur bestimmt, was
gefunden wird — nicht die Aufgabe und nicht das Modell.**

### 2.2 Reproduzierbarkeit

| System | Jaccard-Mittel | Vergleiche | Spanne |
|---|---|---|---|
| System A | **0.500** | 12 | 0.02 bis 0.62 |
| System B | **0.120** | 12 | 0.00 bis 0.50 |

**Was das heisst:** Lässt man dasselbe System zweimal laufen, findet System A
etwa die Hälfte derselben Quellen wieder, System B nur ein Achtel. System A ist
rund **4-mal reproduzierbarer**.

Das passt zur Bauweise: System A fragt jede Nacht dieselbe feste Quellenliste ab,
System B sucht jedes Mal frei im Web.

### 2.3 Token-Effizienz (Juli 2026)

| System | Signale | Token | Signale pro 1000 Token |
|---|---|---|---|
| System A | 259 | 25,937,521 | **0.0100** |
| System B | 1368 | 96,649,854 | **0.0142** |

**Verhältnis: System B ist 1.42-mal effizienter.**

Achtung: In `eval-results/results.md` steht noch **8.9-fach**. Diese Zahl ist
falsch, siehe Abschnitt 3.1. Nimm die 1.42.

### 2.4 Klassifikationsqualität

**Offen — wartet auf dein Gold-Set.** Sobald `data/gold/labels.yaml` existiert,
liefert die Auswertung Precision, Recall, F1 und Cohens Kappa je System.

---

## 3. Korrekturen, die du kennen musst

Diese drei Punkte betreffen Zahlen, die vorher anders berichtet wurden. Wenn du
alte Notizen hast, sind sie überholt.

### 3.1 Token-Effizienz: 8.9-fach war ein Messfehler

Die Datenbank enthielt Tokenzahlen für **99 Prozent** der Läufe von System A,
aber nur für **26 Prozent** der Läufe von System B. Die Signale wurden dagegen
bei beiden vollständig gezählt. System B bekam also einen fast vollständigen
Zähler und einen stark unvollständigen Nenner.

Die Ursache: Am 2026-06-10 wurde System B von der eigenen Python-Implementierung
auf die offizielle Hermes-CLI umgestellt. Die alte Version hat Tokenzahlen nach
Supabase geschrieben, die neue nicht. **Seit dem 2026-06-09 gibt es dort keinen
einzigen neuen Tokeneintrag für System B.** Die verbliebenen Einträge stammen
also von einem System, das gar nicht mehr läuft.

Die echten Zahlen liessen sich retten: Die Hermes-CLI führt eine eigene Datenbank
(`state.db`, Tabelle `sessions`) und protokolliert dort `input_tokens` und
`output_tokens`. Daraus stammen die 96,6 Mio. Token für Juli.

**Für die Arbeit:** Das ist ein gutes Beispiel für das Limitationskapitel. Eine
Architekturumstellung hat still eine Messgrösse abgeschaltet, und der Fehler war
in der Zahl selbst nicht sichtbar — er sah nur nach einem sehr guten Ergebnis aus.

### 3.2 Reproduzierbarkeit war vorher nicht messbar

Die alte Berechnung verglich, welche Signale einem Lauf **zugeordnet** waren.
Signale werden aber dem Lauf zugeordnet, der sie **zuerst** gespeichert hat.
Findet ein späterer Lauf dieselbe Quelle nochmal, speichert er nichts, und ihm
wird nichts zugeordnet.

Zwei aufeinanderfolgende Läufe konnten sich deshalb rechnerisch fast nie
überschneiden. Für System A kam gar kein Ergebnis heraus, für System B eine
künstlich niedrige 0.155.

Jetzt wird verglichen, was jeder Lauf **gefunden** hat, aus den Laufprotokollen.
Daher die Werte in 2.2.

### 3.3 Die Auswertung sah nur ein Drittel der Daten

Die Datenbankabfrage hatte eine stille Obergrenze von 1000 Zeilen. Im
90-Tage-Fenster liegen 3361 Signale. Alle Kennzahlen wurden also monatelang auf
**31 Prozent** der Daten gerechnet, ohne Fehlermeldung.

Verschärfend: Sortiert wurde nach Datum absteigend, es blieben also immer die
neuesten Zeilen übrig. Das ist keine Zufallsstichprobe, und weil die beiden
Systeme unterschiedlich viel pro Nacht produzieren, hat es das Verhältnis
zwischen ihnen verschoben.

---

## 4. Limitationen

Fünf Punkte, alle belegt. Das ist Material für das Kapitel „Grenzen der Arbeit".

### 4.1 System B klassifizierte ausserhalb des Schemas

Im Juli trugen **1304 von 1484** Signalen von System B (**88,5 Prozent**) eine
Kategorie, die es im Schema nicht gibt — insgesamt 214 erfundene Bezeichnungen.
System A lag im selben Zeitraum bei **0 Prozent**.

Die Ursache war nicht das Modell, sondern die Anweisung: Die Skill-Datei
bezeichnete das Feld als „free-text sub-category", und zwei ihrer vier Beispiele
verwendeten selbst ungültige Werte. Der Agent hat exakt das getan, was dort stand.

Nebenwirkung: Die Bewertungsformel schlägt bei unbekannten Kategorien auf
Standardwerte zurück. Die Kennzahlen von System B beruhten also weitgehend auf
Ersatzkonstanten statt auf den signalisierungstheoretischen Gewichten.

Nach der Korrektur am 2026-08-02: **0,0 Prozent** im ersten vollständigen Lauf.
Gleiches Modell, andere Anweisung.

**Formulierungsvorschlag für die Kernaussage:** Die Klassifikationstreue eines
agentischen Systems war durch die Spezifikation begrenzt, nicht durch die
Fähigkeit des Modells.

### 4.2 System B bricht bei über der Hälfte der Akteure ab

Der Agent hat pro Akteur 20 Iterationen. Wenn sie aufgebraucht sind, wird er
mitten im Vorgang abgeschnitten und schreibt sein Ergebnis nie auf. Alles, was er
gefunden hat, ist verloren.

| Nacht | Akteure | davon abgebrochen |
|---|---|---|
| 2026-07-29 | 40 | 20 (50 %) |
| 2026-07-30 | 40 | 27 (67 %) |
| 2026-07-31 | 40 | 29 (72 %) |
| 2026-08-01 | 40 | 22 (55 %) |
| 2026-08-02 | 40 | 23 (57 %) |

**Ungelöst.** Ein Korrekturversuch am 2026-08-02 (ausdrückliche Anweisung, das
Ergebnis rechtzeitig zu schreiben) hat messbar nichts gebracht: 57 Prozent statt
55 Prozent, also innerhalb der normalen Schwankung.

Konsequenz für die Arbeit: Die gemessene Ausbeute von System B ist durch ein
Budget begrenzt, nicht durch das, was auffindbar wäre. Jede Aussage über die
Trefferquote von System B braucht diesen Vorbehalt.

### 4.3 System A lief unter halber Konfiguration

Vier Stellen im Code gaben unterschiedliche Standardwerte für dieselben
Einstellungen an, und der Server hatte die niedrigsten übernommen: 5 statt 10
arXiv-Treffer, 3 statt 5 Unterseiten pro Akteur.

Zusätzlich hatte der arXiv-Abruf keine Wiederholung bei Fehlern. Eine einzelne
Zeitüberschreitung kostete den betroffenen Akteur seinen gesamten
Publikationskanal für diesen Tag. Ergebnis: **System A hat im gesamten Juli null
arXiv-Signale erfasst, System B im selben Zeitraum 151.** Das sieht nach einem
Architekturunterschied aus und ist keiner.

Beides am 2026-08-02 korrigiert.

### 4.4 Kein Vergleich gleicher Budgets möglich

System A misst sein Budget in „Dokumenten pro Quelle", System B in
„Iterationen pro Akteur". Diese Einheiten lassen sich nicht ineinander
umrechnen. Man kann die Budgets also nicht gleichsetzen, sondern nur beide offen
angeben und die Unvergleichbarkeit als Einschränkung benennen.

### 4.5 Kein Integrationstest gegen die echten Dienste

Alle Testläufe arbeiten mit Attrappen. Datenbank, Sprachmodell und Suchmaschine
werden von keinem automatischen Test angesprochen. Genau deshalb sind die Fehler
in 3.1 bis 3.3 so lange unentdeckt geblieben.

---

## 5. Phasengrenze am 2026-08-02

An diesem Tag wurden drei Dinge verändert, die beeinflussen, **was** gemessen
wird. Daten davor und danach sind bei den betroffenen Kennzahlen nicht
vergleichbar.

| Änderung | betrifft | betroffene Kennzahl |
|---|---|---|
| System B an das Schema gebunden | System B | alles, was auf Kategorien beruht |
| System A auf dokumentierte Konfiguration zurückgesetzt | System A | Menge und Abdeckung |
| arXiv-Wiederholung ergänzt | System A | Publikationskanal |

Zwei Sätze im Methodenteil genügen, aber sie müssen drinstehen. Sonst wirkt es
wie ein Fehler statt wie eine bewusste Entscheidung.

---

## 6. Der rote Faden

Wenn du eine übergreifende Aussage brauchst, ist es diese:

> In einem Feld ohne gemeinsame Messlatte versagt das Messinstrument auf dieselbe
> stille Art wie die untersuchten Systeme. Eine Abfrage, die ein Drittel der
> Daten zurückgibt, ohne es zu sagen. Eine Kennzahl, die etwas anderes misst als
> ihr Name behauptet. Eine Architekturumstellung, die eine Messgrösse abschaltet.
> Keiner dieser Fehler hat je eine Fehlermeldung erzeugt.

Das ist ein eigenständiger Beitrag und kein Eingeständnis. Wer eine Vergleichs-
studie über nicht-kommensurable Systeme baut, muss zuerst zeigen, dass das
Messgerät funktioniert.

---

## 7. Zum Nachrechnen

Alle Kennzahlen ausser System Bs Token:

```bash
cd /opt/mas-deeptech-research && docker compose run --rm --no-deps --entrypoint sh -v /opt/mas-deeptech-research/systems/evaluation:/eval -v /opt/mas-deeptech-research/data:/data -v /opt/mas-deeptech-research/systems/hermes:/hermes:ro -v mas-deeptech-research_hermes_state:/hermes_state:ro reports -c 'pip install -q pandas supabase scikit-learn pyarrow; cd /eval && PYTHONPATH=/eval EVAL_OUTPUT_DIR=/data/eval EVAL_WINDOW_DAYS=90 EVAL_MASF_AUDIT_DIR=/data/raw/runs EVAL_HERMES_RUNS_DIR=/hermes_state/state/runs EVAL_HERMES_PERSISTER=/hermes/scripts/persist_signals.py python -m eval_app.runner all'
```

System Bs Tokenverbrauch aus seiner eigenen Datenbank:

```bash
docker run --rm -v mas-deeptech-research_hermes_state:/opt/data:ro --entrypoint sh mas-deeptech-research/hermes:0.4.0 -c "cp /opt/data/state.db /tmp/s.db && /opt/hermes/.venv/bin/python -c \"import sqlite3;c=sqlite3.connect('/tmp/s.db');print(c.execute(\\\"select sum(coalesce(input_tokens,0)), sum(coalesce(output_tokens,0)) from sessions where date(started_at,'unixepoch') like '2026-07%'\\\").fetchone())\""
```

Belege im Repository:

| Aussage | Quelle |
|---|---|
| Alle Kennzahlen | `eval-results/results.md`, `eval-results/results.json` |
| Prüfprotokoll und Befunde | `docs/architecture-analysis.md`, Abschnitte 9 und 10 |
| Warum Reproduzierbarkeit neu gerechnet wird | `systems/evaluation/eval_app/found_sets.py`, Kopfkommentar |
| Taxonomie-Korrektur | Commit `3025c2b` |
| Konfiguration von System A | Commit `71cab3a` |
