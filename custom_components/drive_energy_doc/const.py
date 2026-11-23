"""Konstanten des Drive Energy Docs."""

DOMAIN = "drive_energy_doc"
PANEL_PATH = "drive-energy-doc"
PANEL_URL = "/drive_energy_doc_static/drive-energy-doc-panel.js"

CONF_NAME = "name"
CONF_ENERGY = "energy"            # diesel | e5 | e10 | electric
CONF_ODOMETER = "odometer_entity"
CONF_TRACKER = "tracker_entity"
CONF_LEVEL = "level_entity"       # Tankinhalt / Ladestand in %
CONF_LEVEL_EL = "level_entity_electric"   # Plug-in-Hybrid: Ladestand des Akkus (%), eigene Ladeerkennung
CONF_CAPACITY_EL = "capacity_electric"       # Plug-in-Hybrid: Akkugröße in kWh
CONF_PHEV = "phev"              # Plug-in-Hybrid: Einträge sind Kraftstoff (l) oder Strom (kWh)
CONF_CAPACITY = "capacity"        # Liter bzw. kWh bei 100 %
CONF_MIN_INCREASE = "min_increase"
CONF_SETTLE = "settle_seconds"
CONF_MIN_DISTANCE = "min_distance"
CONF_REQUIRE_DISTANCE = "require_distance"
CONF_TK_KEY = "tankerkoenig_key"
CONF_PRICE_PROVIDER = "price_provider"  # auto | none | tankerkoenig | econtrol_at | prix_fr | minetur_es | mimit_it
CONF_EL_PRICE = "electric_price"  # Entity oder feste Zahl (EUR/kWh)
CONF_TG_TOKEN = "telegram_token"
CONF_TG_CHAT = "telegram_chat_id"
CONF_NOTIFY = "notify_service"    # optional, z. B. notify.whatsapp (nur Ausgang)
CONF_AI_TASK = "ai_task_entity"

ENERGY_ELECTRIC = "electric"
FUEL_TYPES = ["diesel", "e5", "e10"]

DEFAULT_MIN_INCREASE = 5.0
DEFAULT_SETTLE_FUEL = 60
DEFAULT_SETTLE_ELECTRIC = 600
DEFAULT_MIN_DISTANCE = 250
STATION_RADIUS_KM = 0.4
FULL_LEVEL = 95.0

CONF_KIND = "kind"
KIND_SETTINGS = "settings"
KIND_VEHICLE = "vehicle"

CONF_WA_PHONE = "wa_phone"  # je Fahrzeug: Handynummer des Fahrers
CONF_CHANNELS = "channels"  # companion | telegram | whatsapp
CONF_IMAGE = "image_entity"  # optional: Fahrzeugbild (image- oder camera-Entität), sonst automatisch vom selben Gerät
CONF_VEHICLE_TYPE = "vehicle_type"  # Fahrzeugtyp, z. B. „BMW X1 20d“; leer = Modell aus dem Geräteregister
PLATE_CODES = {'AL': 'AL', 'AD': 'AND', 'AT': 'A', 'BY': 'BY', 'BE': 'B', 'BA': 'BIH', 'BG': 'BG', 'HR': 'HR', 'CY': 'CY', 'CZ': 'CZ', 'DK': 'DK', 'EE': 'EST', 'FI': 'FIN', 'FR': 'F', 'DE': 'D', 'GR': 'GR', 'HU': 'H', 'IS': 'IS', 'IE': 'IRL', 'IT': 'I', 'XK': 'RKS', 'LV': 'LV', 'LI': 'FL', 'LT': 'LT', 'LU': 'L', 'MT': 'M', 'MD': 'MD', 'MC': 'MC', 'ME': 'MNE', 'NL': 'NL', 'MK': 'NMK', 'NO': 'N', 'PL': 'PL', 'PT': 'P', 'RO': 'RO', 'RU': 'RUS', 'SM': 'RSM', 'RS': 'SRB', 'SK': 'SK', 'SI': 'SLO', 'ES': 'E', 'SE': 'S', 'CH': 'CH', 'TR': 'TR', 'UA': 'UA', 'GB': 'UK', 'VA': 'V', 'US': 'USA'}  # ISO-Land -> Kennzeichen-Länderkennung (alle europäischen Länder + USA)
PLATE_COUNTRIES = list(PLATE_CODES)
PLATE_NAMES = {'AL': 'Albanien', 'AD': 'Andorra', 'AT': 'Österreich', 'BY': 'Belarus', 'BE': 'Belgien', 'BA': 'Bosnien und Herzegowina', 'BG': 'Bulgarien', 'HR': 'Kroatien', 'CY': 'Zypern', 'CZ': 'Tschechien', 'DK': 'Dänemark', 'EE': 'Estland', 'FI': 'Finnland', 'FR': 'Frankreich', 'DE': 'Deutschland', 'GR': 'Griechenland', 'HU': 'Ungarn', 'IS': 'Island', 'IE': 'Irland', 'IT': 'Italien', 'XK': 'Kosovo', 'LV': 'Lettland', 'LI': 'Liechtenstein', 'LT': 'Litauen', 'LU': 'Luxemburg', 'MT': 'Malta', 'MD': 'Moldau', 'MC': 'Monaco', 'ME': 'Montenegro', 'NL': 'Niederlande', 'MK': 'Nordmazedonien', 'NO': 'Norwegen', 'PL': 'Polen', 'PT': 'Portugal', 'RO': 'Rumänien', 'RU': 'Russland', 'SM': 'San Marino', 'RS': 'Serbien', 'SK': 'Slowakei', 'SI': 'Slowenien', 'ES': 'Spanien', 'SE': 'Schweden', 'CH': 'Schweiz', 'TR': 'Türkei', 'UA': 'Ukraine', 'GB': 'Vereinigtes Königreich', 'VA': 'Vatikanstadt', 'US': 'USA'}  # deutsche Ländernamen für den Kennzeichen-Dialog im Panel
CONF_PLATE_COUNTRY = "plate_country"  # Land des Kennzeichens (Darstellung), Standard: Land der HA-Installation
CONF_IMAGE_FILE = "image_file"  # hochgeladenes Fahrzeugbild (Dateiname in config/drive_energy_doc/images)
CONF_PLATE = "license_plate"  # Kennzeichen, optional
CONF_LANGUAGE = "language"  # Sprache der Bot-Antworten dieses Fahrzeugs (leer = Sprache von Home Assistant)
LANG_NAMES = {"sq": "Shqip", "be": "Беларуская", "bs": "Bosanski", "bg": "Български", "ca": "Català", "hr": "Hrvatski", "cs": "Čeština", "da": "Dansk", "nl": "Nederlands", "en": "English", "et": "Eesti", "fi": "Suomi", "fr": "Français", "de": "Deutsch", "el": "Ελληνικά", "hu": "Magyar", "is": "Íslenska", "ga": "Gaeilge", "it": "Italiano", "lv": "Latviešu", "lt": "Lietuvių", "lb": "Lëtzebuergesch", "mk": "Македонски", "mt": "Malti", "nb": "Norsk", "pl": "Polski", "pt": "Português", "ro": "Română", "ru": "Русский", "sr": "Српски", "sk": "Slovenčina", "sl": "Slovenščina", "es": "Español", "sv": "Svenska", "tr": "Türkçe", "uk": "Українська"}
