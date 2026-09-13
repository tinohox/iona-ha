"""Konstanten für die iona-ha Integration."""

DOMAIN = "iona"
PLATFORMS = ["sensor", "number", "switch", "button"]

# Konfigurationsschlüssel
CONF_IONA_BOX = "IONA_BOX"
CONF_USERNAME = "USERNAME"
CONF_PASSWORD = "PASSWORD"
CONF_VISION_TARIFF = "vision_tariff"
CONF_VISION_TOOLS = "vision_tools"
CONF_INTERVAL_LAN = "interval_lan"
CONF_INTERVAL_WEB = "interval_web"

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

# Maximales Alter der Zähler-MESSWERTE (Sekunden), bevor der Web-Fallback
# greift. Bewusst nicht die Änderungszeit von meter_db.json: die Datei wird
# schon dann neu geschrieben, wenn sich nur die Momentanleistung bewegt –
# ein seit Stunden eingefrorener Zählerstand bliebe dabei unbemerkt.
# 10 Minuten, weil die Cloud selbst nur alle 5 Minuten abgefragt wird und
# frischere Werte darüber gar nicht zu holen sind.
MAX_METER_MEASUREMENT_AGE = 600

# Lovelace Custom Cards
LOVELACE_CARD_URL = "/iona_cards/iona-card.js"
LOVELACE_VISION_CARD_URL = "/iona_cards/iona-vision-card.js"
