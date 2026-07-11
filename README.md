# iONA für Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://hacs.xyz)
[![Version](https://img.shields.io/badge/Version-2.1.1-blue.svg?style=for-the-badge)](https://github.com/tinohox/iona-ha/releases)
[![Lizenz](https://img.shields.io/badge/Lizenz-MIT-green.svg?style=for-the-badge)](https://github.com/tinohox/iona-ha/blob/main/LICENSE)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.11+-blue.svg?style=for-the-badge&logo=homeassistant)](https://www.home-assistant.io/)

> **⚠️ Experimentelles Projekt – Nutzung auf eigene Gefahr**
>
> Diese Integration ist ein **privates Hobbyprojekt** einer Einzelperson und befindet sich in **aktiver Entwicklung**. Sie ist **kein offizielles Produkt** der enviaM oder eines anderen Unternehmens. Es wird **keine Garantie** für Funktionalität, Korrektheit oder Verfügbarkeit übernommen. Die Nutzung erfolgt **auf eigene Verantwortung**.

Deine **iONA Box** liefert Energiedaten direkt an **Home Assistant** – mit Live-Verbrauchswerten, Zählerständen und voller Integration ins Energie-Dashboard.

---

## English (quick)

This custom Home Assistant integration connects your **iONA box** to Home Assistant and provides live power and energy meter sensors. Optionally it supports the dynamic tariff **"mein Strom Vision"** (enviaM): 15-minute spot prices, gross end-consumer prices and automatic cheapest-time-window optimization (see the German section below for details).

**Requirements**

- Home Assistant 2024.11.0+
- HACS installed
- iONA box reachable in your LAN (static IP recommended)
- iONA app credentials (email + password)

**Install via HACS (Custom Repository)**

1. Open HACS → Integrations → (⋮) → Custom repositories
2. Add `https://github.com/tinohox/iona-ha` as category **Integration**
3. Download **iona-ha**
4. Restart Home Assistant
5. Settings → Devices & Services → Add integration → search for **iona-ha**

---

---

## Auf einen Blick

| | Feature |
|---|---|
| ⚡ | **Live-Verbrauch** – Momentanleistung (Watt) direkt von der iONA Box (Standard: alle 5 Sekunden, einstellbar) |
| 📊 | **Zählerstand** – Gesamtverbrauch & Einspeisung (kWh), kompatibel mit dem HA Energie-Dashboard |
| 🔄 | **Dual-Datenquelle** – Primär lokal via LAN, automatischer Web-Fallback bei Verbindungsproblemen |
| 💶 | **Dynamischer Stromtarif** – Optionale Unterstützung für „mein Strom Vision" von enviaM: Spotpreise in 15-Minuten-Auflösung, Brutto-Endkundenpreise und automatische Suche nach dem günstigsten Zeitfenster |
| 🃏 | **Custom Lovelace Cards** – Fertige Kacheln für Verbrauch (mit 24-h-Sparkline) und Vision Tools, automatisch registriert |
| 🛡️ | **HACS-Update-sicher** – Einstellungen und Tokens werden automatisch gesichert und nach Updates wiederhergestellt |
| 🔔 | **Automatische Benachrichtigungen** – Hinweis in der HA-Oberfläche bei Authentifizierungsproblemen, nicht erreichbarer iONA Box oder fehlenden Vision-Preisdaten (Edge-Trigger: nur einmal pro Ausfall, automatisches Verschwinden bei Recovery) |
| ⚙️ | **Einfache Einrichtung** – Konfiguration komplett über die Home Assistant UI |

---

## Voraussetzungen

- **Home Assistant** 2024.11.0 oder neuer
- **[HACS](https://hacs.xyz/docs/use/download/download/)** installiert
- **iONA Box** im Heimnetzwerk (feste IP-Adresse empfohlen)
- **iONA-App Zugangsdaten** (E-Mail & Passwort)

---

## Installation

### Über HACS (empfohlen)

1. **HACS** öffnen → **Integrationen** → Menü (⋮) → **Benutzerdefinierte Repositories**
2. Repository-URL eingeben: `https://github.com/tinohox/iona-ha` → Kategorie: **Integration**
3. **iona-ha** suchen und herunterladen
4. **Home Assistant neu starten**
5. **Einstellungen → Geräte & Dienste → Integration hinzufügen** → nach **iona-ha** suchen
6. iONA Box IP und Zugangsdaten eingeben
7. **Home Assistant neu starten**

### Manuell

```bash
# Repository klonen
git clone https://github.com/tinohox/iona-ha.git

# Inhalt nach custom_components/iona/ kopieren
cp -r iona-ha/* /config/custom_components/iona/
```

Anschließend Home Assistant neu starten und über die UI konfigurieren.

---

## Konfiguration

Die komplette Einrichtung erfolgt über die **Home Assistant UI** – es müssen keine YAML-Dateien bearbeitet werden.

### Ersteinrichtung

| Parameter | Beschreibung | Beispiel |
|-----------|-------------|--------|
| **iONA Box IP** | Lokale IP-Adresse der iONA Box | `192.168.1.100` |
| **Benutzername** | E-Mail der iONA App | `max@example.com` |
| **Passwort** | Passwort der iONA App | `••••••••` |

### Erweiterte Optionen (unter Optionen)

| Parameter | Beschreibung | Standard |
|-----------|-------------|----------|
| **LAN-Abfrageintervall** | Wie oft die iONA Box lokal abgefragt wird | `5` Sekunden |
| **Web-Abfrageintervall** | Wie oft Web-Daten als Fallback abgerufen werden | `300` Sekunden |

> 💡 **Tipp:** Alle Einstellungen lassen sich nachträglich unter **Einstellungen → Geräte & Dienste → iona-ha → Optionen** ändern. Änderungen werden sofort übernommen – kein Neustart nötig.

---

## Sensoren & Entitäten

Die Integration erstellt automatisch ein Gerät **„mein Stromzähler"** mit folgenden Sensoren:

### Stromzähler

| Sensor | Einheit | Beschreibung |
|--------|---------|-------------|
| **Gesamtverbrauch** | kWh | Bezogene Energie – für das Energie-Dashboard geeignet |
| **Gesamteinspeisung** | kWh | Eingespeiste Energie (z. B. PV-Anlage) |
| **Momentanleistung** | W | Aktuelle Leistungsaufnahme in Echtzeit |
| **Datenquelle** | – | Zeigt an, woher die Daten aktuell stammen (siehe unten) |

### 🔌 Datenquelle: LAN vs. WEB

Der Sensor **„Stromzähler Datenquelle"** zeigt an, über welchen Weg die Zählerdaten aktuell bezogen werden:

| Wert | Icon | Bedeutung |
|------|------|-----------|
| **LAN** | 🖧 `mdi:lan` | Daten kommen **direkt von der iONA Box** im lokalen Netzwerk (Standard: alle 5 Sekunden) |
| **WEB** | ☁️ `mdi:cloud` | Daten werden über die **enviaM Web-API** bezogen (Fallback, Standard: alle 5 Minuten) |

**So funktioniert die automatische Umschaltung:**

Die Integration fragt die iONA Box **primär lokal über das LAN** ab – das ist schneller, genauer und erzeugt keine externe API-Last. Sollte die lokale Verbindung ausfallen (z. B. Box nicht erreichbar, Netzwerkprobleme), schaltet die Integration **automatisch auf die Web-API um**, damit die Daten weiterhin aktuell bleiben.

Sobald die LAN-Verbindung wieder steht, wechselt die Datenquelle automatisch zurück auf **LAN**. Der Sensor zeigt also jederzeit transparent, woher die aktuellen Werte kommen.

> 💡 **Idealzustand:** Die Datenquelle zeigt dauerhaft **LAN**. Wird dauerhaft **WEB** angezeigt, prüfe ob die iONA Box im Netzwerk erreichbar ist und die IP-Adresse in den Integrationsoptionen stimmt.

---

## Energie-Dashboard

Die Integration ist direkt mit dem **Home Assistant Energie-Dashboard** kompatibel:

1. **Einstellungen → Energie** öffnen
2. Im Abschnitt **Stromverbrauch** → **Verbrauch hinzufügen** → Sensor **Stromzähler Gesamtverbrauch** auswählen
3. Optional: **Stromzähler Gesamteinspeisung** als Einspeise-Sensor hinzufügen

Die Sensoren liefern `device_class: energy` und `state_class: total_increasing` – sie werden vom Energie-Dashboard automatisch erkannt.

---

## Lovelace Cards

Die Integration enthält zwei fertige **Custom Lovelace Cards**, die nach einem HA-Neustart automatisch verfügbar sind – ohne manuelle Ressourcen-Einträge oder YAML-Änderungen.

### iONA Power Card (`iona-card`)

Zeigt Momentanleistung, heutigen Verbrauch und einen 24-Stunden-Sparkline als Kurve. Optional: aktueller Strompreis und Preis-Balkendiagramm der letzten 12 Stunden (nur mit Vision).

> 💡 **Antippbar:** Leistungsanzeige, Sparkline, Verbrauchs-/Einspeisungs-Kacheln, LAN/WEB-Badge und Preiszeile öffnen per Klick den jeweiligen Sensor mit Verlaufsgraph (More-Info-Dialog).

```yaml
type: custom:iona-card
entity_power: sensor.stromzahler_momentanleistung
entity_consumed: sensor.stromzahler_gesamtverbrauch
entity_fed_back: sensor.stromzahler_gesamteinspeisung
entity_source: sensor.stromzahler_datenquelle
# Optional – nur wenn "mein Strom Vision" aktiv ist:
# entity_price: sensor.stromzahler_aktueller_preis
```

> Die korrekten Entitätsnamen findest du unter **Einstellungen → Geräte & Dienste → iona-ha → Entitäten**.

| Konfigurationsschlüssel | Pflicht | Beschreibung |
|---|---|---|
| `entity_power` | ✅ | Sensor für Momentanleistung (W) |
| `entity_consumed` | ❌ | Sensor für Gesamtverbrauch (kWh); `entity_energy` funktioniert weiterhin als Alias |
| `entity_fed_back` | ❌ | Sensor für Gesamteinspeisung (kWh) |
| `entity_source` | ❌ | Sensor für die Datenquelle (LAN/WEB-Badge) |
| `entity_price` | ❌ | Sensor für aktuellen Preis – nur mit Vision aktiviert |

### iONA Vision Tools Card (`iona-vision-card`)

Steuerungs-Kachel für die Vision-Optimierung: günstigste Startzeit (groß dargestellt), Durchschnittskosten, Endzeit mit Zeitpunkt der nächsten Suche, Zeitraum-Slider, Späteste-Startzeit-Slider, „Neuberechnung nach Ablauf"-Slider, Neu-berechnen-Button und Nacht-Modus-Schalter.

> 💡 **Antippbar:** Startzeit, Datum/Countdown, Kostenzeile sowie die Wert-Labels neben den Slidern öffnen per Klick die jeweilige Entität mit Verlaufsgraph (More-Info-Dialog). Die Slider selbst bleiben Steuerelemente.

> ⚠️ **Nur relevant wenn Vision Tools aktiviert ist.** Ohne aktivierte Vision Tools liefert diese Karte keine Daten.

```yaml
type: custom:iona-vision-card
entity_startzeit: sensor.vision_tools_gunstigste_startzeit_fur_2h
entity_kosten: sensor.vision_tools_durchschnittskosten_fur_die_2h
entity_endzeit: sensor.vision_tools_endzeit_fur_2h
entity_zeitraum: number.mein_strom_vision_tools_vision_tools_zeitraum
entity_vorausschau: number.mein_strom_vision_tools_vision_tools_vorausschau
entity_danach_wieder: number.mein_strom_vision_tools_vision_tools_danach_wieder
entity_berechnen: button.mein_strom_vision_tools_vision_tools_berechnen
entity_nacht: switch.mein_strom_vision_tools_vision_tools_nur_nachtstrom
```

> Die exakten Entitätsnamen hängen vom Gerätenamen in HA ab – im Zweifel unter **Einstellungen → Geräte & Dienste → iona-ha → Entitäten** nachsehen. Seit v2.2.1 löst die Card abweichende IDs automatisch auf (z. B. Bereichs-Präfixe wie `number.energie_mein_strom_...` oder andere `_fur_Xh`-Suffixe) und findet den Endzeit-Sensor auch ohne `entity_endzeit`-Eintrag.

| Konfigurationsschlüssel | Pflicht | Beschreibung |
|---|---|---|
| `entity_startzeit` | ✅ | Sensor für günstigste Startzeit |
| `entity_kosten` | ✅ | Sensor für Durchschnittskosten |
| `entity_zeitraum` | ✅ | Number-Entität für Zeitraum (Stunden) |
| `entity_vorausschau` | ✅ | Number-Entität für späteste Startzeit (Vorausschau) |
| `entity_endzeit` | ❌ | Sensor für das Ende des Zeitfensters (More-Info-Ziel der Endzeit-Zeile) |
| `entity_danach_wieder` | ❌ | Number-Entität für die Wartezeit bis zur Neuberechnung nach Ablauf (0–48 h, `0` = sofort) |
| `entity_berechnen` | ❌ | Button-Entität für manuelle Neuberechnung |
| `entity_nacht` | ❌ | Switch für Nur-Nachtstrom-Modus (20–07 Uhr) |

### Karte zum Dashboard hinzufügen

1. Dashboard öffnen → **Bearbeiten** (Stift-Symbol oben rechts)
2. **Karte hinzufügen** → **YAML** wählen
3. Obige Konfiguration einfügen und Entitätsnamen anpassen
4. **Speichern**

---

## mein Strom Vision – dynamischer Stromtarif (optional)

Die Integration unterstützt den dynamischen Stromtarif **mein Strom Vision** von enviaM. Die Vision-Funktionen sind **standardmäßig deaktiviert** und werden nur genutzt, wenn du sie in den Integrationsoptionen einschaltest – sinnvoll ist das nur mit einem aktiven „mein Strom Vision"-Vertrag.

**Ohne aktiviertes Vision** läuft die Integration vollständig normal mit allen Stromzähler-Sensoren.

### Was ist „mein Strom Vision"?

Bei einem dynamischen Tarif ist der Strompreis nicht fix, sondern folgt dem **Börsenpreis (EEX-Spotmarkt)** – in **15-Minuten-Intervallen**. Nachts, an Wochenenden oder bei viel Wind- und Sonnenstrom ist Strom oft deutlich günstiger. Wer flexible Verbraucher (E-Auto, Wärmepumpe, Waschmaschine, Spülmaschine) gezielt in günstige Zeitfenster verschiebt, spart bares Geld.

Die Integration übernimmt dabei die komplette Rechenarbeit:

1. **Spotpreise abrufen** – die EEX-Viertelstundenpreise werden alle 30 Minuten von der enviaM-API geladen (typisch liegen die Preise für den Folgetag ab ca. 14 Uhr vor)
2. **Tarifdaten abrufen** – die fixen Preisbestandteile deines Vertrags (Netzentgelte, Steuern, Umlagen, Abgaben) werden täglich aktualisiert
3. **Bruttopreis berechnen** – Spotpreis + fixe Drittkosten = dein tatsächlicher **Brutto-Endkundenpreis in €/kWh**, für jede Viertelstunde
4. **Günstigstes Zeitfenster finden** – die Vision-Optimierung durchsucht die kommenden Stunden nach dem zusammenhängenden Zeitblock mit dem niedrigsten Durchschnittspreis

### Preissensor

Mit aktiviertem `vision_tariff` erscheint am Gerät **„mein Stromzähler"**:

| Entität | Typ | Beschreibung |
|---|---|---|
| Strompreis für die aktuelle ¼h | Sensor | Aktueller Brutto-Preis in €/kWh (15-Minuten-Auflösung); das Attribut `spot_prices` enthält die komplette Preiskurve für eigene Auswertungen und Diagramme |

### Vision Tools – Zeitfenster-Optimierung

Mit zusätzlich aktiviertem `vision_tools` erscheint das Gerät **„mein Strom Vision Tools"** mit folgenden Entitäten:

| Entität | Typ | Beschreibung |
|---|---|---|
| Günstigste Startzeit | Sensor | Startzeit des günstigsten Zeitfensters (Timestamp – ideal für Automatisierungen) |
| Endzeit | Sensor | Ende des Zeitfensters (Startzeit + Zeitraum, Timestamp – z. B. zum automatischen Abschalten) |
| Durchschnittskosten | Sensor | Ø-Preis im gefundenen Zeitfenster in €/kWh |
| Zeitraum | Number | Gewünschte Nutzungsdauer des Verbrauchers (z. B. 2 h für einen Waschgang) |
| Vorausschau | Number | Wie weit in die Zukunft nach einer Startzeit gesucht wird (max. begrenzt durch die verfügbaren Preisdaten) |
| danach wieder | Number | Wartezeit nach Ablauf des Zeitfensters bis zur nächsten automatischen Suche (0–48 h, `0` = sofort, 1 Minute nach Fensterende) |
| Berechnen | Button | Manuelle Neuberechnung der optimalen Startzeit sofort auslösen |
| Nur Nachtstrom | Switch | Suche auf Nachtzeiten (20–07 Uhr) einschränken |

**So arbeitet die Optimierung:**

- Eine einmal berechnete Startzeit bleibt **eingefroren**, solange sie in der Zukunft liegt – sie springt also nicht ständig um, während eine Automatisierung darauf wartet. Nur der aktuelle Preis wird weiter aktualisiert.
- Ist das Zeitfenster abgelaufen, entscheidet **„danach wieder"**, wann automatisch neu gesucht wird: Bei `0` wird **sofort** (1 Minute nach Fensterende) das nächste günstige Zeitfenster berechnet. Bei z. B. `8` wartet die Suche 8 Stunden nach Fenster-Ende. Die Neuberechnung erfolgt minutengenau – nicht erst beim nächsten 5-Minuten-Takt.
- Änderungen an **Zeitraum**, **Vorausschau** oder dem **Nachtstrom**-Schalter stoßen die Berechnung direkt an. Der **Berechnen**-Button erzwingt jederzeit eine sofortige Neuberechnung.

> ⚠️ **Wichtig für Automatisierungen:** Bei `danach wieder = 0` springt die Startzeit direkt nach Fensterende auf das nächste günstige Fenster – unter Umständen nur wenige Minuten später. Deine Automatisierung sollte daher selbst prüfen, ob das Gerät überhaupt startbereit ist (z. B. Bedingung „Waschmaschine beladen/bereit"), sonst startet es unmittelbar wieder.

**Beispiel-Automatisierung** – Steckdose zum günstigsten Zeitpunkt einschalten:

```yaml
automation:
  - alias: "Waschmaschine im günstigsten Zeitfenster starten"
    trigger:
      - platform: time
        at: sensor.vision_tools_gunstigste_startzeit_fur_2h
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.steckdose_waschmaschine

  - alias: "Steckdose am Ende des Zeitfensters ausschalten"
    trigger:
      - platform: time
        at: sensor.vision_tools_endzeit_fur_2h
    action:
      - service: switch.turn_off
        target:
          entity_id: switch.steckdose_waschmaschine
```

> 💡 Die passende **Lovelace-Karte** für die Steuerung ist die [iONA Vision Tools Card](#iona-vision-tools-card-iona-vision-card) – inklusive Slider, Berechnen-Button und Countdown zur Startzeit.

### Vision aktivieren

1. **Einstellungen → Geräte & Dienste → iona-ha → Optionen**
2. „mein Strom Vision aktivieren" einschalten (`vision_tariff` – Preissensor & Preisdaten)
3. Optional: „Vision Tools aktivieren" (`vision_tools` – Zeitfenster-Optimierung mit allen Steuerentitäten)
4. Änderungen speichern – die Integration lädt automatisch neu

> ⚠️ **Hinweis:** Die angezeigten Preise werden nach bestem Wissen aus Spotpreisen und Tarifdaten berechnet, können aber von der tatsächlichen Abrechnung abweichen. Verbindlich ist allein die Abrechnung von enviaM.

---

## Update-sicheres Backup

Bei einem **HACS-Update** wird der gesamte Integrationsordner überschrieben. Damit Einstellungen und Tokens dabei nicht verloren gehen, sichert die Integration alle `.env`-Dateien automatisch an einem geschützten Ort:

```
.storage/iona_env_backup/     ← HACS-sicher, wird bei Updates nicht gelöscht
```

**Nach einem Update:**
1. Die Integration erkennt automatisch, dass die Konfigurationsdateien fehlen
2. Sie werden aus dem Backup wiederhergestellt
3. Die Integration läuft nahtlos weiter – ohne erneute Eingabe

> Du musst nichts tun – das Backup funktioniert vollautomatisch im Hintergrund.

### Sicherheit: Zugangsdaten

Deine **Zugangsdaten (E-Mail & Passwort)** werden ausschließlich im **Home Assistant ConfigEntry** (`.storage/`, außerhalb des Integrationsordners) gespeichert – nicht als Klartext-Datei im Integrationsverzeichnis. Token- und Konfigurationsdateien werden mit restriktiven Dateirechten (nur Besitzer) angelegt. Im Normalbetrieb wird ein **Refresh-Token** zur Authentifizierung genutzt. Nur wenn dieser abläuft, greift die Integration automatisch auf die gespeicherten Zugangsdaten zurück.

---

## Troubleshooting

<details>
<summary><b>Keine Sensoren sichtbar</b></summary>

- **Logs prüfen:** Einstellungen → System → Protokolle → nach `iona` filtern
- **iONA Box erreichbar?** Im Terminal `ping <IP-Adresse>` testen
- **Home Assistant nach der Konfiguration neu gestartet?** Ein Neustart ist nach der Ersteinrichtung erforderlich

</details>

<details>
<summary><b>Datenquelle zeigt dauerhaft „WEB"</b></summary>

- **IP-Adresse korrekt?** Unter Einstellungen → Geräte & Dienste → iona-ha → Optionen prüfen
- **iONA Box im Netzwerk erreichbar?** Die Box muss im selben Netzwerk wie Home Assistant sein
- **Firewall/VLAN?** Lokaler Zugriff auf die Box darf nicht blockiert sein

</details>

<details>
<summary><b>Token-Fehler (401 / Authentifizierung fehlgeschlagen)</b></summary>

- Die Integration nutzt bevorzugt einen **Refresh-Token** – ein einzelner 401-Fehler wird automatisch behoben
- Bei dauerhaftem Fehlschlag erscheint automatisch eine **Benachrichtigung** in der HA-Oberfläche
- Zugangsdaten in den Optionen prüfen – stimmen E-Mail und Passwort?
- Testweise in der iONA App oder Webapp einloggen
- Die enviaM-API kann zeitweise nicht erreichbar sein – einfach 5–10 Minuten warten

</details>

<details>
<summary><b>Benachrichtigung: Vision-Preisdaten nicht verfügbar</b></summary>

- Die Integration zeigt eine **Benachrichtigung** an, wenn die enviaM-Schnittstelle wiederholt keine Spotpreis- oder Tarifdaten liefert
- **Vorübergehende API-Störung?** Einfach abwarten – die Meldung verschwindet automatisch, sobald wieder Daten kommen
- **Kein „mein Strom Vision"-Tarif gebucht?** Ohne dynamischen Tarif liefert die Schnittstelle dauerhaft keine Preisdaten – deaktiviere dann die Vision-Option unter **Einstellungen → Geräte & Dienste → iona-ha → Optionen**
- Die Stromzähler-Sensoren (Verbrauch, Einspeisung, Leistung) laufen davon unabhängig normal weiter

</details>

<details>
<summary><b>Benachrichtigung: iONA Box nicht erreichbar</b></summary>

- Die Integration zeigt eine **Benachrichtigung** an, wenn die iONA Box wiederholt nicht erreichbar ist
- **IP-Adresse korrekt?** Unter Einstellungen → Geräte & Dienste → iona-ha → Optionen prüfen
- **Box eingeschaltet?** Prüfe, ob die LED an der iONA Box leuchtet
- **Netzwerk?** Die Box muss im selben Netzwerk wie Home Assistant sein
- Die Benachrichtigung verschwindet **automatisch**, sobald die Box wieder erreichbar ist

</details>

---

## Über dieses Projekt

Dieses Projekt ist ein **privates, experimentelles Open-Source-Projekt**. Der Autor ist eine **Privatperson**, die bei **enviaM** arbeitet und dort unter anderem auch am iONA-Produkt mitarbeitet. Durch diese Nähe zum Produkt kennt er die iONA Box und die zugehörigen Schnittstellen gut – das Projekt entsteht jedoch **ausschließlich in der Freizeit** und aus persönlichem Interesse. Ziel ist es, der Community die iONA-Daten für Home Assistant zugänglich zu machen.

> **⚠️ Haftungsausschluss**
>
> Dies ist **kein offizielles enviaM-Produkt** und steht in **keiner geschäftlichen Verbindung** zu enviaM. Es besteht **kein Anspruch auf Support, Wartung oder Weiterentwicklung**. Die Software wird „as is" (so wie sie ist) bereitgestellt – **ohne jegliche Gewährleistung oder Haftung**.
>
> Angezeigte Werte können von der tatsächlichen Abrechnung abweichen und sind **nicht als Abrechnungsgrundlage** geeignet. Die allein verbindliche Abrechnung erfolgt durch enviaM auf Basis des geeichten Stromzählers.
>
> Die Nutzung erfolgt **auf eigene Gefahr und Verantwortung**.

---

## FAQ

<details>
<summary><b>Funktioniert die Integration ohne iONA Box?</b></summary>

Nein. Die iONA Box ist Voraussetzung – sie liest die Zählerdaten über die Infrarot-Schnittstelle des Smart Meters aus. Die Web-API dient nur als Fallback.

</details>

<details>
<summary><b>Entstehen Kosten?</b></summary>

Nein. Die Integration ist Open Source (MIT-Lizenz). Du benötigst lediglich einen aktiven enviaM-Stromvertrag mit installierter iONA Box.

</details>

<details>
<summary><b>Kann ich mehrere iONA Boxen einbinden?</b></summary>

Aktuell wird eine Box pro Integration unterstützt.

</details>

<details>
<summary><b>Funktioniert die Integration ohne Internet?</b></summary>

Die lokale Abfrage über LAN funktioniert komplett offline. Nur die Web-API als Fallback benötigt eine Internetverbindung.

</details>

---

## Lizenz

MIT License – siehe [LICENSE](LICENSE)

---

## IMPRESSUM

[IMPRESSUM](https://tinohox.de/impressum/)

---

<p align="center">
  <a href="https://github.com/tinohox/iona-ha/issues">Fehler melden & Feature-Wünsche</a> ·
  <a href="https://www.enviam.de/bestellung-iona">iONA Box bestellen</a> ·
  <a href="https://hacs.xyz">HACS</a>
</p>
