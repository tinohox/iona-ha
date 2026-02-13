# iona-ha – iONA Energie-Daten für Home Assistant

**Version:** 2.0.0 | **Domain:** `iona` | **Lizenz:** MIT

[![HACS](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)

Eine **Home Assistant Custom Integration**, die Energiedaten aus dem **iONA-System von enviaM** in Home Assistant verfügbar macht – inklusive Live-Verbrauchswerte, Zählerständen und optionaler Spotpreis-Analyse für dynamische Stromtarife.

---

> **⚠️ Experimentell – keine Abrechnungsgrundlage**
>
> Diese Integration ist ein **experimentelles Community-Projekt** und eignet sich **nicht** als Grundlage für die Abrechnung mit enviaM. Angezeige Verbrauchs- und Preiswerte können von der tatsächlichen enviaM-Rechnung abweichen, u. a. wegen:
>
> - **Zeitliche Differenzen:** Spotpreise werden über öffentliche APIs abgerufen und können je nach Abrufzeitpunkt, Caching und Netzwerkverzögerung vom exakten Zeitpunkt der tatsächlichen Messung abweichen. Bereits wenige Minuten Versatz zwischen Preis- und Verbrauchszuordnung führen zu Abweichungen.
> - **Strompreis-Berechnung:** Die Bruttopreis-Berechnung (Netzentgelte, Umlagen, Steuern, MwSt.) basiert auf öffentlich verfügbaren Durchschnittswerten und kann von den individuellen Vertragskonditionen bei enviaM abweichen. Tarifänderungen, Sonderbedingungen oder regionale Unterschiede werden nicht automatisch berücksichtigt.
> - **Messgenauigkeit:** Die iONA Box liefert Momentanwerte per Smart-Meter-Infrarot-Schnittstelle. Rundungsdifferenzen, Abtastraten und kurzzeitige Aussetzer (z. B. bei WLAN-Unterbrechungen) können zu geringfügigen Abweichungen gegenüber dem geeichten Zählerstand führen.
>
> **Die allein verbindliche Abrechnung erfolgt durch enviaM auf Basis des geeichten Stromzählers.**

---

## Über dieses Projekt

Dieses Projekt ist ein **privates Open-Source-Projekt**. Der Autor ist Mitarbeiter bei **enviaM** und arbeitet dort auch am iONA-Produkt mit. Ziel ist es, der Community die iONA-Daten für Home Assistant zugänglich zu machen – insbesondere für Nutzer mit einem enviaM-Stromvertrag und installiertem iONA-Ausleser.

> **Hinweis:** Dies ist **kein offizielles enviaM-Produkt**. Es besteht kein Anspruch auf Support durch enviaM. Die Nutzung erfolgt auf eigene Verantwortung.

---

## Hauptfunktionen

- **Live-Verbrauchsdaten** – Momentanleistung (W) und Zählerstand (kWh) direkt von der lokalen iONA Box
- **Energie-Dashboard** – volle Integration ins Home Assistant Energie-Dashboard
- **mein Strom Vision** – optionale Spotpreis-Analyse für den dynamischen enviaM-Tarif:
  - Aktueller Strompreis (€/kWh)
- **mein Strom Vision Tools** – Optimierungswerkzeuge für den dynamischen Tarif:
  - Günstigste Startzeit für konfigurierbaren Zeitraum (`device_class: timestamp` – direkt für Automations nutzbar)
  - Durchschnittspreis für den günstigsten Zeitblock
  - **Zeitraum-Slider** – Dauer des gewünschten Verbrauchsfensters (1h bis max. Datenlage)
  - **Vorausschau-Slider** – Suchhorizont, dynamisch (immer > Zeitraum, max. Datenlage)
  - **Nacht-Schalter** – Toggle für Nur-Nachtzeit-Suche (20:00–07:00)
- **Dynamische Slider-Grenzen** – Schieberegler passen sich automatisch an die verfügbare Spotpreis-Datenlage an
- **Automatisches Env-Backup** – Zugangsdaten werden in `.storage/` gesichert und nach HACS-Updates wiederhergestellt
- **Minimale API-Last** – intelligentes Caching: Daten werden nur abgerufen, wenn sie fehlen oder veraltet sind

---

## Voraussetzungen

| Bereich | Anforderung |
|---------|-------------|
| **Home Assistant** | 2023.1.0 oder neuer |
| **HACS** | installiert ([Anleitung](https://hacs.xyz/docs/use/download/download/)) |
| **enviaM** | aktiver Stromvertrag mit iONA |
| **iONA Box** | im Heimnetzwerk erreichbar, feste IP-Adresse |
| **Zugangsdaten** | E-Mail & Passwort der iONA-App |

---

## Installation

### Über HACS (empfohlen)

1. **HACS** öffnen → **Integrationen** → Menü (⋮) → **Benutzerdefinierte Repositories**
2. Repository hinzufügen:
   - **URL:** `https://github.com/tinohox/iona-ha`
   - **Kategorie:** `Integration`
3. `iona-ha` downloaden (⋮ → Download)
4. **Home Assistant neu starten**
5. **Einstellungen → Geräte & Dienste → Integration hinzufügen** → `iona-ha` suchen
6. Zugangsdaten eingeben (siehe Konfiguration)
7. **Home Assistant neu starten**

### Manuell

```bash
git clone https://github.com/tinohox/iona-ha.git
# Inhalt nach custom_components/iona/ kopieren
```

Danach Home Assistant neu starten und über UI konfigurieren.

---

## Konfiguration

Die Integration wird vollständig über die **Home Assistant UI** eingerichtet:

| Parameter | Beschreibung | Beispiel |
|-----------|-------------|---------|
| **iONA Box IP** | Lokale IP-Adresse der iONA Box | `192.168.1.100` |
| **Benutzername** | E-Mail-Adresse der iONA App | `max@example.com` |
| **Passwort** | Passwort der iONA App | `••••••••` |
| **mein Strom Vision** | Dynamischen Tarif aktivieren | `ja / nein` |

Alle Einstellungen können nachträglich über **Einstellungen → Geräte & Dienste → iona-ha → Optionen** geändert werden.

---

## Geräte & Entitäten

Die Integration erstellt bis zu **drei Geräte** in Home Assistant:

### 🔌 mein Stromzähler

Für jeden erkannten Zähler werden automatisch Sensoren erstellt:

| Sensor | Einheit | Device Class | State Class |
|--------|---------|-------------|-------------|
| Gesamtverbrauch | kWh | `energy` | `total_increasing` |
| Gesamteinspeisung | kWh | `energy` | `total_increasing` |
| Momentanleistung | W | `power` | `measurement` |

### 💡 mein Strom Vision

Wird nur bei aktiviertem dynamischen Tarif (mein Strom Vision) erstellt:

| Sensor | Einheit | Device Class | Beschreibung |
|--------|---------|-------------|-------------|
| aktueller Strompreis | €/kWh | `monetary` | Aktueller Brutto-Spotpreis inkl. aller Abgaben |

### 🛠️ mein Strom Vision Tools

Optimierungswerkzeuge für den dynamischen Tarif:

| Entität | Typ | Beschreibung |
|---------|-----|-------------|
| günstigste Startzeit | Sensor (`timestamp`) | Optimaler Startzeitpunkt für den Zeitblock – direkt für HA-Automations nutzbar |
| Durchschnittskosten | Sensor (`monetary`) | Ø-Preis (€/kWh) im günstigsten Zeitblock |
| Vision Tools – Zeitraum | Slider (Number) | Dauer des Verbrauchsfensters (1h bis Datenlage − 1) |
| Vision Tools – Vorausschau | Slider (Number) | Suchhorizont (Zeitraum + 1 bis Datenlage) |
| Vision Tools – nur Nachtstrom | Schalter (Switch) | Suche auf Nachtzeiten beschränken (20:00–07:00) |

#### Dynamische Slider-Grenzen

Die Schieberegler passen sich automatisch an die tatsächlich verfügbare Spotpreis-Datenlage an:

- **Zeitraum**: Minimum 1h, Maximum = verfügbare Stunden − 1
- **Vorausschau**: Minimum = Zeitraum + 1, Maximum = verfügbare Stunden
- Wenn der **Zeitraum** erhöht wird und die **Vorausschau** zu niedrig wäre, wird sie automatisch angehoben
- Typischerweise sind 24–48h Spotpreise verfügbar, aber die Datenlage variiert je nach API-Verfügbarkeit

#### Automations-Tipp

Die **günstigste Startzeit** hat `device_class: timestamp` und kann direkt in HA-Automations verwendet werden:

```yaml
automation:
  - alias: "Wallbox bei günstigstem Strom starten"
    trigger:
      - platform: time
        at: sensor.gunstigste_startzeit_fur_2h
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.wallbox
```

Oder als Template-Bedingung:

```yaml
condition:
  - condition: template
    value_template: >
      {{ now() >= states('sensor.gunstigste_startzeit_fur_2h') | as_datetime }}
```

---

## Energie-Dashboard

1. **Einstellungen → Energie**
2. Abschnitt **Strom** → Sensor `Stromzähler Gesamtverbrauch` auswählen
3. Optional: `mein Strom Vision – aktueller Strompreis` als Preissensor zuordnen

---

## Architektur

### Datenfluss

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐     ┌──────────────┐
│  iONA Box   │────→│ get_lan_data │────→│ meter_db    │────→│  HA Sensor   │
│  (lokal)    │     │              │     │  .json      │     │  Entities    │
└─────────────┘     └──────────────┘     └─────────────┘     └──────────────┘

┌─────────────┐     ┌──────────────┐     ┌─────────────┐     ┌──────────────┐
│ enviaM API  │────→│ get_spot_    │────→│ spotpreise_ │────→│ calc_preise  │
│             │     │ prices       │     │ db.json     │     │              │
└─────────────┘     └──────────────┘     └─────────────┘     └──────┬───────┘
                                                                     │
                    ┌──────────────┐     ┌─────────────┐            │
                    │   vision     │←────│ brutto_db   │←───────────┘
                    │              │     │  .json      │
                    └──────┬───────┘     └─────────────┘
                           │
                    ┌──────▼───────┐     ┌──────────────┐
                    │ vision_db    │────→│  HA Sensor   │
                    │  .json       │     │  Entities    │
                    └──────────────┘     └──────────────┘
```

### Module

| Modul | Funktion |
|-------|----------|
| `__init__.py` | Integration-Lifecycle, Setup, Unload, Credential-Restore |
| `data_manager.py` | Zentrale Steuerung aller Datenabfragen via HA Event-Loop |
| `config_flow.py` | UI-Konfiguration (Config Flow + Options Flow) |
| `sensor.py` | Sensor-Entities (Coordinator-Pattern) |
| `number.py` | Zeitraum- & Vorausschau-Slider (dynamische Grenzen) |
| `switch.py` | Nacht-Modus Schalter |
| `env_utils.py` | Gemeinsame .env Dateiverwaltung, Datenlage-Erkennung |
| `env_backup.py` | Automatisches Backup/Restore von .env und Datendateien |
| `app/get_web_token.py` | Web-API Authentifizierung |
| `app/get_lan_token.py` | LAN-Token für lokale iONA Box |
| `app/get_lan_data.py` | Live-Daten von der lokalen Box (alle 5s) |
| `app/get_web_data.py` | Web-API Fallback für Verbrauchsdaten |
| `app/get_spot_prices.py` | Spotpreise von enviaM |
| `app/get_tariff_data.py` | Tarifdetails (Umlagen, Steuern) |
| `app/calc_preise.py` | Brutto-Endkundenpreise berechnen |
| `app/vision.py` | Günstigste Zeitfenster analysieren |

### API-Optimierung

Die Integration minimiert API-Aufrufe an enviaM durch intelligentes Caching:

| Daten | Abruf-Intervall | Bedingung |
|-------|-----------------|-----------|
| LAN-Zählerdaten | 5 Sekunden | Lokale Box, kein API-Aufruf |
| Web-Zählerdaten | 5 Minuten | **Nur als Fallback** wenn LAN-Daten > 1 Min alt |
| Web-Token | 30 Minuten | Immer (Token-Refresh) |
| LAN-Token | 86 Minuten | Nur wenn Web-Token vorhanden |
| Spotpreise | 30 Minuten | **Nur wenn Daten > 25 Min alt** oder fehlend |
| Tarifdaten | 24 Stunden | **Nur wenn Daten > 23h alt** oder fehlend |
| Bruttopreise | 30 Minuten | Nur wenn Quelldaten vorhanden |
| Vision | 5 Minuten | Nur wenn aktiviert und Bruttopreise vorhanden |

Beim ersten Start werden fehlende Daten sofort abgerufen.

---

## .env Backup-System

HACS überschreibt beim Update den gesamten Integrationsordner. Die Integration sichert `.env`-Dateien automatisch:

```
~/.homeassistant/
├── custom_components/iona/app/env/     ← Arbeitsverzeichnis (Runtime)
│   ├── account.env
│   ├── secrets-n2g.env
│   ├── LanToken.env
│   └── WebToken.env
└── .storage/
    └── iona_env_backup/                ← HACS-sicheres Backup
```

**Ablauf bei HACS-Update:**
1. Update löscht `env/` Dateien
2. Integration startet → erkennt leeres `env/`
3. Automatisches Restore aus `iona_env_backup/`
4. Integration läuft mit bestehenden Zugangsdaten weiter

---

## Troubleshooting

### Keine Sensoren sichtbar
- **Logs prüfen:** Einstellungen → System → Protokolle → nach `iona` filtern
- **iONA Box erreichbar?** `ping <IP>` im Terminal testen
- **Home Assistant nach Konfiguration neu starten**

### mein Strom Vision Sensoren fehlen
- Option `mein Strom Vision` in den Integrationsoptionen aktivieren
- Home Assistant neu starten
- In `account.env` muss `vision_tariff="True"` stehen

### Token-Fehler (401)
- Zugangsdaten in den Optionen prüfen
- Passwort in der iONA App/Webapp testen
- Die enviaM/iONA API (Net2Grid) kann zeitweise nicht erreichbar sein – 5–10 Min warten

---

## Migration von v1.x

Beim Update von der alten `free-iONA` Version auf `iona-ha` v2.0:

1. Die Datei `accound.env` wird automatisch zu `account.env` umbenannt (Tippfehler-Fix)
2. `python-dotenv` wird nicht mehr als Abhängigkeit benötigt
3. `app/main.py` wird nicht mehr benötigt (Scheduling läuft jetzt über Home Assistant)
4. Alle App-Skripte wurden in importierbare Module umgewandelt

Es ist keine manuelle Migration nötig. Die Integration erkennt und migriert alte Konfigurationen automatisch.

---

## FAQ

**Funktioniert die Integration ohne iONA Box?**
Nein. Die Box ist erforderlich für lokale Echtzeit-Messwerte. Die Web-API dient nur als Fallback.

**Welche Kosten entstehen?**
Keine. Die Integration ist Open Source (MIT). Du brauchst nur einen aktiven enviaM-Stromvertrag mit iONA.

**Mehrere iONA Boxen?**
Aktuell wird nur eine Box pro Integration unterstützt.

**Offline-Betrieb?**
Lokale Datenabfrage (LAN) funktioniert offline. Spotpreise und Web-API benötigen Internet.

---

## Lizenz

MIT License – siehe [LICENSE](LICENSE)

---

## Links

- [GitHub Issues](https://github.com/tinohox/iona-ha/issues) – Fehler melden & Feature-Wünsche
- [iONA bei enviaM](https://www.enviam.de/bestellung-iona) – iONA Box bestellen
- [HACS](https://hacs.xyz) – Home Assistant Community Store
