"""Daten-Manager für iona-ha.

Koordiniert alle Datenabfragen über Home Assistant's native Scheduling.
Ersetzt die alte Subprocess-/Threading-Architektur (main.py) durch
HA-konforme async_track_time_interval Tasks.

Jedes App-Skript wird als importierbare Funktion aufgerufen und läuft
im HA Executor Thread-Pool (kein Blocking im Event-Loop).
"""

import os
import logging
from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval

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
    FRESHNESS_METER,
)
from .env_utils import env_file_exists, is_vision_enabled, WEB_TOKEN_ENV, LAN_TOKEN_ENV

_LOGGER = logging.getLogger(__name__)

_SCRIPT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app")
_DATA_DIR = os.path.join(_SCRIPT_DIR, "data")


class IonaDataManager:
    """Zentrale Steuerung aller Datenabfragen für iona-ha.

    Nutzt Home Assistant's Event-Loop und Executor für eine saubere
    Integration ohne eigene Threads oder Subprozesse.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._cancel_callbacks: list = []

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
        self._schedule(self._task_web_token, INTERVAL_WEB_TOKEN)
        self._schedule(self._task_lan_token, INTERVAL_LAN_TOKEN)
        self._schedule(self._task_lan_data, INTERVAL_LAN_DATA)
        self._schedule(self._task_web_data, INTERVAL_WEB_DATA)
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
        lan_ok = await self.hass.async_add_executor_job(
            self._is_data_fresh, "meter_db.json", FRESHNESS_METER
        )
        if not lan_ok:
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
        """Web-Token erneuern."""
        _LOGGER.info("Starte: get_web_token")
        from .app.get_web_token import run as _run
        ok = await self.hass.async_add_executor_job(_run)
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
        _LOGGER.info("Starte: get_lan_data")
        from .app.get_lan_data import run as _run
        ok = await self.hass.async_add_executor_job(_run)
        _LOGGER.info("Fertig: get_lan_data → %s", "OK" if ok else "FEHLER")

    async def _task_web_data(self) -> None:
        """Web-Daten als Fallback wenn LAN nicht liefert.

        LAN schreibt alle 5s in meter_db.json.  Wenn die Datei älter als
        1 Minute ist, liefert LAN offensichtlich nicht – dann Web-Fallback.
        """
        if not await self.hass.async_add_executor_job(env_file_exists, WEB_TOKEN_ENV):
            return
        if await self.hass.async_add_executor_job(
            self._is_data_fresh, "meter_db.json", FRESHNESS_METER
        ):
            return
        _LOGGER.info("Starte: get_web_data (LAN liefert nicht, Fallback)")
        from .app.get_web_data import run as _run
        ok = await self.hass.async_add_executor_job(_run)
        _LOGGER.info("Fertig: get_web_data → %s", "OK" if ok else "FEHLER")

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
        """Vision-Berechnung – nur bei aktiviertem Tarif und vorhandenen Daten."""
        if not await self.hass.async_add_executor_job(is_vision_enabled):
            return

        def _check_brutto():
            return os.path.isfile(
                os.path.join(_DATA_DIR, "spotpreise_brutto_db.json")
            )

        if not await self.hass.async_add_executor_job(_check_brutto):
            _LOGGER.debug("Überspringe Vision: spotpreise_brutto_db.json fehlt")
            return
        _LOGGER.info("Starte: vision")
        from .app.vision import run as _run
        ok = await self.hass.async_add_executor_job(_run)
        _LOGGER.info("Fertig: vision → %s", "OK" if ok else "FEHLER")
