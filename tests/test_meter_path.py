#!/usr/bin/env python3
"""Tests für den Zählerdaten-Pfad (LAN, Cloud, Persistenz, Backup).

Aufruf siehe tests/README.md. Kein pytest nötig – das Skript meldet sich mit
Exit-Code 1, wenn ein Fall fehlschlägt.

Reihenfolge ist Absicht: zuerst die Datenerhalt-Garantien, danach die
Funktion. Fällt eine Garantie, darf nicht ausgeliefert werden.
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
#  Home Assistant stubben (nur, was data_manager/env_backup wirklich nutzen)
# --------------------------------------------------------------------------

def _stub_homeassistant():
    def mod(name, **attrs):
        m = types.ModuleType(name)
        for k, v in attrs.items():
            setattr(m, k, v)
        sys.modules[name] = m
        return m

    mod("homeassistant")
    mod("homeassistant.core", HomeAssistant=object)
    mod("homeassistant.config_entries", ConfigEntry=object)
    mod("homeassistant.helpers")
    mod("homeassistant.helpers.event",
        async_track_point_in_time=lambda *a, **k: None,
        async_track_time_interval=lambda *a, **k: (lambda: None))
    mod("homeassistant.helpers.config_validation",
        config_entry_only_config_schema=lambda d: None)
    mod("homeassistant.util")
    mod("homeassistant.util.dt",
        now=lambda: datetime.now(TZ),
        parse_datetime=datetime.fromisoformat,
        as_local=lambda d: d.replace(tzinfo=TZ))
    mod("homeassistant.components")
    mod("homeassistant.components.http", StaticPathConfig=object)
    mod("homeassistant.components.persistent_notification",
        async_create=lambda *a, **k: None, async_dismiss=lambda *a, **k: None)


# --------------------------------------------------------------------------
#  Nachgebaute Box und Cloud
# --------------------------------------------------------------------------

BOX = {"payload": None}
CLOUD = {"payload": None}


class _Resp:
    def __init__(self, payload, status=200):
        self._p, self.status_code = payload, status

    def json(self):
        return self._p

    def raise_for_status(self):
        pass


def _fake_get(url, **kw):
    if "/meter/now" in url:
        if BOX["payload"] is None:
            import requests
            raise requests.RequestException("box offline")
        return _Resp(BOX["payload"])
    return _Resp(CLOUD["payload"])


def box_payload(epoch, power, imp, exp):
    """Die Box stempelt ALLE Register mit derselben Abrufzeit."""
    return {"elec": {
        "power": {"now": {"value": power, "time": epoch}},
        "import": {"now": {"value": imp, "time": epoch}},
        "export": {"now": {"value": exp, "time": epoch}},
    }}


def cloud_payload(ts, power, summation):
    return {"data": {"electricity": {
        "timestamp": ts, "power": power, "current_summation": summation}}}


def setup_modules():
    """Frisches Datenverzeichnis, Module darauf umbiegen."""
    import get_lan_data, get_web_data
    tmp = tempfile.mkdtemp()
    env, data = os.path.join(tmp, "env"), os.path.join(tmp, "data")
    os.makedirs(env)
    os.makedirs(data)
    with open(os.path.join(env, "secrets-n2g.env"), "w") as f:
        f.write("IONA_BOX=192.168.1.50\n")
    with open(os.path.join(env, "LanToken.env"), "w") as f:
        f.write("DATA={'user_lan_token': 'tok'}\n")
    with open(os.path.join(env, "WebToken.env"), "w") as f:
        f.write("ACCESS_TOKEN=abc\n")
    for m in (get_lan_data, get_web_data):
        m.ENV_DIR, m.DATA_DIR = env, data
        m.DB_PATH = os.path.join(data, "meter_db.json")
        m.requests.get = _fake_get
    return tmp, data


def entry():
    import get_lan_data
    with open(get_lan_data.DB_PATH) as f:
        return list(json.load(f)["_default"].values())[0]


EPOCH = int(datetime(2026, 9, 14, 18, 0, 0, tzinfo=TZ).timestamp())


# --------------------------------------------------------------------------
#  Teil A – Datenerhalt-Garantien
# --------------------------------------------------------------------------

def test_value_guard():
    section("G · Zählerstände können nicht sinken")
    from fetch_utils import value_allows_update
    check("Gesamtverbrauch darf steigen",
          value_allows_update("Gesamtverbrauch", 11722, 11721), True)
    check("Gesamtverbrauch darf nicht sinken",
          value_allows_update("Gesamtverbrauch", 11000, 11721), False)
    check("Einspeisung >0 auf 0 verworfen",
          value_allows_update("Gesamteinspeisung", 0, 105.6), False)
    check("Momentanleistung darf sinken",
          value_allows_update("Momentanleistung", -412, 3000), True)
    check("ohne Altwert immer erlaubt",
          value_allows_update("Gesamtverbrauch", 11721, None), True)


def test_no_key_ever_removed():
    section("G · Kein Key verschwindet aus dem Datensatz")
    import get_lan_data
    setup_modules()
    BOX["payload"] = box_payload(EPOCH, 3000, 11_721_176, 105_621)
    get_lan_data.run()
    before = set(entry().keys())
    check("Einspeisung zunächst vorhanden", "Gesamteinspeisung" in before, True)

    # Nacht: Export meldet 0 -> Wert wird gar nicht erst gelesen
    BOX["payload"] = box_payload(EPOCH + 60, 3100, 11_721_200, 0)
    get_lan_data.run()
    check("Einspeisungs-Key bleibt erhalten",
          "Gesamteinspeisung" in entry(), True)
    check("Einspeisungs-Wert unverändert",
          entry()["Gesamteinspeisung"], 105.621)

    # Unveränderte Antwort schreibt gar nichts -> Keys bleiben ebenfalls
    r = get_lan_data.run()
    check("unveränderte Antwort schreibt nichts", r.updated, False)
    check("Key-Bestand identisch", set(entry().keys()), before)


def test_backup_survives_hacs_update():
    section("G · Backup überlebt ein HACS-Update")
    _stub_homeassistant()
    sys.path.insert(0, os.path.join(REPO, "..", "pkgroot_dummy"))
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "env_backup_test", os.path.join(REPO, "env_backup.py"))
    eb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(eb)

    root = tempfile.mkdtemp()
    storage = os.path.join(root, ".storage")
    os.makedirs(storage)

    class FakeHass:
        class config:
            @staticmethod
            def path(sub):
                # hass.config.path(".storage") -> <config>/.storage
                return os.path.join(root, sub)

    # env_backup leitet app/ aus seinem eigenen __file__ ab -> umbiegen
    eb.__file__ = os.path.join(root, "env_backup.py")
    app_data = os.path.join(root, "app", "data")
    app_env = os.path.join(root, "app", "env")
    os.makedirs(app_data)
    os.makedirs(app_env)

    good = {"_default": {"1": {"device_id": "Stromzaehler",
                              "Gesamtverbrauch": 15418.5,
                              "Gesamteinspeisung": 153.4}}}
    with open(os.path.join(app_data, "meter_db.json"), "w") as f:
        json.dump(good, f)
    with open(os.path.join(app_env, "secrets-n2g.env"), "w") as f:
        f.write("IONA_BOX=1.2.3.4\n")

    eb.backup_env_files(FakeHass)
    backup_db = os.path.join(storage, "iona_data_backup", "meter_db.json")
    check("Backup angelegt", os.path.isfile(backup_db), True)

    # HACS löscht app/data, HA läuft weiter, LAN legt Rumpf-Datensatz an
    os.remove(os.path.join(app_data, "meter_db.json"))
    with open(os.path.join(app_data, "meter_db.json"), "w") as f:
        json.dump({"_default": {"1": {"device_id": "Stromzaehler"}}}, f)
    eb.backup_env_files(FakeHass)

    with open(backup_db) as f:
        still = list(json.load(f)["_default"].values())[0]
    check("Backup NICHT durch Rumpf-Datensatz ersetzt",
          still.get("Gesamtverbrauch"), 15418.5)

    # Env-Backup darf ebenfalls nicht verschwinden, wenn app/env leer ist
    os.remove(os.path.join(app_env, "secrets-n2g.env"))
    eb.backup_env_files(FakeHass)
    check("env-Backup überlebt leeres app/env",
          os.path.isfile(os.path.join(storage, "iona_env_backup",
                                      "secrets-n2g.env")), True)

    # Restore pro Datei, obwohl andere JSONs vorhanden sind
    os.remove(os.path.join(app_data, "meter_db.json"))
    with open(os.path.join(app_data, "spotpreise_db.json"), "w") as f:
        json.dump({}, f)
    eb.restore_env_from_backup(FakeHass)
    check("meter_db.json trotz anderer JSONs wiederhergestellt",
          os.path.isfile(os.path.join(app_data, "meter_db.json")), True)

    # Keine .tmp-Reste, die als Datenbestand zählen würden
    leftovers = [f for f in os.listdir(os.path.join(storage, "iona_data_backup"))
                 if f.endswith(".tmp")]
    check("keine .tmp-Reste im Backup", leftovers, [])


# --------------------------------------------------------------------------
#  Teil B – Funktion
# --------------------------------------------------------------------------

def test_frozen_box_is_visible():
    section("F · Eingefrorene Box wird erkannt (der Kern des Fixes)")
    import get_lan_data
    setup_modules()
    BOX["payload"] = box_payload(EPOCH, 800, 15_418_500, 0)
    r = get_lan_data.run()
    check("erster Abruf schreibt", r.updated, True)
    ts_first = entry()["Gesamtverbrauch_timestamp"]

    # Box liefert unverändert dieselben Werte, aber mit frischer Abrufzeit
    for step in (60, 120, 600):
        BOX["payload"] = box_payload(EPOCH + step, 800, 15_418_500, 0)
        r = get_lan_data.run()
    check("eingefrorene Box: updated bleibt False", r.updated, False)
    check("Zeitstempel rückt NICHT vor",
          entry()["Gesamtverbrauch_timestamp"], ts_first)

    # Sobald sich der Wert ändert, läuft alles wieder
    BOX["payload"] = box_payload(EPOCH + 660, 850, 15_418_600, 0)
    r = get_lan_data.run()
    check("Werteänderung schreibt wieder", r.updated, True)
    check("Zeitstempel rückt vor",
          entry()["Gesamtverbrauch_timestamp"] != ts_first, True)


def test_web_does_not_steal_power():
    section("F · Cloud überschreibt die Momentanleistung nicht, solange LAN lebt")
    import get_lan_data, get_web_data
    setup_modules()
    BOX["payload"] = box_payload(EPOCH, 800, 15_418_500, 0)
    get_lan_data.run()

    # Cloud ist beim Zählerstand voraus, bei der Leistung veraltet
    CLOUD["payload"] = cloud_payload(
        "2026-09-14T18:20:00+02:00", 300, 15_419_000)
    r = get_web_data.run(lan_alive=True)
    check("Zählerstand korrigiert", entry()["Gesamtverbrauch"], 15419.0)
    check("Momentanleistung bleibt LAN-Wert", entry()["Momentanleistung"], 800)
    check("Datenquelle bleibt LAN", entry()["source"], "LAN")
    check("Abruf meldet Änderung", r.updated, True)


def test_web_takes_over_when_lan_silent():
    section("F · Cloud übernimmt, wenn LAN stumm ist")
    import get_lan_data, get_web_data
    setup_modules()
    BOX["payload"] = box_payload(EPOCH, 800, 15_418_500, 0)
    get_lan_data.run()

    CLOUD["payload"] = cloud_payload(
        "2026-09-14T18:30:00+02:00", 300, 15_419_000)
    get_web_data.run(lan_alive=False)
    check("Momentanleistung von der Cloud", entry()["Momentanleistung"], 300)
    check("Datenquelle wechselt auf WEB", entry()["source"], "WEB")


def test_web_cannot_lower_counter():
    section("F · Cloud kann den Zählerstand nicht senken")
    import get_lan_data, get_web_data
    setup_modules()
    BOX["payload"] = box_payload(EPOCH, 800, 15_419_557, 0)
    get_lan_data.run()
    before = entry()["Gesamtverbrauch"]
    # Realer Normalfall: die Cloud hinkt dem LAN-Register hinterher
    CLOUD["payload"] = cloud_payload(
        "2026-09-14T18:30:00+02:00", 835, 15_419_384)
    r = get_web_data.run(lan_alive=True)
    check("Zählerstand unverändert", entry()["Gesamtverbrauch"], before)
    check("nichts geschrieben", r.updated, False)
    check("Datenquelle bleibt LAN", entry()["source"], "LAN")


def test_lan_unreachable():
    section("F · Box nicht erreichbar")
    import get_lan_data
    setup_modules()
    BOX["payload"] = None
    r = get_lan_data.run()
    check("success False", r.success, False)
    check("falsy für 'if ok:'", bool(r), False)


def test_datamanager_signals():
    section("F · DataManager: Stillstands- und Stummheits-Signal")
    _stub_homeassistant()
    import importlib.util
    pkg = types.ModuleType("iona")
    pkg.__path__ = [REPO]
    sys.modules["iona"] = pkg
    from iona.data_manager import IonaDataManager, _DATA_DIR
    from iona.const import MAX_METER_MEASUREMENT_AGE

    db = os.path.join(_DATA_DIR, "meter_db.json")
    backup = db + ".testbackup"
    had = os.path.isfile(db)
    if had:
        os.replace(db, backup)

    def write(**fields):
        e = {"device_id": "Stromzaehler", "source": "LAN"}
        e.update(fields)
        os.makedirs(_DATA_DIR, exist_ok=True)
        with open(db, "w") as f:
            json.dump({"_default": {"1": e}}, f)

    def iso(minutes_ago):
        return (datetime.now(TZ) - timedelta(minutes=minutes_ago)).isoformat()

    try:
        age = IonaDataManager._meter_measurement_age

        write(Gesamtverbrauch=1.0, Gesamtverbrauch_timestamp=iso(0),
              Momentanleistung=800, Momentanleistung_timestamp=iso(0))
        check("frischer Zählerstand → kein Fallback",
              age() < MAX_METER_MEASUREMENT_AGE, True)

        # Konstante Last: Leistung steht, Zählerstand läuft → KEIN Fallback
        write(Gesamtverbrauch=1.0, Gesamtverbrauch_timestamp=iso(0),
              Momentanleistung=800, Momentanleistung_timestamp=iso(30))
        check("konstante Leistung löst NICHT aus",
              age() < MAX_METER_MEASUREMENT_AGE, True)

        # Der Zielfall
        write(Gesamtverbrauch=1.0, Gesamtverbrauch_timestamp=iso(8 * 60),
              Momentanleistung=800, Momentanleistung_timestamp=iso(0))
        check("stehender Zählerstand löst aus",
              age() >= MAX_METER_MEASUREMENT_AGE, True)
        check("Alter ≈ 8 h", int(age() // 3600), 8)

        write(Momentanleistung=800, Momentanleistung_timestamp=iso(0))
        check("ohne Gesamtverbrauch → None", age(), None)

        os.remove(db)
        check("ohne DB → None", age(), None)

        # Stummheits-Signal
        mgr = IonaDataManager.__new__(IonaDataManager)
        mgr._lan_last_success = None
        mgr._max_lan_silence = 60
        check("beim Start gilt LAN als stumm", mgr._lan_is_silent(), True)
        import time as _t
        mgr._lan_last_success = _t.monotonic()
        check("nach Erfolg nicht stumm", mgr._lan_is_silent(), False)
        mgr._lan_last_success = _t.monotonic() - 120
        check("nach 120 s stumm", mgr._lan_is_silent(), True)
    finally:
        if os.path.isfile(db):
            os.remove(db)
        if had:
            os.replace(backup, db)


def test_atomic_storage():
    section("G · Schreibvorgänge sind atomar")
    import threading
    from fetch_utils import AtomicJSONStorage
    from tinydb import TinyDB

    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "meter_db.json")

    with TinyDB(path, storage=AtomicJSONStorage) as db:
        db.insert({"device_id": "Stromzaehler", "Gesamtverbrauch": 1.0})

    torn = []
    stop = threading.Event()

    def reader():
        while not stop.is_set():
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    json.loads(fh.read())
            except FileNotFoundError:
                torn.append("fehlt")
            except ValueError:
                torn.append("halb")

    t = threading.Thread(target=reader, daemon=True)
    t.start()
    for i in range(300):
        with TinyDB(path, storage=AtomicJSONStorage) as db:
            db.update({"Gesamtverbrauch": float(i)})
    stop.set()
    t.join(timeout=5)

    check("kein Leser sah eine halbe Datei", torn, [])
    check("keine .tmp-Reste",
          [f for f in os.listdir(tmp) if f.endswith(".tmp")], [])


def test_quarantine_instead_of_delete():
    section("G · Beschädigte DB wird beiseitegelegt, nicht gelöscht")
    from fetch_utils import quarantine_corrupt_db

    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "meter_db.json")

    with open(path, "w") as f:
        json.dump({"_default": {"1": {"Gesamtverbrauch": 1.0}}}, f)
    check("gesunde Datei bleibt unangetastet", quarantine_corrupt_db(path), False)
    check("Datei existiert noch", os.path.isfile(path), True)

    with open(path, "w") as f:
        f.write("{ kaputt")
    check("beschädigte Datei wird verschoben", quarantine_corrupt_db(path), True)
    check("Original ist weg", os.path.isfile(path), False)
    saved = [f for f in os.listdir(tmp) if ".corrupt-" in f]
    check("Inhalt bleibt für die Fehlersuche erhalten", len(saved), 1)

    check("fehlende Datei ist kein Fehler", quarantine_corrupt_db(path), False)


def test_overflow_escape():
    section("G · Ausweg aus dem Rückgang-Schutz")
    from fetch_utils import value_allows_update
    check("normaler Rückgang bleibt blockiert",
          value_allows_update("Gesamtverbrauch", 11000, 15418), False)
    check("Registerüberlauf wird übernommen",
          value_allows_update("Gesamtverbrauch", 0.005, 16777.2), True)
    check("kein Überlauf bei kleinem Altwert",
          value_allows_update("Gesamtverbrauch", 0.005, 15418), False)

    # Nach einem Zählertausch meldet der Abruf den blockierten Rückgang,
    # damit der DataManager den Nutzer informieren kann.
    import get_lan_data
    setup_modules()
    BOX["payload"] = box_payload(EPOCH, 800, 15_418_500, 0)
    get_lan_data.run()
    BOX["payload"] = box_payload(EPOCH + 60, 800, 12_000_000, 0)
    r = get_lan_data.run()
    check("Rückgang gemeldet", r.rejected_decrease, True)
    check("Wert unverändert", entry()["Gesamtverbrauch"], 15418.5)


def test_failure_causes():
    section("F · Fehlerursachen werden unterschieden")
    import get_lan_data
    import requests
    setup_modules()

    def unauthorized(url, **kw):
        return _Resp({}, status=401)

    get_lan_data.requests.get = unauthorized
    r = get_lan_data.run()
    check("401 wird als Auth-Problem gemeldet", r.error, get_lan_data.ERR_AUTH)

    def server_error(url, **kw):
        return _Resp({}, status=503)

    get_lan_data.requests.get = server_error
    r = get_lan_data.run()
    check("HTTP-Fehler eigene Ursache", r.error, get_lan_data.ERR_HTTP)

    def offline(url, **kw):
        raise requests.RequestException("timeout")

    get_lan_data.requests.get = offline
    r = get_lan_data.run()
    check("Timeout eigene Ursache", r.error, get_lan_data.ERR_UNREACHABLE)
    get_lan_data.requests.get = _fake_get


def main():
    test_value_guard()
    test_no_key_ever_removed()
    test_backup_survives_hacs_update()
    test_frozen_box_is_visible()
    test_web_does_not_steal_power()
    test_web_takes_over_when_lan_silent()
    test_web_cannot_lower_counter()
    test_lan_unreachable()
    test_datamanager_signals()
    test_atomic_storage()
    test_quarantine_instead_of_delete()
    test_overflow_escape()
    test_failure_causes()

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
