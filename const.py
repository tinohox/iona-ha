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

# Maximales Alter des Zählerstands (Sekunden), bevor die Cloud zum Abgleich
# herangezogen wird. Gemeint ist NICHT die Änderungszeit von meter_db.json und
# auch nicht der Abrufzeitpunkt: Box und Cloud stempeln beide "jetzt", daraus
# lässt sich kein Stillstand ablesen. Seit Gesamtverbrauch_timestamp nur noch
# bei echter Werteänderung vorrückt, misst das Alter "seit wann steht dieser
# Zählerstand" – und genau das ist das Signal.
# 10 Minuten, weil die Cloud ohnehin nur alle 5 Minuten abgefragt wird.
MAX_METER_MEASUREMENT_AGE = 600

# LAN gilt als stumm, wenn so lange kein Abruf mehr geglückt ist. Nicht fest
# 60 s: der Options-Flow lässt interval_lan bis 60 s zu, ein starrer Wert
# würde solche Anlagen dauerhaft als stumm einstufen.
MAX_LAN_SILENCE_MIN = 60
LAN_SILENCE_FACTOR = 6

# Mindestabstand zwischen zwei Cloud-Abrufen, unabhängig von interval_web
# (der Options-Flow lässt dort 10 s zu). Der Web-Token wird mit den
# Vision-Abrufen geteilt – ein Rate-Limit träfe sonst auch die Preisdaten.
MIN_WEB_FETCH_INTERVAL = 120

# Lovelace Custom Cards
LOVELACE_CARD_URL = "/iona_cards/iona-card.js"
LOVELACE_VISION_CARD_URL = "/iona_cards/iona-vision-card.js"
