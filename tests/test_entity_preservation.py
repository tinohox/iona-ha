#!/usr/bin/env python3
"""Tests für die Zusage 'niemand verliert Entitäten oder Daten'.

Deckt die Fälle ab, die der Feldtest auf einer gesunden Anlage NICHT prüfen
kann, weil dort alles vorhanden ist: fehlende Keys, PV-Betrieb, Wechsel der
Datenquelle und Datenbestände aus älteren Versionen.

Aufruf siehe tests/README.md.
"""

import json
import os
import sys
import tempfile
import types
from datetime import datetime, timedelta, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "app"))

TZ = timezone(timedelta(hours=2))
_FAILS: list[str] = []


def check(name, got, want):
    ok = got == want
    if not ok:
        _FAILS.append(f"{name}: erwartet {want!r}, war {got!r}")
    print(f"{'OK  ' if ok else 'FEHL'}  {name:<62} = {got!r}")


def section(title):
    print(f"\n=== {title} ===")


# --------------------------------------------------------------------------
#  Home Assistant so weit stubben, dass sensor.py importierbar ist
# --------------------------------------------------------------------------

class _FakeRegistryEntry:
    def __init__(self, entity_id, unique_id, domain="sensor"):
        self.entity_id = entity_id
        self.unique_id = unique_id
        self.domain = domain


_REGISTRY_ENTRIES: list = []


def _stub_homeassistant():
    def mod(name, **attrs):
        m = types.ModuleType(name)
        for k, v in attrs.items():
            setattr(m, k, v)
        sys.modules[name] = m
        return m

    class CoordinatorEntity:
        def __init__(self, coordinator):
            self.coordinator = coordinator

    mod("homeassistant")
    mod("homeassistant.core", HomeAssistant=object)
    mod("homeassistant.helpers")
    mod("homeassistant.helpers.entity", Entity=object)
    mod("homeassistant.helpers.update_coordinator",
        DataUpdateCoordinator=object, CoordinatorEntity=CoordinatorEntity)
    mod("homeassistant.helpers.entity_registry",
        async_get=lambda hass: object(),
        async_entries_for_config_entry=lambda reg, eid: list(_REGISTRY_ENTRIES))
    mod("homeassistant.util")
    mod("homeassistant.util.dt", now=lambda: datetime.now(TZ))


class _Coordinator:
    def __init__(self, data):
        self.data = data


class _Entry:
    entry_id = "abc123"


class _Logger:
    def info(self, *a, **k):
        pass

    def debug(self, *a, **k):
        pass


# --------------------------------------------------------------------------

def test_entity_never_disappears():
    section("Entität aus dem Registry überlebt einen fehlenden DB-Key")
    _stub_homeassistant()
    pkg = types.ModuleType("iona")
    pkg.__path__ = [REPO]
    sys.modules["iona"] = pkg
    from iona.sensor import IonaSensor, _restore_known_meter_sensors

    # So sieht der Datensatz einer PV-Anlage nachts aus: Export meldet 0,
    # get_lan_data lässt den Key deshalb komplett weg.
    ohne_einspeisung = {
        "device_id": "Stromzaehler", "source": "LAN",
        "Gesamtverbrauch": 15421.5, "Gesamtverbrauch_unit": "kWh",
        "Momentanleistung": 800, "Momentanleistung_unit": "W",
    }
    coord = _Coordinator({"Stromzaehler": ohne_einspeisung})

    # Die Entität, die es beim Nutzer bereits gibt
    global _REGISTRY_ENTRIES
    _REGISTRY_ENTRIES = [
        _FakeRegistryEntry("sensor.stromzahler_gesamteinspeisung",
                           "iona_meter_Gesamteinspeisung_d10aaa26"),
        _FakeRegistryEntry("sensor.stromzahler_gesamtverbrauch",
                           "iona_meter_Gesamtverbrauch_19835afb"),
    ]

    sensors = [IonaSensor(coord, "Stromzaehler", k, ohne_einspeisung)
               for k in ("Gesamtverbrauch", "Momentanleistung", "source")]
    vorher = {s.unique_id for s in sensors}
    check("Einspeisung fehlt zunächst",
          "iona_meter_Gesamteinspeisung_d10aaa26" in vorher, False)

    n = _restore_known_meter_sensors(None, _Entry(), coord, sensors, _Logger())
    nachher = {s.unique_id for s in sensors}
    check("genau eine Entität wiederhergestellt", n, 1)
    check("Einspeisung ist wieder da",
          "iona_meter_Gesamteinspeisung_d10aaa26" in nachher, True)
    check("unique_id exakt wie im Registry",
          sorted(nachher - vorher), ["iona_meter_Gesamteinspeisung_d10aaa26"])
    check("keine Entität doppelt", len(sensors), len(nachher))

    # Erneuter Aufruf darf nichts verdoppeln
    n2 = _restore_known_meter_sensors(None, _Entry(), coord, sensors, _Logger())
    check("zweiter Aufruf legt nichts nach", n2, 0)


def test_deleted_entity_stays_deleted():
    section("Vom Nutzer gelöschte Entität bleibt gelöscht")
    from iona.sensor import IonaSensor, _restore_known_meter_sensors
    global _REGISTRY_ENTRIES
    data = {"device_id": "Stromzaehler", "source": "LAN", "Gesamtverbrauch": 1.0}
    coord = _Coordinator({"Stromzaehler": data})
    _REGISTRY_ENTRIES = []          # Nutzer hat alles entfernt
    sensors = [IonaSensor(coord, "Stromzaehler", "Gesamtverbrauch", data)]
    n = _restore_known_meter_sensors(None, _Entry(), coord, sensors, _Logger())
    check("nichts wird wiederbelebt", n, 0)


def test_foreign_registry_entries_ignored():
    section("Fremde Registry-Einträge werden nicht angefasst")
    from iona.sensor import IonaSensor, _restore_known_meter_sensors
    global _REGISTRY_ENTRIES
    data = {"device_id": "Stromzaehler", "source": "LAN", "Gesamtverbrauch": 1.0}
    coord = _Coordinator({"Stromzaehler": data})
    _REGISTRY_ENTRIES = [
        _FakeRegistryEntry("sensor.stromzahler_strompreis",
                           "iona_vision_aktueller_preis_3cc4e38e"),
        _FakeRegistryEntry("button.vision_berechnen", "iona_vision_berechnen",
                           domain="button"),
        _FakeRegistryEntry("sensor.fremd", "irgendwas_anderes"),
        _FakeRegistryEntry("sensor.kaputt", "iona_meter_"),   # unbrauchbar
    ]
    sensors = [IonaSensor(coord, "Stromzaehler", "Gesamtverbrauch", data)]
    n = _restore_known_meter_sensors(None, _Entry(), coord, sensors, _Logger())
    check("keine Vision-/Fremd-Entität erzeugt", n, 0)


def test_pv_export_running():
    section("PV-Anlage mit laufender Einspeisung")
    import get_lan_data
    import requests

    tmp = tempfile.mkdtemp()
    env, data = os.path.join(tmp, "env"), os.path.join(tmp, "data")
    os.makedirs(env)
    os.makedirs(data)
    with open(os.path.join(env, "secrets-n2g.env"), "w") as f:
        f.write("IONA_BOX=1.2.3.4\n")
    with open(os.path.join(env, "LanToken.env"), "w") as f:
        f.write("DATA={'user_lan_token': 'tok'}\n")
    get_lan_data.ENV_DIR, get_lan_data.DATA_DIR = env, data
    get_lan_data.DB_PATH = os.path.join(data, "meter_db.json")

    box = {}

    class R:
        status_code = 200

        def json(self):
            return box["p"]

    get_lan_data.requests.get = lambda url, **kw: R()

    def payload(epoch, power, imp, exp):
        return {"elec": {
            "power": {"now": {"value": power, "time": epoch}},
            "import": {"now": {"value": imp, "time": epoch}},
            "export": {"now": {"value": exp, "time": epoch}}}}

    def entry():
        return list(json.load(open(get_lan_data.DB_PATH))["_default"].values())[0]

    e0 = int(datetime(2026, 9, 14, 12, 0, tzinfo=TZ).timestamp())
    box["p"] = payload(e0, -1500, 15_000_000, 200_000)      # Einspeisung läuft
    get_lan_data.run()
    check("Einspeisung angelegt", entry()["Gesamteinspeisung"], 200.0)
    check("negative Leistung übernommen", entry()["Momentanleistung"], -1500)

    box["p"] = payload(e0 + 60, -1400, 15_000_000, 200_500)
    r = get_lan_data.run()
    check("Einspeisung steigt", entry()["Gesamteinspeisung"], 200.5)
    check("Verbrauch unverändert, kein Schreiben nötig",
          entry()["Gesamtverbrauch"], 15000.0)
    check("als Änderung gemeldet", r.updated, True)

    # Wolke: Einspeisung stoppt, Box meldet 0 -> Wert darf nicht zurückfallen
    box["p"] = payload(e0 + 120, 900, 15_000_100, 0)
    get_lan_data.run()
    check("Einspeisung faellt NICHT auf 0", entry()["Gesamteinspeisung"], 200.5)
    check("Verbrauch laeuft weiter", entry()["Gesamtverbrauch"], 15000.1)

    # Nacht: Box laesst den Export-Key ganz weg
    box["p"] = {"elec": {
        "power": {"now": {"value": 400, "time": e0 + 180}},
        "import": {"now": {"value": 15_000_200, "time": e0 + 180}}}}
    get_lan_data.run()
    check("Einspeisungs-Key bleibt im Datensatz",
          "Gesamteinspeisung" in entry(), True)
    check("Einspeisungs-Wert unveraendert", entry()["Gesamteinspeisung"], 200.5)


def test_upgrade_from_old_data():
    section("Datenbestand aus 2.2.x wird korrekt weitergeführt")
    import get_lan_data

    tmp = tempfile.mkdtemp()
    env, data = os.path.join(tmp, "env"), os.path.join(tmp, "data")
    os.makedirs(env)
    os.makedirs(data)
    with open(os.path.join(env, "secrets-n2g.env"), "w") as f:
        f.write("IONA_BOX=1.2.3.4\n")
    with open(os.path.join(env, "LanToken.env"), "w") as f:
        f.write("DATA={'user_lan_token': 'tok'}\n")
    get_lan_data.ENV_DIR, get_lan_data.DATA_DIR = env, data
    get_lan_data.DB_PATH = os.path.join(data, "meter_db.json")

    # So sah der Datensatz vor 2.3.0 aus: Zeitstempel = Abrufzeit
    alt = {"_default": {"1": {
        "device_id": "Stromzaehler", "source": "LAN",
        "Gesamtverbrauch": 15421.5, "Gesamtverbrauch_unit": "kWh",
        "Gesamtverbrauch_timestamp": "2026-09-14T11:59:59+02:00",
        "Momentanleistung": 800, "Momentanleistung_unit": "W",
        "Momentanleistung_timestamp": "2026-09-14T11:59:59+02:00",
        "Gesamteinspeisung": 153.384, "Gesamteinspeisung_unit": "kWh",
        "Gesamteinspeisung_timestamp": "2026-09-14T11:59:59+02:00"}}}
    with open(get_lan_data.DB_PATH, "w") as f:
        json.dump(alt, f)

    box = {}

    class R:
        status_code = 200

        def json(self):
            return box["p"]

    get_lan_data.requests.get = lambda url, **kw: R()

    def entry():
        return list(json.load(open(get_lan_data.DB_PATH))["_default"].values())[0]

    e0 = int(datetime(2026, 9, 14, 12, 0, tzinfo=TZ).timestamp())
    box["p"] = {"elec": {
        "power": {"now": {"value": 810, "time": e0}},
        "import": {"now": {"value": 15_421_600, "time": e0}},
        "export": {"now": {"value": 153_384, "time": e0}}}}
    r = get_lan_data.run()
    check("Altbestand wird fortgeschrieben", entry()["Gesamtverbrauch"], 15421.6)
    check("Einspeisung bleibt erhalten", entry()["Gesamteinspeisung"], 153.384)
    check("alle Keys erhalten", len(entry()), len(alt["_default"]["1"]))
    check("als Änderung gemeldet", r.updated, True)

    # Ein niedrigerer Altbestand darf nicht zurückgesetzt werden
    box["p"]["elec"]["import"]["now"]["value"] = 10_000_000
    get_lan_data.run()
    check("Rückgang weiterhin blockiert", entry()["Gesamtverbrauch"], 15421.6)


def test_vision_device_id_matches_vision_module():
    section("Vision-device_id stimmt mit app/vision.py überein")
    from iona.sensor import VISION_DEVICE_ID
    quelle = open(os.path.join(REPO, "app", "vision.py"), encoding="utf-8").read()
    check("vision.py schreibt dieselbe device_id",
          f'"device_id": "{VISION_DEVICE_ID}"' in quelle, True)
    # Abweichung wäre fatal: die device_id geht in die unique_id ein.
    import hashlib
    h = hashlib.md5(f"vision_{VISION_DEVICE_ID}_aktueller_preis".encode()).hexdigest()[:8]
    check("ergibt die bekannte unique_id",
          f"iona_vision_aktueller_preis_{h}", "iona_vision_aktueller_preis_3cc4e38e")


def test_price_sensor_without_data():
    section("Preissensor entsteht auch ohne Vision-Daten (Issue #3)")
    import asyncio
    import iona.sensor as S

    class _Coord:
        def __init__(self, update_method):
            self.update_method = update_method
            self.data = {}

        async def async_config_entry_first_refresh(self):
            self.data = await self.update_method()

    class _Reg:
        entities: dict = {}

        def async_remove(self, eid):
            pass

    # sensor.py hat den Namen beim Import gebunden – dort ersetzen, nicht im Modul
    S.DataUpdateCoordinator = (
        lambda hass, logger=None, name=None, update_method=None,
        update_interval=None: _Coord(update_method))
    sys.modules["homeassistant.helpers.entity_registry"].async_get = lambda h: _Reg()

    class _Hass:
        async def async_add_executor_job(self, fn, *a):
            return fn(*a)

    def setup(vision_data, vision_on, tools_on=False):
        tmp = tempfile.mkdtemp()
        S.DB_PATH = os.path.join(tmp, "meter_db.json")
        S.VISION_DB_PATH = os.path.join(tmp, "vision_db.json")
        S.SPOTPREISE_DB_PATH = os.path.join(tmp, "spot.json")
        json.dump({"_default": {"1": {"device_id": "Stromzaehler", "source": "LAN",
                                      "Gesamtverbrauch": 1.0}}},
                  open(S.DB_PATH, "w"))
        if vision_data:
            json.dump({"_default": {"1": vision_data}}, open(S.VISION_DB_PATH, "w"))
        S._VISION_AVAILABLE = True
        S.is_vision_enabled = lambda: vision_on
        S.is_vision_tools_enabled = lambda: tools_on
        made = []
        asyncio.run(S.async_setup_entry(
            _Hass(), _Entry(), lambda ents, update_before_add=False: made.extend(ents)))
        return sorted(x.unique_id for x in made)

    mit = setup({"device_id": "vision_strom", "aktueller_preis": 0.49,
                 "timestamp": "x"}, True)
    ohne = setup(None, True)
    aus = setup(None, False)

    preis = "iona_vision_aktueller_preis_3cc4e38e"
    check("mit Daten: Preissensor da", preis in mit, True)
    check("OHNE Daten: Preissensor trotzdem da", preis in ohne, True)
    check("gleiche unique_id wie mit Daten – kein Duplikat",
          [u for u in ohne if "aktueller_preis" in u],
          [u for u in mit if "aktueller_preis" in u])
    check("Vision aus: kein Preissensor", any("aktueller_preis" in u for u in aus), False)
    check("Zähler-Entitäten unverändert",
          sorted(u for u in ohne if u.startswith("iona_meter_")),
          sorted(u for u in mit if u.startswith("iona_meter_")))

    tools = setup(None, True, tools_on=True)
    check("mit Vision Tools kommen die Tools-Sensoren dazu",
          len([u for u in tools if u.startswith("iona_vision_")]), 4)


def main():
    test_entity_never_disappears()
    test_deleted_entity_stays_deleted()
    test_foreign_registry_entries_ignored()
    test_pv_export_running()
    test_upgrade_from_old_data()
    test_vision_device_id_matches_vision_module()
    test_price_sensor_without_data()
    print()
    if _FAILS:
        print(f"{len(_FAILS)} FEHLER:")
        for f in _FAILS:
            print("  -", f)
        return 1
    print("Alle Fälle bestanden.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
