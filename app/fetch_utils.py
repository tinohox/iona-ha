"""Gemeinsame Helfer für die Datenabruf-Module.

Drei Aufgaben:

1. `FetchResult` trennt "Abruf erfolgreich" von "Messdaten aktualisiert".
   Ein erfolgreicher HTTP-Aufruf sagt nichts darüber, ob die gelieferten
   Werte neuer sind als die gespeicherten – ohne diese Unterscheidung sieht
   ein blockierter Datenpfad im Log wie ein gesunder aus.

2. Zeitstempel-Auswertung. LAN und Web liefern unterschiedliche Formate
   (die Box ein Epoch, die Cloud einen String unbekannter Zeitzone). Die
   Regeln dafür stehen bewusst an einer Stelle, weil ein Fehler hier dazu
   führt, dass gültige Messwerte still verworfen werden.

3. Persistenz. `AtomicJSONStorage` und `write_env_atomic` schreiben über eine
   temporäre Datei: Sensor-Coordinator und Fetch-Module greifen im
   5-Sekunden-Takt auf dieselben Dateien zu, ein halb geschriebener Stand
   blendet sonst alle Zählersensoren für einen Zyklus aus.
"""

import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime

from tinydb.storages import Storage

_LOGGER = logging.getLogger(__name__)

# Zählerstände: state_class "total_increasing". Ein Rückgang gilt in Home
# Assistant als Zählerreset und erzeugt einen falschen Verbrauchs-Spike in
# den Langzeitstatistiken – deshalb dürfen diese Werte nie sinken.
CUMULATIVE_KEYS = ("Gesamtverbrauch", "Gesamteinspeisung")

# Fehlerursachen eines Abrufs. Sie landen in FetchResult.error, weil der
# DataManager daraus den Benachrichtigungstext wählt: Bei einem 401 ist
# "Box nicht erreichbar – prüfe Strom, Netzwerk und IP" in jedem Satz falsch
# und schickt den Nutzer in die verkehrte Richtung.
# Bewusst hier und nicht in get_lan_data: so muss der DataManager für die
# Konstanten nicht das ganze Abrufmodul samt `requests` laden.
ERR_UNREACHABLE = "unreachable"
ERR_AUTH = "auth"
ERR_HTTP = "http"
ERR_CONFIG = "config"

# Die Box rechnet mit 24-Bit-Feldern (siehe die Überlaufkorrektur für die
# Momentanleistung in get_lan_data). Ob auch die Zählregister so schmal sind,
# ist unbestätigt – ZigBee Smart Energy führt die Zählerstände als 48 Bit.
# Falls doch: Ein Überlauf ließe den Wert von knapp 16 777 kWh auf nahe Null
# springen, und die Monotonie-Regel würde den Zählerstand für immer
# einfrieren. Ein solcher Sprung wird deshalb als Überlauf behandelt und
# zugelassen; Home Assistant wertet ihn bei total_increasing als Zählerreset,
# was hier genau richtig ist.
_WRAP_LIMIT_KWH = (2 ** 24) / 1000          # 16 777,216 kWh
_WRAP_NEAR_LIMIT_KWH = _WRAP_LIMIT_KWH - 50  # letzte 50 kWh vor dem Überlauf
_WRAP_RESTART_KWH = 50                       # danach steht der Zähler nahe Null


@dataclass
class FetchResult:
    """Ergebnis eines Datenabrufs.

    `__bool__` liefert `success`, damit bestehende `if result:`-Aufrufer
    unverändert weiterarbeiten.
    """

    success: bool
    updated: bool = False
    source: str = ""
    measurement_time: datetime | None = None
    error: str | None = None
    # True, wenn ein Zählerstand nur deshalb nicht geschrieben wurde, weil er
    # gesunken wäre. Hält das dauerhaft an, steckt meist ein Zählertausch
    # dahinter – und der Rückgang-Schutz würde den Wert sonst für immer
    # einfrieren, ohne dass es jemand bemerkt.
    rejected_decrease: bool = False

    def __bool__(self) -> bool:
        return self.success


def parse_ts(value) -> datetime | None:
    """Zeitstempel beliebiger Herkunft in ein datetime wandeln.

    Verarbeitet ISO-Strings (mit Offset, mit "Z" oder ohne Zeitzone) sowie
    Epoch-Sekunden als Zahl oder Zahl-String.

    Eine fehlende Zeitzone wird **nicht** ergänzt: der Wert bleibt naiv,
    damit `ts_allows_update` gemischte Zeitbasen erkennen kann, statt eine
    Zeitzone zu raten. Rät man hier falsch, verschiebt sich der Wert um den
    Offset – je nach Richtung blockiert das entweder die Cloud- oder die
    LAN-Quelle für genau diese Zeitspanne.

    None bedeutet "nicht interpretierbar".
    """
    if value is None or value == "":
        return None

    if isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value).astimezone()
        except (OverflowError, OSError, ValueError):
            # Millisekunden-Epochs landen im Jahr 58000 → out of range
            return None

    if isinstance(value, str):
        raw = value.strip()
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            pass
        try:
            return datetime.fromtimestamp(float(raw)).astimezone()
        except (ValueError, OverflowError, OSError):
            return None

    return None


def ts_allows_update(new_ts, old_ts) -> bool:
    """Darf ein Messwert mit diesem Zeitstempel geschrieben werden?

    True, wenn der neue Zeitstempel nachweislich neuer ist – oder wenn die
    beiden Werte nicht vergleichbar sind (kein gespeicherter Wert, fremdes
    Format, oder eine Seite mit und eine ohne Zeitzone).

    "Nicht vergleichbar" heißt bewusst *aktualisieren*: Einfrieren ist der
    teurere Fehler, weil es stundenlang unbemerkt bleibt. Die Zählerstände
    sind zusätzlich über `value_allows_update` abgesichert, ein Rückschritt
    ist damit auch bei falsch verstandenen Zeitstempeln ausgeschlossen.
    """
    if not old_ts:
        return True

    new_dt = parse_ts(new_ts)
    old_dt = parse_ts(old_ts)

    if new_dt is None or old_dt is None:
        return True
    if (new_dt.tzinfo is None) != (old_dt.tzinfo is None):
        return True

    return new_dt > old_dt


def value_allows_update(key: str, new_value, old_value) -> bool:
    """False, wenn ein Zählerstand sinken würde (siehe CUMULATIVE_KEYS).

    Einzige Ausnahme ist ein erkennbarer Registerüberlauf – sonst bliebe der
    Zählerstand danach für immer stehen.
    """
    if key not in CUMULATIVE_KEYS or old_value is None or new_value is None:
        return True
    try:
        new_f, old_f = float(new_value), float(old_value)
    except (TypeError, ValueError):
        return True

    if new_f >= old_f:
        return True

    if old_f >= _WRAP_NEAR_LIMIT_KWH and new_f <= _WRAP_RESTART_KWH:
        _LOGGER.warning(
            "%s springt von %s auf %s – als Registerüberlauf gewertet und "
            "übernommen. Home Assistant behandelt das als Zählerreset.",
            key, old_value, new_value,
        )
        return True

    return False


def newest(*timestamps) -> datetime | None:
    """Jüngsten interpretierbaren Zeitstempel liefern.

    Naive und zeitzonenbehaftete Werte lassen sich nicht miteinander
    vergleichen; in diesem Fall gewinnen die zeitzonenbehafteten, weil sie
    eindeutig sind.
    """
    parsed = [dt for dt in (parse_ts(ts) for ts in timestamps) if dt is not None]
    if not parsed:
        return None
    aware = [dt for dt in parsed if dt.tzinfo is not None]
    return max(aware) if aware else max(parsed)


class AtomicJSONStorage(Storage):
    """TinyDB-Storage, das über eine temporäre Datei schreibt.

    Der mitgelieferte JSONStorage kürzt die Zieldatei und schreibt sie neu.
    Liest der Sensor-Coordinator (alle 5 s) genau in dieses Fenster, sieht er
    eine halbe Datei, verwirft sie und liefert einen leeren Datensatz – alle
    Zählersensoren fallen dann für einen Zyklus auf "unknown". Genau das war
    im Verlauf als Paar `unknown → LAN` im Abstand von exakt 5 s zu sehen.

    Drei Details, die nicht weggelassen werden dürfen:

    - Das Suffix ist ``.tmp`` und nicht ``.json`` – env_backup sichert jede
      ``*.json`` aus app/data/ und zählt sie als vorhandenen Datenbestand.
    - ``fsync`` auf Datei und Verzeichnis. JSONStorage macht heute flush und
      fsync; ein tmp+replace ohne fsync wäre nach einem Stromausfall
      schlechter als der bisherige Zustand.
    - Wiederholversuch bei ``PermissionError``: unter Windows scheitert
      ``os.replace()`` auf eine Datei, die ein Leser gerade geöffnet hat.
    """

    _REPLACE_RETRIES = 5
    _REPLACE_DELAY = 0.05

    def __init__(self, path: str, encoding: str = "utf-8", **kwargs) -> None:
        super().__init__()
        self._path = path
        self._encoding = encoding
        self._kwargs = kwargs

    def read(self):
        try:
            with open(self._path, "r", encoding=self._encoding) as fh:
                raw = fh.read()
        except FileNotFoundError:
            return None
        if not raw.strip():
            return None
        return json.loads(raw)

    def write(self, data) -> None:
        directory = os.path.dirname(self._path) or "."
        os.makedirs(directory, exist_ok=True)
        tmp_path = self._path + ".tmp"

        with open(tmp_path, "w", encoding=self._encoding) as fh:
            json.dump(data, fh, **self._kwargs)
            fh.flush()
            os.fsync(fh.fileno())

        for attempt in range(self._REPLACE_RETRIES):
            try:
                os.replace(tmp_path, self._path)
                break
            except PermissionError:
                if attempt == self._REPLACE_RETRIES - 1:
                    raise
                time.sleep(self._REPLACE_DELAY)

        # Verzeichniseintrag mitschreiben; auf Windows nicht verfügbar.
        try:
            dir_fd = os.open(directory, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(dir_fd)
        except OSError:
            pass
        finally:
            os.close(dir_fd)

    def close(self) -> None:
        pass


def quarantine_corrupt_db(db_path: str) -> bool:
    """Beschädigte Datenbank zur Seite legen statt löschen.

    Ein ``os.remove()`` nimmt den gespeicherten Zählerstand mit. Ohne ihn hat
    `value_allows_update()` keinen Vergleichswert mehr, der nächste –
    womöglich niedrigere – Wert wird geschrieben, und Home Assistant bucht den
    Rückgang bei ``state_class: total_increasing`` als Zählerreset: der
    gesamte neue Wert landet als Verbrauch in der Langzeitstatistik und lässt
    sich nur von Hand korrigieren.

    Gibt True zurück, wenn eine beschädigte Datei beiseitegelegt wurde.
    """
    if not os.path.isfile(db_path):
        return False
    try:
        with open(db_path, "r", encoding="utf-8") as fh:
            json.load(fh)
        return False
    except (json.JSONDecodeError, ValueError):
        pass
    except OSError:
        return False

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = f"{db_path}.corrupt-{stamp}"
    try:
        os.replace(db_path, target)
        _LOGGER.error(
            "%s ist beschädigt und wurde nach %s verschoben. Der gespeicherte "
            "Zählerstand fehlt damit vorübergehend – beim nächsten Start wird "
            "er aus dem Backup wiederhergestellt.",
            os.path.basename(db_path), os.path.basename(target),
        )
        return True
    except OSError as err:
        _LOGGER.error("Beschädigte %s konnte nicht verschoben werden: %s",
                      os.path.basename(db_path), err)
        return False


def write_env_atomic(filepath: str, token_data: dict, mode: int = 0o600) -> None:
    """Schreibt eine .env-Datei über eine temporäre Datei.

    Die Token-Dateien werden periodisch neu geschrieben, während
    `get_lan_data` sie im 5-Sekunden-Takt liest. Ein Lesezugriff mitten im
    Schreibvorgang liefert einen abgeschnittenen Wert, `ast.literal_eval`
    scheitert – und der DataManager meldet daraufhin "Box nicht erreichbar",
    obwohl mit der Box alles in Ordnung ist. Seit die Erneuerung zusätzlich
    durch einen 401 ausgelöst werden kann, ist das Fenster größer geworden.

    Das Suffix ist ``.tmp``; Restore und Backup filtern auf ``.env``.
    """
    directory = os.path.dirname(filepath) or "."
    os.makedirs(directory, exist_ok=True)
    tmp_path = filepath + ".tmp"

    with open(tmp_path, "w", encoding="utf-8") as fh:
        for key, value in token_data.items():
            fh.write(f"{key.upper()}={value}\n")
        fh.flush()
        os.fsync(fh.fileno())

    os.chmod(tmp_path, mode)
    os.replace(tmp_path, filepath)
