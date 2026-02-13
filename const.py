"""Konstanten für die iona-ha Integration."""

DOMAIN = "iona"
PLATFORMS = ["sensor", "number"]

# Konfigurationsschlüssel
CONF_IONA_BOX = "IONA_BOX"
CONF_USERNAME = "USERNAME"
CONF_PASSWORD = "PASSWORD"
CONF_VISION_TARIFF = "vision_tariff"

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

# API-Endpunkte
API_AUTH_URL = "https://webapp.iona-energy.com/auth"
API_N2G_BASE = "https://api.n2g-iona.net/v2"
API_ENVIAM_BASE = "https://api.enviam.de/shared/v2/enviaM/service"

# Daten-Frische (Minuten) – wenn Daten jünger sind, wird kein neuer Abruf gestartet
FRESHNESS_SPOT_PRICES = 25       # Spotpreise: 25 Minuten
FRESHNESS_TARIFF = 1380          # Tarif: 23 Stunden
FRESHNESS_BRUTTO = 25            # Bruttopreise: 25 Minuten
FRESHNESS_VISION = 4             # Vision: 4 Minuten
FRESHNESS_METER = 1              # Meter-Daten: 1 Minute (für Web-Fallback)

# Script-Timeout
SCRIPT_TIMEOUT = 30
