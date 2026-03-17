# iONA für Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://hacs.xyz)
[![Version](https://img.shields.io/badge/Version-2.0.2-blue.svg?style=for-the-badge)](https://github.com/tinohox/iona-ha/releases)
[![Lizenz](https://img.shields.io/badge/Lizenz-MIT-green.svg?style=for-the-badge)](LICENSE)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2023.1+-blue.svg?style=for-the-badge&logo=homeassistant)](https://www.home-assistant.io/)

> **⚠️ Experimentelles Projekt – Nutzung auf eigene Gefahr**
>
> Diese Integration ist ein **privates Hobbyprojekt** einer Einzelperson und befindet sich in **aktiver Entwicklung**. Sie ist **kein offizielles Produkt** der enviaM oder eines anderen Unternehmens. Es wird **keine Garantie** für Funktionalität, Korrektheit oder Verfügbarkeit übernommen. Die Nutzung erfolgt **auf eigene Verantwortung**.

Deine **iONA Box** liefert Energiedaten direkt an **Home Assistant** – mit Live-Verbrauchswerten, Zählerständen und voller Integration ins Energie-Dashboard.

---

## English (quick)

This custom Home Assistant integration connects your **iONA box** to Home Assistant and provides live power and energy meter sensors.

**Requirements**

- Home Assistant 2023.1.0+
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

> **📢 Coming Soon: mein Strom Vision**
>
> Unterstützung für den **dynamischen Stromtarif „mein Strom Vision"** von enviaM wird in einem kommenden Update verfügbar sein. Damit werden Spotpreis-Daten und smarte Optimierungswerkzeuge direkt in Home Assistant nutzbar – ideal für alle, die ihren Stromverbrauch automatisiert an günstige Stundenpreise anpassen möchten.

---

## Auf einen Blick

| | Feature |
|---|---|
| ⚡ | **Live-Verbrauch** – Momentanleistung (Watt) alle 5 Sekunden direkt von der iONA Box |
| 📊 | **Zählerstand** – Gesamtverbrauch & Einspeisung (kWh), kompatibel mit dem HA Energie-Dashboard |
| 🔄 | **Dual-Datenquelle** – Primär lokal via LAN, automatischer Web-Fallback bei Verbindungsproblemen |
| 🛡️ | **HACS-Update-sicher** – Zugangsdaten werden automatisch gesichert und nach Updates wiederhergestellt |
| ⚙️ | **Einfache Einrichtung** – Konfiguration komplett über die Home Assistant UI |

---

## Voraussetzungen

- **Home Assistant** 2023.1.0 oder neuer
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

| Parameter | Beschreibung | Beispiel |
|-----------|-------------|---------|
| **iONA Box IP** | Lokale IP-Adresse der iONA Box | `192.168.1.100` |
| **Benutzername** | E-Mail der iONA App | `max@example.com` |
| **Passwort** | Passwort der iONA App | `••••••••` |

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
| **LAN** | 🖧 `mdi:lan` | Daten kommen **direkt von der iONA Box** im lokalen Netzwerk (alle 5 Sekunden) |
| **WEB** | ☁️ `mdi:cloud` | Daten werden über die **enviaM Web-API** bezogen (Fallback, alle 5 Minuten) |

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

## Update-sicheres Backup

Bei einem **HACS-Update** wird der gesamte Integrationsordner überschrieben. Damit deine Zugangsdaten dabei nicht verloren gehen, sichert die Integration alle `.env`-Dateien automatisch an einem geschützten Ort:

```
.storage/iona_env_backup/     ← HACS-sicher, wird bei Updates nicht gelöscht
```

**Nach einem Update:**
1. Die Integration erkennt automatisch, dass die Zugangsdaten fehlen
2. Sie werden aus dem Backup wiederhergestellt
3. Die Integration läuft nahtlos weiter – ohne erneute Eingabe

> Du musst nichts tun – das Backup funktioniert vollautomatisch im Hintergrund.

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

- Zugangsdaten in den Optionen prüfen – stimmen E-Mail und Passwort?
- Testweise in der iONA App oder Webapp einloggen
- Die enviaM-API kann zeitweise nicht erreichbar sein – einfach 5–10 Minuten warten

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
