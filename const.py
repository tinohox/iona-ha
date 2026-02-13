"""Konstanten für die iona-ha Integration."""

DOMAIN = "iona"
PLATFORMS = ["sensor", "number", "switch"]

# Konfigurationsschlüssel
CONF_IONA_BOX = "IONA_BOX"
CONF_USERNAME = "USERNAME"
CONF_PASSWORD = "PASSWORD"
CONF_VISION_TARIFF = "vision_tariff"
CONF_VISION_TOOLS = "vision_tools"

# Abruf-Intervalle (Sekunden)
INTERVAL_LAN_DATA = 5
INTERVAL_WEB_DATA = 300          # 5 Minuten
INTERVAL_WEB_TOKEN = 1800        # 30 Minuten
INTERVAL_LAN_TOKEN = 5160        # 86 Minuten
INTERVAL_SPOT_PRICES = 1800      # 30 Minuten
INTERVAL_TARIFF_DATA = 86400     # 24 Stunden
INTERVAL_CALC_PREISE = 1800      # 30 Minuten
INTERVAL_VISION = 300            # 5 Minuten
INTERVAL_SENSOR_UPDATE = 5       # 5 Sekunden

# Daten-Frische (Minuten) – wenn Daten jünger sind, wird kein neuer Abruf gestartet
FRESHNESS_SPOT_PRICES = 25       # Spotpreise: 25 Minuten
FRESHNESS_TARIFF = 1380          # Tarif: 23 Stunden
FRESHNESS_VISION = 4             # Vision: 4 Minuten
FRESHNESS_METER = 1              # Meter-Daten: 1 Minute (für Web-Fallback)
