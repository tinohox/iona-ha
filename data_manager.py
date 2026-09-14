"""Daten-Manager für iona-ha.

Koordiniert alle Datenabfragen über Home Assistant's native Scheduling.
Ersetzt die alte Subprocess-/Threading-Architektur (main.py) durch
HA-konforme async_track_time_interval Tasks.

Jedes App-Skript wird als importierbare Funktion aufgerufen und läuft
im HA Executor Thread-Pool (kein Blocking im Event-Loop).
"""

import os
import json
import logging
import threading
import time
from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import (
    async_track_point_in_time,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util
from homeassistant.components.persistent_notification import (
    async_create as pn_create,
    async_dismiss as pn_dismiss,
)

from .const import (
    INTERVAL_LAN_DATA,
    INTERVAL_WEB_DATA,
    INTERVAL_WEB_TOKEN,
    INTERVAL_LAN_TOKEN,
    INTERVAL_SPOT_PRICES,
    INTERVAL_TARIFF_DATA,
    INTERVAL_CALC_PREISE,
    INTERVAL_VISION,
    FRESHNESS_SPOT_PRICES,
    FRESHNESS_TARIFF,
    FRESHNESS_VISION,
    MAX_METER_MEASUREMENT_AGE,
    MAX_LAN_SILENCE_MIN,
    LAN_SILENCE_FACTOR,
    MIN_WEB_FETCH_INTERVAL,
    DOMAIN,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_INTERVAL_LAN,
    CONF_INTERVAL_WEB,
)
from .env_utils import env_file_exists, is_vision_enabled, WEB_TOKEN_ENV, LAN_TOKEN_ENV
from .app.fetch_utils import (
    ERR_AUTH,
    ERR_CONFIG,
    ERR_HTTP,
    ERR_UNREACHABLE,
    parse_ts,
)

_LOGGER = logging.getLogger(__name__)

_SCRIPT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app")
_DATA_DIR = os.path.join(_SCRIPT_DIR, "data")

# Notification IDs
_NOTIFY_AUTH_FAILED = "iona_auth_failed"
_NOTIFY_BOX_UNREACHABLE = "iona_box_unreachable"
_NOTIFY_VISION_NO_DATA = "iona_vision_no_data"
_NOTIFY_METER_STALE = "iona_meter_stale"
_NOTIFY_METER_STANDOFF = "iona_meter_standoff"

# Anzahl aufeinanderfolgender Fehler bevor eine Notification erscheint.
# Getrennt für LAN und Auth, weil die Abfrage-Intervalle stark variieren.
# LAN-Intervall ist typischerweise 5 s → 6 Versuche ≈ 30 s Toleranz.
_FAIL_THRESHOLD_LAN = 6
# Web-Token-Intervall ist deutlich größer (Minuten) → schon 2 Fehlversuche
# bedeuten längere Auszeit; trotzdem mind. 2, um Einzel-Glitches zu ignorieren.
_FAIL_THRESHOLD_AUTH = 2
# Vision-Abrufe (Spotpreise 30 min, Tarif 24 h): 2 Fehlversuche in Folge
# (≈ 1 h API-Störung bzw. dauerhaft leer bei Konten ohne Vision-Tarif).
_FAIL_THRESHOLD_VISION = 2

# Nach einem abgelehnten LAN-Token frühestens so oft neu anfordern. Ohne das
# liefe bei jedem 5-s-Abruf ein Token-Request gegen die Cloud.
_LAN_TOKEN_RETRY_COOLDOWN = 300

# So lange muss ein abgelehnter Zählerstand-Rückgang anhalten, bevor die
# Integration von einem Zählertausch ausgeht und den Nutzer informiert.
# Kurze Ausreißer (ein einzelner Fehlwert der Box) sollen nicht melden.
_METER_STANDOFF_SECONDS = 6 * 3600

_LAN_STATE_BY_REASON = {
    ERR_UNREACHABLE: "LAN nicht erreichbar",
    ERR_AUTH: "LAN weist den Token ab",
    ERR_HTTP: "LAN antwortet fehlerhaft",
    ERR_CONFIG: "LAN nicht konfiguriert",
}


def _lan_failure_notification(reason: str, ip: str) -> tuple[str, str]:
    """Benachrichtigungstext passend zur Fehlerursache.

    Ein 401 heißt: Die Box ist erreichbar, akzeptiert aber den Token nicht.
    Der bisherige Einheitstext ("prüfe Strom, Netzwerk, IP") war in dem Fall
    in jedem Satz falsch und ließ Nutzer an der falschen Stelle suchen.
    """
    if reason == ERR_AUTH:
        return (
            "iONA: Anmeldung an der Box abgelehnt",
            (
                f"Die iONA Box unter **{ip}** ist erreichbar, weist den "
                "Zugangs-Token der Integration aber ab (HTTP 401).\n\n"
                "Die Integration fordert automatisch einen neuen Token an. "
                "Bleibt die Meldung bestehen, prüfe deine Zugangsdaten unter "
                "**Einstellungen → Geräte & Dienste → iona-ha → Optionen** – "
                "der Token für die Box wird über das enviaM-Konto ausgestellt."
            ),
        )
    if reason == ERR_HTTP:
        return (
            "iONA: Box antwortet fehlerhaft",
            (
                f"Die iONA Box unter **{ip}** ist erreichbar, liefert aber "
                "keine verwertbare Antwort.\n\n"
                "Häufigste Ursache: Unter dieser IP-Adresse antwortet ein "
                "anderes Gerät. Prüfe die Adresse unter **Einstellungen → "
                "Geräte & Dienste → iona-ha → Optionen**; bei DHCP kann sie "
                "sich geändert haben."
            ),
        )
    if reason == ERR_CONFIG:
        return (
            "iONA: Lokaler Zugriff nicht eingerichtet",
            (
                "Für den lokalen Zugriff auf die iONA Box fehlen Angaben "
                "(IP-Adresse oder Token).\n\n"
                "Bitte prüfe die Einstellungen unter **Einstellungen → "
                "Geräte & Dienste → iona-ha → Optionen**."
            ),
        )
    return (
        "iONA: Box nicht erreichbar",
        (
            f"Die iONA Box unter **{ip}** ist nicht erreichbar. "
            "Bitte prüfe, ob die Box eingeschaltet und im Netzwerk ist, "
            "und ob die IP-Adresse unter "
            "**Einstellungen → Geräte & Dienste → iona-ha → Optionen** "
            "korrekt ist.\n\n"
            "Hängt die Box im WLAN, hat sie dort eine **andere IP-Adresse** "
            "als am LAN-Anschluss."
        ),
    )


class IonaDataManager:
    """Zentrale Steuerung aller Datenabfragen für iona-ha.

    Nutzt Home Assistant's Event-Loop und Executor für eine saubere
    Integration ohne eigene Threads oder Subprozesse.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._cancel_callbacks: list = []
        self._meter_db_lock = threading.Lock()
        self._auth_fail_count: int = 0
        self._lan_fail_count: int = 0
        # Edge-Trigger-Flags: Notification nur einmal beim Übergang senden,
        # damit nachgelagerte Automationen (z. B. Mail-Weiterleitung) nicht
        # bei jedem 5-s-Tick erneut feuern.
        self._lan_unreachable_notified: bool = False
        self._auth_failed_notified: bool = False
        self._vision_fail_count: int = 0
        self._vision_no_data_notified: bool = False
        # One-Shot-Timer für die minutengenaue Vision-Neuberechnung
        self._vision_recalc_cancel = None
        # Letzter geloggter Zustand des Zählerpfads – damit Zustandswechsel
        # auf INFO erscheinen, der 5-s-Normalbetrieb aber nicht ins Log spamt.
        self._meter_state: str | None = None
        # Monotone Uhr: wann ist zuletzt ein LAN-Abruf geglückt. Bewusst im
        # Speicher statt aus der Datei abgeleitet – die Zeitstempel in
        # meter_db.json beantworten seit 2.3.0 eine andere Frage
        # ("seit wann steht dieser Wert").
        self._lan_last_success: float | None = None
        self._max_lan_silence: int = MAX_LAN_SILENCE_MIN
        self._web_last_run: float | None = None
        self._meter_stale_notified: bool = False
        # Ursache der zuletzt verschickten LAN-Meldung; wechselt sie, wird neu
        # benachrichtigt statt den alten – dann falschen – Text stehenzulassen.
        self._lan_notified_reason: str | None = None
        self._lan_token_retry_at: float | None = None
        self._lan_token_renewing: bool = False
        self._decrease_rejected_since: float | None = None
        self._meter_standoff_notified: bool = False

    # ------------------------------------------------------------------ #
    #  Lifecycle                                                          #
    # ------------------------------------------------------------------ #

    async def async_start(self) -> None:
        """Starte initiale Datenabfrage und periodische Tasks."""
        _LOGGER.info("iona-ha Datenmanager wird gestartet")

        # Sicherstellen, dass data/ existiert
        await self.hass.async_add_executor_job(
            os.makedirs, _DATA_DIR, 0o755, True
        )

        # Initiale Daten holen (sequentiell mit Abhängigkeiten)
        try:
            await self._run_initial_fetch()
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Fehler bei der initialen Datenabfrage – Integration startet trotzdem")

        # Periodische Tasks registrieren
        # LAN/Web-Intervalle aus ConfigEntry (oder Defaults)
        entries = self.hass.config_entries.async_entries(DOMAIN)
        if entries:
            entry = entries[0]
            lan_interval = int(entry.data.get(CONF_INTERVAL_LAN, INTERVAL_LAN_DATA))
            web_interval = int(entry.data.get(CONF_INTERVAL_WEB, INTERVAL_WEB_DATA))
        else:
            lan_interval = INTERVAL_LAN_DATA
            web_interval = INTERVAL_WEB_DATA

        self._max_lan_silence = max(
            MAX_LAN_SILENCE_MIN, LAN_SILENCE_FACTOR * lan_interval
        )

        self._schedule(self._task_web_token, INTERVAL_WEB_TOKEN)
        self._schedule(self._task_lan_token, INTERVAL_LAN_TOKEN)
        self._schedule(self._task_lan_data, lan_interval)
        self._schedule(self._task_web_data, web_interval)
        self._schedule(self._task_spot_prices, INTERVAL_SPOT_PRICES)
        self._schedule(self._task_tariff_data, INTERVAL_TARIFF_DATA)
        self._schedule(self._task_calc_preise, INTERVAL_CALC_PREISE)
        self._schedule(self._task_vision, INTERVAL_VISION)

        _LOGGER.info("iona-ha Datenmanager gestartet – %d Tasks aktiv", len(self._cancel_callbacks))

    async def async_stop(self) -> None:
        """Stoppe alle periodischen Tasks."""
        for cancel in self._cancel_callbacks:
            cancel()
        self._cancel_callbacks.clear()
        if self._vision_recalc_cancel:
            self._vision_recalc_cancel()
            self._vision_recalc_cancel = None
        _LOGGER.info("iona-ha Datenmanager gestoppt")

    # ------------------------------------------------------------------ #
    #  Scheduling                                                         #
    # ------------------------------------------------------------------ #

    def _schedule(self, coro_func, interval_seconds: int) -> None:
        """Registriert eine Coroutine als periodischen Task."""
        async def _wrapper(_now=None):
            try:
                await coro_func()
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Fehler in periodischem Task %s", coro_func.__name__)

        cancel = async_track_time_interval(
            self.hass, _wrapper, timedelta(seconds=interval_seconds)
        )
        self._cancel_callbacks.append(cancel)

    # ------------------------------------------------------------------ #
    #  Hilfsfunktionen                                                    #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _is_data_fresh(filename: str, max_age_minutes: int) -> bool:
        """Prüft ob eine Datendatei existiert und frisch genug ist."""
        filepath = os.path.join(_DATA_DIR, filename)
        if not os.path.isfile(filepath):
            return False
        try:
            mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
            age_seconds = (datetime.now() - mtime).total_seconds()
            return age_seconds < max_age_minutes * 60
        except OSError:
            return False

    @staticmethod
    def _meter_measurement_age() -> float | None:
        """Wie lange steht der Zählerstand schon unverändert (Sekunden)?

        Ausgewertet wird ausschließlich `Gesamtverbrauch`. Seine Zeitmarke
        rückt seit 2.3.0 nur noch bei echter Werteänderung vor, das Alter ist
        damit ein brauchbares Stillstands-Signal.

        `Momentanleistung` wird bewusst NICHT mehr mitgeprüft: Läuft eine Last
        konstant, bleibt der Leistungswert minutenlang gleich, seine Zeitmarke
        altert – und der Fallback würde bei einer völlig gesunden Anlage
        auslösen. Die Erreichbarkeit deckt `_lan_is_silent()` ab.

        `Gesamteinspeisung` bleibt außen vor: ohne PV steht das Exportregister
        dauerhaft still, und die Cloud liefert es ohnehin nicht.

        None = kein verwertbarer Zeitstempel (gilt als veraltet).
        """
        filepath = os.path.join(_DATA_DIR, "meter_db.json")
        if not os.path.isfile(filepath):
            return None
        try:
            with open(filepath, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError, ValueError):
            return None

        try:
            entries = list(data.get("_default", {}).values())
        except AttributeError:
            return None

        entry = next(
            (e for e in entries
             if isinstance(e, dict) and e.get("device_id") == "Stromzaehler"),
            None,
        )
        if entry is None:
            return None

        if "Gesamtverbrauch" not in entry:
            return None
        stamp = parse_ts(entry.get("Gesamtverbrauch_timestamp"))
        if stamp is None:
            return None
        now = dt_util.now() if stamp.tzinfo else datetime.now()
        return (now - stamp).total_seconds()

    def _lan_is_silent(self) -> bool:
        """True, wenn seit `_max_lan_silence` kein LAN-Abruf mehr geglückt ist.

        Beim Start (noch kein Abruf) gilt LAN als stumm, damit die Cloud die
        Sensoren sofort mit Werten versorgen kann.
        """
        if self._lan_last_success is None:
            return True
        return (time.monotonic() - self._lan_last_success) > self._max_lan_silence

    def _check_meter_standoff(self, rejected: bool) -> None:
        """Meldet einen dauerhaft blockierten Zählerstand.

        Zählerstände dürfen nicht sinken – sonst wertet Home Assistant den
        Rückgang bei `total_increasing` als Zählerreset und bucht den vollen
        neuen Wert als Verbrauch. Nach einem Zählertausch meldet die Box aber
        dauerhaft einen niedrigeren Stand, und der Schutz würde den Sensor
        ohne diesen Hinweis für immer einfrieren.

        Bewusst nur eine Meldung und keine automatische Übernahme: Die wäre
        nicht rückgängig zu machen.
        """
        if not rejected:
            self._decrease_rejected_since = None
            if self._meter_standoff_notified:
                pn_dismiss(self.hass, _NOTIFY_METER_STANDOFF)
                self._meter_standoff_notified = False
            return

        now = time.monotonic()
        if self._decrease_rejected_since is None:
            self._decrease_rejected_since = now
            return
        if self._meter_standoff_notified:
            return
        if (now - self._decrease_rejected_since) < _METER_STANDOFF_SECONDS:
            return

        pn_create(
            self.hass,
            (
                "Die iONA Box meldet seit mehreren Stunden einen **niedrigeren "
                "Zählerstand** als den gespeicherten. Die Integration übernimmt "
                "ihn nicht, weil Home Assistant einen Rückgang als Zählerreset "
                "wertet und den vollen Wert als Verbrauch verbuchen würde.\n\n"
                "Der Zählerstand-Sensor steht deshalb still. Wurde dein Zähler "
                "**getauscht**, ist das zu erwarten – dann muss der gespeicherte "
                "Wert einmalig verworfen werden:\n\n"
                "1. Home Assistant stoppen\n"
                "2. `custom_components/iona/app/data/meter_db.json` löschen\n"
                "3. Home Assistant starten\n\n"
                "Die Langzeitstatistik lässt sich danach unter "
                "**Entwicklerwerkzeuge → Statistiken** korrigieren."
            ),
            title="iONA: Zählerstand blockiert",
            notification_id=_NOTIFY_METER_STANDOFF,
        )
        self._meter_standoff_notified = True

    def _notify_meter_stale(self, stale: bool) -> None:
        """Edge-getriggerte Meldung: Box antwortet, Zählerstand steht still.

        Ohne diese Meldung wäre der Zustand für den Nutzer unsichtbar – die
        Datenquelle bleibt bewusst auf LAN, weil die Momentanleistung weiterhin
        von der Box kommt.
        """
        if stale:
            if self._meter_stale_notified:
                return
            pn_create(
                self.hass,
                (
                    "Die iONA Box ist erreichbar, ihr **Zählerstand steht aber "
                    "seit einiger Zeit still**. Die Integration gleicht den Wert "
                    "so lange über die enviaM-Cloud ab; die Momentanleistung "
                    "kommt weiterhin direkt von der Box.\n\n"
                    "Mögliche Ursachen:\n"
                    "- Der Stromzähler meldet seinen Zählerstand nur selten an "
                    "die Box.\n"
                    "- Die Verbindung zwischen Zähler und Box ist gestört – "
                    "prüfe den Sitz des Lesekopfs.\n\n"
                    "Diese Meldung verschwindet automatisch, sobald die Box "
                    "wieder einen steigenden Zählerstand liefert."
                ),
                title="iONA: Zählerstand der Box steht still",
                notification_id=_NOTIFY_METER_STALE,
            )
            self._meter_stale_notified = True
            return

        if self._meter_stale_notified:
            pn_dismiss(self.hass, _NOTIFY_METER_STALE)
            self._meter_stale_notified = False
            _LOGGER.info("Zählerstand der Box läuft wieder")

    def _log_meter_state(self, state: str, detail: str = "") -> None:
        """Loggt den Zählerpfad-Zustand nur beim Wechsel (INFO)."""
        if state == self._meter_state:
            return
        _LOGGER.info(
            "Zählerdaten: Zustand %s → %s%s",
            self._meter_state or "unbekannt", state,
            f" ({detail})" if detail else "",
        )
        self._meter_state = state

    def _handle_vision_fetch_result(self, ok: bool, source: str) -> None:
        """Edge-getriggerte Notification, wenn enviaM keine Vision-Daten liefert.

        Greift bei vorübergehenden API-Störungen ebenso wie bei Konten ohne
        gebuchten "mein Strom Vision"-Tarif (die Schnittstelle liefert dann
        dauerhaft keine Preisdaten). Wie bei der Box-Meldung wird nur EINMAL
        beim Erreichen der Schwelle benachrichtigt; sobald wieder Daten
        kommen, verschwindet die Meldung automatisch.
        """
        if ok:
            if self._vision_no_data_notified:
                pn_dismiss(self.hass, _NOTIFY_VISION_NO_DATA)
                self._vision_no_data_notified = False
                _LOGGER.info("Vision-Daten wieder verfügbar (%s)", source)
            self._vision_fail_count = 0
            return

        self._vision_fail_count += 1
        _LOGGER.debug(
            "Vision-Abruf fehlgeschlagen (%s, %d/%d)",
            source, self._vision_fail_count, _FAIL_THRESHOLD_VISION,
        )
        if (
            self._vision_fail_count >= _FAIL_THRESHOLD_VISION
            and not self._vision_no_data_notified
        ):
            pn_create(
                self.hass,
                (
                    "Die enviaM-Schnittstelle liefert aktuell **keine Daten für "
                    "'mein Strom Vision'** (Spotpreise/Tarifdaten).\n\n"
                    "Mögliche Ursachen:\n"
                    "- Die enviaM-API ist vorübergehend gestört – dann behebt sich "
                    "das Problem in der Regel von selbst, diese Meldung verschwindet "
                    "automatisch.\n"
                    "- Für dein Konto ist **kein dynamischer Tarif 'mein Strom "
                    "Vision'** gebucht – deaktiviere in diesem Fall die Vision-Option "
                    "unter **Einstellungen → Geräte & Dienste → iona-ha → Optionen**."
                ),
                title="iONA: Vision-Preisdaten nicht verfügbar",
                notification_id=_NOTIFY_VISION_NO_DATA,
            )
            self._vision_no_data_notified = True

    # ------------------------------------------------------------------ #
    #  Initiale Datenabfrage                                              #
    # ------------------------------------------------------------------ #

    async def _run_initial_fetch(self) -> None:
        """Initiale Abfolge: Tokens → Daten → Berechnung.

        Holt IMMER alle Daten beim Start, damit Sensoren sofort Werte haben.
        Freshness-Checks erst bei den periodischen Tasks.
        """
        _LOGGER.info("Starte initiale Datenabfrage")

        # 1. Web-Token IMMER holen (Token kann abgelaufen sein)
        await self._task_web_token()

        # 2. LAN-Token holen
        await self._task_lan_token()

        # 3. Zählerdaten holen (LAN bevorzugt, Web nur als Fallback)
        await self._task_lan_data()
        # Hat LAN nicht geliefert, holt die Cloud die Startwerte. Bewusst über
        # den Abruf-Erfolg und nicht über das Datenalter: beim Start gibt es
        # noch keine Historie, an der sich ein Stillstand erkennen ließe.
        if self._lan_last_success is None:
            await self._task_web_data()

        # 4. Spotpreise IMMER holen beim Start
        await self._task_spot_prices_force()

        # 5. Tarifdaten IMMER holen beim Start
        await self._task_tariff_data_force()

        # 6. Bruttopreise berechnen
        await self._task_calc_preise()

        # 7. Vision berechnen
        await self._task_vision()

        _LOGGER.info("Initiale Datenabfrage abgeschlossen")

    # ------------------------------------------------------------------ #
    #  Task-Funktionen (jeweils ein App-Modul)                            #
    # ------------------------------------------------------------------ #

    async def _task_web_token(self) -> None:
        """Web-Token erneuern (Refresh bevorzugt, Login als Fallback)."""
        _LOGGER.info("Starte: get_web_token")
        from .app.get_web_token import run as _run

        # Credentials aus ConfigEntry holen (nicht aus .env)
        username = ""
        password = ""
        entries = self.hass.config_entries.async_entries(DOMAIN)
        if entries:
            entry = entries[0]
            username = entry.data.get(CONF_USERNAME, "")
            password = entry.data.get(CONF_PASSWORD, "")

        ok = await self.hass.async_add_executor_job(
            _run, username, password
        )

        if ok:
            if self._auth_failed_notified:
                pn_dismiss(self.hass, _NOTIFY_AUTH_FAILED)
                self._auth_failed_notified = False
            self._auth_fail_count = 0
        else:
            self._auth_fail_count += 1
            # Edge-Trigger: nur EINMAL beim Erreichen der Schwelle benachrichtigen.
            if (
                self._auth_fail_count >= _FAIL_THRESHOLD_AUTH
                and not self._auth_failed_notified
            ):
                pn_create(
                    self.hass,
                    (
                        "Die Anmeldung bei iONA/enviaM ist fehlgeschlagen. "
                        "Bitte prüfe deine Zugangsdaten unter "
                        "**Einstellungen → Geräte & Dienste → iona-ha → Optionen**."
                    ),
                    title="iONA: Authentifizierung fehlgeschlagen",
                    notification_id=_NOTIFY_AUTH_FAILED,
                )
                self._auth_failed_notified = True

        _LOGGER.info("Fertig: get_web_token → %s", "OK" if ok else "FEHLER")

    async def _task_lan_token(self) -> None:
        """LAN-Token erneuern – nur wenn Web-Token vorhanden."""
        if not await self.hass.async_add_executor_job(env_file_exists, WEB_TOKEN_ENV):
            _LOGGER.debug("Überspringe LAN-Token: Kein Web-Token vorhanden")
            return
        _LOGGER.info("Starte: get_lan_token")
        from .app.get_lan_token import run as _run
        ok = await self.hass.async_add_executor_job(_run)
        _LOGGER.info("Fertig: get_lan_token → %s", "OK" if ok else "FEHLER")

    async def _task_lan_data(self) -> None:
        """Lokale Zählerdaten von der iONA Box abrufen."""
        if not await self.hass.async_add_executor_job(env_file_exists, LAN_TOKEN_ENV):
            _LOGGER.debug("Überspringe LAN-Daten: Kein LAN-Token vorhanden")
            return
        _LOGGER.debug("Starte: get_lan_data")
        from .app.get_lan_data import run as _run
        lock = self._meter_db_lock

        def _locked_run():
            with lock:
                return _run()

        result = await self.hass.async_add_executor_job(_locked_run)
        ok = bool(result)

        if ok:
            self._lan_last_success = time.monotonic()
            self._check_meter_standoff(result.rejected_decrease)
            if result.updated:
                self._log_meter_state("LAN aktuell")
                self._notify_meter_stale(False)
            else:
                # Box antwortet, liefert aber keine neuen Messwerte. Das ist
                # der Fall, den ein reines True/False unsichtbar macht.
                self._log_meter_state(
                    "LAN ohne neue Messwerte",
                    f"letzte Messzeit {result.measurement_time}",
                )
            if self._lan_unreachable_notified:
                pn_dismiss(self.hass, _NOTIFY_BOX_UNREACHABLE)
                self._lan_unreachable_notified = False
            self._lan_notified_reason = None
            self._lan_fail_count = 0
        else:
            self._lan_fail_count += 1
            reason = result.error or ERR_UNREACHABLE
            self._log_meter_state(_LAN_STATE_BY_REASON.get(
                reason, "LAN nicht erreichbar"))

            if reason == ERR_AUTH:
                await self._renew_lan_token_after_auth_error()

            # Edge-Trigger: nur EINMAL beim Erreichen der Schwelle benachrichtigen,
            # nicht bei jedem 5-s-Fehlversuch (sonst Mail-Flut bei weitergeleiteten
            # persistent_notification-Events). Zusätzlich neu benachrichtigen,
            # wenn sich die URSACHE ändert – sonst liest der Nutzer weiter
            # "prüfe die IP", obwohl es längst ein Token-Problem ist.
            if self._lan_fail_count >= _FAIL_THRESHOLD_LAN and (
                self._lan_notified_reason != reason
            ):
                from .env_utils import read_env_file, SECRETS_ENV
                secrets = await self.hass.async_add_executor_job(
                    read_env_file, SECRETS_ENV
                )
                ip = secrets.get("IONA_BOX", "unbekannt")
                title, message = _lan_failure_notification(reason, ip)
                pn_create(
                    self.hass,
                    message,
                    title=title,
                    notification_id=_NOTIFY_BOX_UNREACHABLE,
                )
                self._lan_unreachable_notified = True
                self._lan_notified_reason = reason

        _LOGGER.debug("Fertig: get_lan_data → %s", "OK" if ok else "FEHLER")

    async def _renew_lan_token_after_auth_error(self) -> None:
        """Nach einem 401 sofort einen neuen LAN-Token holen.

        Ohne das wartet die Integration bis zu 86 Minuten auf den regulären
        Turnus (INTERVAL_LAN_TOKEN) und bleibt in der Zwischenzeit blind –
        schlägt die turnusmäßige Erneuerung dann ebenfalls fehl, dauerhaft.

        Der Cooldown-Stempel wird VOR dem await gesetzt und ein
        In-Flight-Flag gehalten: `async_track_time_interval` unterdrückt keine
        Überlappung, und der LAN-Task feuert alle 5 s, während der
        Token-Abruf bis zu 15 s braucht. Ohne beides liefen mehrere
        Token-Anfragen parallel in dieselbe Datei.
        """
        if self._lan_token_renewing:
            return
        now = time.monotonic()
        if (
            self._lan_token_retry_at is not None
            and now < self._lan_token_retry_at
        ):
            return

        self._lan_token_retry_at = now + _LAN_TOKEN_RETRY_COOLDOWN
        self._lan_token_renewing = True
        _LOGGER.info("LAN-Token wurde abgelehnt – fordere sofort einen neuen an")
        try:
            await self._task_lan_token()
        finally:
            self._lan_token_renewing = False

    async def _task_web_data(self) -> None:
        """Cloud-Abruf als Fallback. Zwei unabhängige Auslöser:

        1. **LAN ist stumm** – seit `_max_lan_silence` kein erfolgreicher
           Abruf. Dann übernimmt die Cloud alle Werte.
        2. **LAN antwortet, der Zählerstand steht** – `Gesamtverbrauch` hat
           sich seit `MAX_METER_MEASUREMENT_AGE` nicht verändert. Dann gleicht
           die Cloud nur den Zählerstand ab; die Momentanleistung bleibt beim
           sekundengenauen LAN-Wert (`lan_alive`).

        Erreichbarkeit und Datenqualität sind zwei verschiedene Fragen und
        brauchen deshalb zwei Schwellen.
        """
        if not await self.hass.async_add_executor_job(env_file_exists, WEB_TOKEN_ENV):
            return

        lan_silent = self._lan_is_silent()
        age = await self.hass.async_add_executor_job(self._meter_measurement_age)
        meter_stale = age is None or age >= MAX_METER_MEASUREMENT_AGE

        if not lan_silent and not meter_stale:
            return

        # Mindestabstand unabhängig vom eingestellten interval_web.
        now = time.monotonic()
        if (
            self._web_last_run is not None
            and (now - self._web_last_run) < MIN_WEB_FETCH_INTERVAL
        ):
            return
        self._web_last_run = now

        if lan_silent:
            grund = "LAN stumm"
        else:
            grund = (
                "Zählerstand steht seit "
                + ("unbekannt lange" if age is None else f"{int(age)} s")
            )

        _LOGGER.info("Starte: get_web_data (Fallback – %s)", grund)
        from .app.get_web_data import run as _run
        lock = self._meter_db_lock

        def _locked_run():
            with lock:
                return _run(lan_alive=not lan_silent)

        result = await self.hass.async_add_executor_job(_locked_run)
        if not result:
            self._log_meter_state("WEB fehlgeschlagen", result.error or "")
        elif result.updated and lan_silent:
            self._log_meter_state("WEB aktuell")
        elif result.updated:
            # Erst jetzt steht fest, dass der Zählerstand der Box wirklich
            # falsch war: Die Cloud hatte einen höheren Wert und hat ihn
            # geschrieben. Das bloße Alter reicht als Begründung nicht – bei
            # sehr kleiner Last (5 W braucht 12 Minuten für eine Wattstunde)
            # steht das Register auch bei einer völlig gesunden Anlage länger
            # als die Schwelle still. Dann liegt der Cloud-Wert aber darunter
            # und wird verworfen, hier kommt niemand vorbei.
            self._log_meter_state("LAN mit veralteten Zählerständen")
            self._notify_meter_stale(True)
        else:
            # Cloud antwortet, hat aber selbst keinen neueren Messwert –
            # dann kann der Fallback nicht helfen.
            self._log_meter_state(
                "WEB ohne neue Messwerte",
                f"letzte Messzeit {result.measurement_time}",
            )
        _LOGGER.info(
            "Fertig: get_web_data → %s (geschrieben: %s)",
            "OK" if result else "FEHLER", result.updated,
        )

    async def _task_spot_prices(self) -> None:
        """Spotpreise von enviaM abrufen – nur wenn Vision aktiv und veraltet."""
        if not await self.hass.async_add_executor_job(is_vision_enabled):
            return
        if not await self.hass.async_add_executor_job(env_file_exists, WEB_TOKEN_ENV):
            return
        if await self.hass.async_add_executor_job(
            self._is_data_fresh, "spotpreise_db.json", FRESHNESS_SPOT_PRICES
        ):
            return
        _LOGGER.info("Starte: get_spot_prices")
        try:
            from .app.get_spot_prices import run as _run
        except ImportError:
            _LOGGER.debug("Modul get_spot_prices nicht verfügbar")
            return
        ok = await self.hass.async_add_executor_job(_run)
        self._handle_vision_fetch_result(ok, "spot_prices")
        _LOGGER.info("Fertig: get_spot_prices → %s", "OK" if ok else "FEHLER")

    async def _task_spot_prices_force(self) -> None:
        """Spotpreise IMMER abrufen (für initialen Start) – nur wenn Vision aktiv."""
        if not await self.hass.async_add_executor_job(is_vision_enabled):
            _LOGGER.debug("Überspringe get_spot_prices: Vision nicht aktiviert")
            return
        _LOGGER.info("Starte: get_spot_prices (initial)")
        try:
            from .app.get_spot_prices import run as _run
        except ImportError:
            _LOGGER.debug("Modul get_spot_prices nicht verfügbar")
            return
        ok = await self.hass.async_add_executor_job(_run)
        self._handle_vision_fetch_result(ok, "spot_prices")
        _LOGGER.info("Fertig: get_spot_prices → %s", "OK" if ok else "FEHLER")

    async def _task_tariff_data(self) -> None:
        """Tarifdaten von enviaM abrufen – nur wenn Vision aktiv und veraltet."""
        if not await self.hass.async_add_executor_job(is_vision_enabled):
            return
        if not await self.hass.async_add_executor_job(env_file_exists, WEB_TOKEN_ENV):
            return
        if await self.hass.async_add_executor_job(
            self._is_data_fresh, "tariff_db.json", FRESHNESS_TARIFF
        ):
            return
        _LOGGER.info("Starte: get_tariff_data")
        try:
            from .app.get_tariff_data import run as _run
        except ImportError:
            _LOGGER.debug("Modul get_tariff_data nicht verfügbar")
            return
        ok = await self.hass.async_add_executor_job(_run)
        self._handle_vision_fetch_result(ok, "tariff_data")
        _LOGGER.info("Fertig: get_tariff_data → %s", "OK" if ok else "FEHLER")

    async def _task_tariff_data_force(self) -> None:
        """Tarifdaten IMMER abrufen (für initialen Start) – nur wenn Vision aktiv."""
        if not await self.hass.async_add_executor_job(is_vision_enabled):
            _LOGGER.debug("Überspringe get_tariff_data: Vision nicht aktiviert")
            return
        _LOGGER.info("Starte: get_tariff_data (initial)")
        try:
            from .app.get_tariff_data import run as _run
        except ImportError:
            _LOGGER.debug("Modul get_tariff_data nicht verfügbar")
            return
        ok = await self.hass.async_add_executor_job(_run)
        self._handle_vision_fetch_result(ok, "tariff_data")
        _LOGGER.info("Fertig: get_tariff_data → %s", "OK" if ok else "FEHLER")

    async def _task_calc_preise(self) -> None:
        """Bruttopreise berechnen – nur wenn Vision aktiv und Quelldaten vorhanden."""
        if not await self.hass.async_add_executor_job(is_vision_enabled):
            return

        def _check_sources():
            spot = os.path.isfile(os.path.join(_DATA_DIR, "spotpreise_db.json"))
            tariff = os.path.isfile(os.path.join(_DATA_DIR, "tariff_db.json"))
            return spot and tariff

        if not await self.hass.async_add_executor_job(_check_sources):
            _LOGGER.debug("Überspringe calc_preise: Quelldaten fehlen")
            return
        _LOGGER.info("Starte: calc_preise")
        from .app.calc_preise import run as _run
        ok = await self.hass.async_add_executor_job(_run)
        _LOGGER.info("Fertig: calc_preise → %s", "OK" if ok else "FEHLER")

    async def _task_vision(self) -> None:
        """Vision-Berechnung – eingefroren außer wenn Neuberechnung fällig."""
        if not await self.hass.async_add_executor_job(is_vision_enabled):
            return

        def _check_brutto():
            return os.path.isfile(
                os.path.join(_DATA_DIR, "spotpreise_brutto_db.json")
            )

        if not await self.hass.async_add_executor_job(_check_brutto):
            _LOGGER.debug("Überspringe Vision: spotpreise_brutto_db.json fehlt")
            return
        _LOGGER.debug("Starte: vision (force=False)")
        from .app.vision import run as _run
        ok = await self.hass.async_add_executor_job(_run, False)
        _LOGGER.debug("Fertig: vision → %s", "OK" if ok else "FEHLER")
        await self._schedule_vision_recalc()

    async def _task_vision_force(self) -> None:
        """Vision-Berechnung erzwingen – immer neu berechnen (manueller Button)."""
        if not await self.hass.async_add_executor_job(is_vision_enabled):
            return

        def _check_brutto():
            return os.path.isfile(
                os.path.join(_DATA_DIR, "spotpreise_brutto_db.json")
            )

        if not await self.hass.async_add_executor_job(_check_brutto):
            _LOGGER.debug("Überspringe Vision (force): spotpreise_brutto_db.json fehlt")
            return
        _LOGGER.info("Starte: vision (force=True)")
        from .app.vision import run as _run
        ok = await self.hass.async_add_executor_job(_run, True)
        _LOGGER.info("Fertig: vision (force) → %s", "OK" if ok else "FEHLER")
        await self._schedule_vision_recalc()

    # ------------------------------------------------------------------ #
    #  Vision-Recalc-Timer                                                #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _read_naechste_berechnung() -> str | None:
        """Liest 'naechste_berechnung' aus vision_db.json (Executor)."""
        filepath = os.path.join(_DATA_DIR, "vision_db.json")
        if not os.path.isfile(filepath):
            return None
        try:
            with open(filepath, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            items = list(data.get("_default", {}).values())
            return items[0].get("naechste_berechnung") if items else None
        except (json.JSONDecodeError, OSError, AttributeError):
            return None

    async def _schedule_vision_recalc(self) -> None:
        """Armiert einen One-Shot-Timer auf 'naechste_berechnung'.

        Der 5-Min-Task allein wäre bis zu 5 Minuten zu spät; der Timer
        sorgt für die minutengenaue Neuberechnung nach Fensterende.
        """
        if self._vision_recalc_cancel:
            self._vision_recalc_cancel()
            self._vision_recalc_cancel = None

        raw = await self.hass.async_add_executor_job(self._read_naechste_berechnung)
        if not raw:
            return

        when = dt_util.parse_datetime(raw)
        if when is None:
            return
        if when.tzinfo is None:
            when = dt_util.as_local(when)
        if when <= dt_util.now():
            return

        # Kleiner Puffer, damit der Freeze-Check (now >= recalc_time)
        # beim Feuern sicher erfüllt ist.
        when = when + timedelta(seconds=5)

        async def _on_vision_recalc(_now) -> None:
            self._vision_recalc_cancel = None
            try:
                await self._task_vision()
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Fehler bei geplanter Vision-Neuberechnung")

        self._vision_recalc_cancel = async_track_point_in_time(
            self.hass, _on_vision_recalc, when
        )
        _LOGGER.debug("Vision: Neuberechnung geplant für %s", when.isoformat())
