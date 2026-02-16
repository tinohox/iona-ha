"""Brutto-Endkundenpreise aus Spotpreisen und Tarifdaten berechnen.

Liest spotpreise_db.json und tariff_db.json, addiert alle variablen
Kosten (Netzentgelt, Umlagen, Steuern, MwSt.) und speichert das
Ergebnis in spotpreise_brutto_db.json.
"""

import json
import logging
import os
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR / "data"
SPOTPREISE_FILE = DATA_DIR / "spotpreise_db.json"
TARIFF_FILE = DATA_DIR / "tariff_db.json"
OUTPUT_FILE = DATA_DIR / "spotpreise_brutto_db.json"


def _load_json(filepath: Path) -> dict:
    with open(filepath, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _save_json(data: dict, filepath: Path) -> None:
    """Speichert Preise mit 2 Dezimalstellen."""
    entries = []
    for key, entry in data["_default"].items():
        price_str = f"{entry['price']:.2f}"
        entries.append(
            f'"{key}": {{"timestamp": "{entry["timestamp"]}", "price": {price_str}}}'
        )
    json_str = '{"_default": {' + ", ".join(entries) + "}}"
    with open(filepath, "w", encoding="utf-8") as fh:
        fh.write(json_str)


def _get_variable_costs(tariff: dict) -> float:
    """Extrahiert alle variablen Kosten aus dem Tarif (ct/kWh brutto).

    Berücksichtigt: Arbeitspreis, Netzentgelt, §19 StromNEV,
    Konzessionsabgabe, Stromsteuer, Offshore-Umlage, KWK-Umlage,
    EEG-Umlage, Umlage abschaltbare Lasten.
    """
    costs = 0.0

    if tariff.get("workingPrice"):
        costs += tariff["workingPrice"].get("gross", 0.0)

    tpc = tariff.get("thirdPartyCost", {}) or {}

    cost_keys = [
        "gridWorkingPrice",
        "gridFedInRegulation",
        "concessionLevy",
        "energyTax",
        "offshoreLevy",
        "powerHeatCouplingLevy",
        "renewableEnergyLevy",
        "defeatableLoadLevy",
    ]
    for key in cost_keys:
        component = tpc.get(key)
        if component:
            costs += component.get("gross", 0.0)

    return costs


def _convert_spot_to_brutto(
    spotpreise: dict, zusatzkosten_ct_kwh: float, mwst_faktor: float = 1.19
) -> dict:
    """Konvertiert Spotpreise (€/MWh netto) zu Brutto-Endkundenpreisen (€/MWh)."""
    brutto = {"_default": {}}
    zusatzkosten_eur_mwh = zusatzkosten_ct_kwh * 10

    for key, entry in spotpreise.get("_default", {}).items():
        spot_brutto = entry["price"] * mwst_faktor
        brutto_total = round(spot_brutto + zusatzkosten_eur_mwh, 2)
        brutto["_default"][key] = {
            "timestamp": entry["timestamp"],
            "price": brutto_total,
        }

    return brutto


def run() -> bool:
    """Bruttopreise berechnen und speichern. Gibt True bei Erfolg zurück."""
    if not SPOTPREISE_FILE.exists():
        _LOGGER.warning("calc_preise: spotpreise_db.json nicht vorhanden")
        return False
    if not TARIFF_FILE.exists():
        _LOGGER.warning("calc_preise: tariff_db.json nicht vorhanden")
        return False

    try:
        spotpreise = _load_json(SPOTPREISE_FILE)
        tariff = _load_json(TARIFF_FILE)
    except (json.JSONDecodeError, OSError) as err:
        _LOGGER.error("calc_preise: Fehler beim Laden – %s", err)
        return False

    zusatzkosten = _get_variable_costs(tariff)
    brutto = _convert_spot_to_brutto(spotpreise, zusatzkosten)

    _save_json(brutto, OUTPUT_FILE)
    _LOGGER.info(
        "Bruttopreise: %d Einträge berechnet (Zusatzkosten: %.2f ct/kWh)",
        len(brutto["_default"]),
        zusatzkosten,
    )
    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(0 if run() else 1)
