"""Gemeinsame Helfer für die Datenabruf-Module.

Zwei Aufgaben:

1. `FetchResult` trennt "Abruf erfolgreich" von "Messdaten aktualisiert".
   Ein erfolgreicher HTTP-Aufruf sagt nichts darüber, ob die gelieferten
   Werte neuer sind als die gespeicherten – ohne diese Unterscheidung sieht
   ein blockierter Datenpfad im Log wie ein gesunder aus.

2. Zeitstempel-Auswertung. LAN und Web liefern unterschiedliche Formate
   (die Box ein Epoch, die Cloud einen String unbekannter Zeitzone). Die
   Regeln dafür stehen bewusst an einer Stelle, weil ein Fehler hier dazu
   führt, dass gültige Messwerte still verworfen werden.
"""

from dataclasses import dataclass
from datetime import datetime

# Zählerstände: state_class "total_increasing". Ein Rückgang gilt in Home
# Assistant als Zählerreset und erzeugt einen falschen Verbrauchs-Spike in
# den Langzeitstatistiken – deshalb dürfen diese Werte nie sinken.
CUMULATIVE_KEYS = ("Gesamtverbrauch", "Gesamteinspeisung")


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
    """False, wenn ein Zählerstand sinken würde (siehe CUMULATIVE_KEYS)."""
    if key not in CUMULATIVE_KEYS or old_value is None or new_value is None:
        return True
    try:
        return float(new_value) >= float(old_value)
    except (TypeError, ValueError):
        return True


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
