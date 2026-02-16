# HACS Default Store – Einreichungs-Checkliste (Integration)

Diese Repo ist bereits als **Custom Repository** nutzbar. Für die Aufnahme in den **HACS Default Store** (also ohne „Custom Repository“-Eintrag) sind ein paar zusätzliche Schritte nötig.

## 1) GitHub Repository Settings (muss manuell im GitHub UI passieren)

HACS prüft bei der PR unter anderem:

- **Description** gesetzt (kurzer Satz, wofür das Repo ist)
- **Topics** gesetzt (mindestens ein paar sinnvolle Tags)
- **Issues** aktiviert

Vorschlag Topics:
- `home-assistant`, `hacs`, `integration`, `energy`, `smart-meter`, `iona`

## 2) GitHub Actions (im Repo enthalten)

Für Default-Submission verlangt HACS (Stand: HACS Docs) bei Integrationen:

- **HACS Action** (Validation) – Workflow: `.github/workflows/validate.yml`
- **Hassfest** – Workflow: `.github/workflows/hassfest.yml`

Wichtig:
- Beide Workflows sollten **auf dem Default-Branch grün** sein.

Hinweis: Falls `hassfest` bei Root-Struktur scheitert, ist häufig eine Umstellung auf `custom_components/<domain>/` nötig. (Du wolltest das aktuell nicht ändern.)

## 3) Release erstellen (wichtig: Release, nicht nur Tag)

HACS Default Checks verlangen mindestens **ein GitHub Release**.

- Auf GitHub → **Releases** → **Draft a new release**
- Tag: `v2.0.0` (existiert bereits als Tag)
- Title: `v2.0.0`
- Notes: kurz, z. B. „Initial public release“

## 4) Home Assistant Brands

Für Default-Listing wird geprüft, ob deine Integration in `home-assistant/brands` eingetragen ist (Domain: `iona`).

- Repo: `https://github.com/home-assistant/brands`
- Üblicherweise: PR mit `brands/iona/icon.png` und `brands/iona/logo.png` (und ggf. `manifest.json`-Infos)

## 5) PR zu `hacs/default`

- Fork von `https://github.com/hacs/default`
- Neuer Branch von `master`
- Datei `integration` bearbeiten und **alphabetisch** eintragen:
  - `https://github.com/tinohox/iona-ha`
- PR-Template vollständig ausfüllen (sonst wird die PR schnell geschlossen)

Docs:
- https://hacs.xyz/docs/publish/start/
- https://hacs.xyz/docs/publish/include/
- https://hacs.xyz/docs/publish/integration/
