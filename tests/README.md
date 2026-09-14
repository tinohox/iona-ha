# Tests

Das Repo hat (noch) keine pytest-Infrastruktur. Diese Skripte laufen
eigenständig gegen eine nachgebaute iONA Box und eine nachgebaute Cloud.

`tinydb`, `requests` und `homeassistant` sind auf einem Entwicklungsrechner
üblicherweise nicht installiert – ein venv ist nötig:

```bash
python3 -m venv .venv
.venv/bin/pip install tinydb==4.8.0 requests
.venv/bin/python tests/test_meter_path.py
.venv/bin/python tests/test_entity_preservation.py
```

- **test_meter_path.py** – Abrufpfad, Schreibgates, Persistenz, Fehlerursachen.
- **test_entity_preservation.py** – die Fälle, die ein Feldtest auf einer
  gesunden Anlage nicht prüfen kann: fehlende DB-Keys, PV mit laufender
  Einspeisung, Datenbestände aus 2.2.x.

`homeassistant` wird nicht gebraucht: die wenigen benötigten Teile werden im
Testskript gestubbt (siehe `_stub_homeassistant()`).

Die Tests decken die Zusagen aus dem 2.3.0-Umbau ab – zuerst die
Datenerhalt-Garantien, danach die Funktion. Fällt einer der Garantie-Tests,
darf nicht ausgeliefert werden.
