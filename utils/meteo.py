"""
utils/meteo.py — Météo quotidienne pour l'assistant potager
------------------------------------------------------------
Source : Open-Meteo (gratuit, sans clé API)
         https://open-meteo.com/

Fonctionnement :
  - Appel API Open-Meteo avec les coordonnées GPS configurées
  - Récupère température matin (8h) + après-midi (14h), précipitations,
    probabilité de pluie/orage, vent, code météo WMO
  - Traduit le code WMO en label lisible orienté potager
  - Enregistre automatiquement en base comme action 'observation'

Déclenchement :
  - Automatique à 05h00 chaque matin via JobQueue Telegram (bot.py)
  - Manuel via commande /meteo depuis Telegram

Zéro token Groq consommé — traitement 100% local.
"""

import logging
import requests
from datetime import datetime, date
from sqlalchemy.orm import Session

log = logging.getLogger("potager")

# ── Coordonnées GPS du potager ────────────────────────────────────────────────
METEO_LATITUDE  = 48.96082453509178
METEO_LONGITUDE = 2.2038296967715305
METEO_TIMEZONE  = "Europe/Paris"

# ── URL Open-Meteo ─────────────────────────────────────────────────────────────
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# ── Codes météo WMO → label potager ───────────────────────────────────────────
# https://open-meteo.com/en/docs#weathervariables
WMO_CODES = {
    0:  ("☀️", "Ciel dégagé"),
    1:  ("🌤️", "Principalement dégagé"),
    2:  ("⛅", "Partiellement nuageux"),
    3:  ("☁️", "Couvert"),
    45: ("🌫️", "Brouillard"),
    48: ("🌫️", "Brouillard givrant"),
    51: ("🌦️", "Bruine légère"),
    53: ("🌦️", "Bruine modérée"),
    55: ("🌦️", "Bruine dense"),
    61: ("🌧️", "Pluie légère"),
    63: ("🌧️", "Pluie modérée"),
    65: ("🌧️", "Pluie forte"),
    71: ("🌨️", "Neige légère"),
    73: ("🌨️", "Neige modérée"),
    75: ("🌨️", "Neige forte"),
    77: ("🌨️", "Grains de neige"),
    80: ("🌦️", "Averses légères"),
    81: ("🌦️", "Averses modérées"),
    82: ("🌦️", "Averses violentes"),
    85: ("🌨️", "Averses de neige"),
    86: ("🌨️", "Averses de neige fortes"),
    95: ("⛈️", "Orage"),
    96: ("⛈️", "Orage avec grêle"),
    99: ("⛈️", "Orage violent avec grêle"),
}

def _wmo_label(code: int) -> tuple[str, str]:
    """Retourne (emoji, description) pour un code WMO."""
    return WMO_CODES.get(code, ("🌡️", f"Code météo {code}"))


def _conseil_potager(wmo_code: int, temp_matin: float, temp_aprem: float,
                     precipitations: float, vent_kmh: float) -> str:
    """
    Génère un conseil potager court en fonction des conditions météo.
    Logique locale — zéro token Groq.
    """
    conseils = []

    # Gel
    if temp_matin <= 0:
        conseils.append("⚠️ Risque de gel — protéger les plantations sensibles")
    elif temp_matin <= 3:
        conseils.append("🌡️ Température basse — surveiller les jeunes plants")

    # Canicule
    if temp_aprem >= 35:
        conseils.append("🌡️ Canicule — arrosage en soirée indispensable")
    elif temp_aprem >= 28:
        conseils.append("☀️ Chaleur — arrosage en soirée recommandé")

    # Pluie / orage
    if wmo_code in (95, 96, 99):
        conseils.append("⛈️ Orage prévu — pas d'arrosage ni de traitement")
    elif precipitations >= 10:
        conseils.append("🌧️ Pluie abondante — arrosage inutile")
    elif precipitations >= 3:
        conseils.append("🌦️ Pluie légère — arrosage probablement inutile")
    elif precipitations == 0 and temp_aprem >= 22:
        conseils.append("💧 Pas de pluie prévue — penser à arroser en soirée")

    # Vent
    if vent_kmh >= 50:
        conseils.append("💨 Vent fort — vérifier tuteurs et protections")
    elif vent_kmh >= 30:
        conseils.append("💨 Vent modéré — éviter les traitements foliaires")

    # Brouillard
    if wmo_code in (45, 48):
        conseils.append("🌫️ Brouillard — risque de maladies fongiques à surveiller")

    # Bon temps pour traitement
    if (wmo_code in (0, 1, 2) and precipitations == 0
            and vent_kmh < 20 and 10 <= temp_aprem <= 28):
        conseils.append("✅ Conditions idéales pour traitements foliaires")

    return " · ".join(conseils) if conseils else "🌿 Conditions normales"


def fetch_meteo() -> dict | None:
    """
    Interroge l'API Open-Meteo et retourne un dict avec les données météo
    pertinentes pour le potager.

    Retourne None en cas d'erreur réseau.
    """
    params = {
        "latitude"            : METEO_LATITUDE,
        "longitude"           : METEO_LONGITUDE,
        "timezone"            : METEO_TIMEZONE,
        "forecast_days"       : 1,
        # Données horaires
        "hourly"              : [
            "temperature_2m",
            "precipitation_probability",
            "precipitation",
            "windspeed_10m",
            "weathercode",
        ],
        # Données journalières
        "daily"               : [
            "weathercode",
            "temperature_2m_max",
            "temperature_2m_min",
            "precipitation_sum",
            "precipitation_probability_max",
            "windspeed_10m_max",
            "sunrise",
            "sunset",
        ],
        "wind_speed_unit"     : "kmh",
        "precipitation_unit"  : "mm",
    }

    try:
        resp = requests.get(OPEN_METEO_URL, params=params, timeout=10)
        resp.raise_for_status()
        raw = resp.json()
    except requests.RequestException as e:
        log.error(f"❌ MÉTÉO ERREUR     : {e}")
        return None

    try:
        daily   = raw["daily"]
        hourly  = raw["hourly"]
        times   = hourly["time"]  # liste de "2026-03-25T00:00", "...T01:00"...

        # Extraire la valeur horaire pour une heure cible (ex: 8 → 08:00)
        def hourly_val(key: str, hour: int):
            prefix = f"T{hour:02d}:00"
            for i, t in enumerate(times):
                if t.endswith(prefix):
                    return hourly[key][i]
            return None

        wmo_code      = daily["weathercode"][0]
        temp_min      = daily["temperature_2m_min"][0]
        temp_max      = daily["temperature_2m_max"][0]
        precipitations= daily["precipitation_sum"][0] or 0.0
        proba_pluie   = daily["precipitation_probability_max"][0] or 0
        vent_max      = daily["windspeed_10m_max"][0] or 0.0
        lever_soleil  = daily["sunrise"][0]
        coucher_soleil= daily["sunset"][0]

        # Températures horaires pour le résumé potager
        temp_matin    = hourly_val("temperature_2m", 8)  or temp_min
        temp_aprem    = hourly_val("temperature_2m", 14) or temp_max
        proba_matin   = hourly_val("precipitation_probability", 8)  or 0
        proba_aprem   = hourly_val("precipitation_probability", 14) or 0

        emoji, label  = _wmo_label(wmo_code)
        conseil       = _conseil_potager(wmo_code, temp_matin, temp_aprem,
                                         precipitations, vent_max)

        return {
            "wmo_code"       : wmo_code,
            "emoji"          : emoji,
            "label"          : label,
            "temp_min"       : round(temp_min, 1),
            "temp_max"       : round(temp_max, 1),
            "temp_matin"     : round(temp_matin, 1),
            "temp_aprem"     : round(temp_aprem, 1),
            "precipitations" : round(precipitations, 1),
            "proba_pluie"    : proba_pluie,
            "proba_matin"    : proba_matin,
            "proba_aprem"    : proba_aprem,
            "vent_max_kmh"   : round(vent_max, 1),
            "lever_soleil"   : lever_soleil[-5:],   # "HH:MM"
            "coucher_soleil" : coucher_soleil[-5:], # "HH:MM"
            "conseil"        : conseil,
            "date"           : date.today().isoformat(),
        }

    except (KeyError, IndexError, TypeError) as e:
        log.error(f"❌ MÉTÉO PARSE      : {e}")
        return None


def format_meteo_commentaire(m: dict) -> str:
    """
    Formate les données météo en une ligne de commentaire pour la base.
    Stocké dans le champ `commentaire` de l'événement observation.

    Exemple :
    ☀️ Ensoleillé · Min 8°C / Max 22°C · Matin 12°C / AM 21°C ·
    Pluie 0mm (5%) · Vent 18km/h · Lever 07:12 · ✅ Conditions idéales
    """
    return (
        f"{m['emoji']} {m['label']} · "
        f"Min {m['temp_min']}°C / Max {m['temp_max']}°C · "
        f"Matin {m['temp_matin']}°C / AM {m['temp_aprem']}°C · "
        f"Pluie {m['precipitations']}mm ({m['proba_pluie']}%) · "
        f"Vent {m['vent_max_kmh']}km/h · "
        f"☀ {m['lever_soleil']}→{m['coucher_soleil']} · "
        f"{m['conseil']}"
    )


def save_meteo_observation(db: Session) -> dict | None:
    """
    Récupère la météo du jour et l'enregistre en base comme observation.
    Évite les doublons : si une observation météo existe déjà pour aujourd'hui,
    ne crée pas de doublon.

    Retourne le dict météo si succès, None sinon.
    """
    from database.models import Evenement
    from utils.date_utils import parse_date

    # ── Anti-doublon : vérifier si observation météo déjà présente aujourd'hui
    today_start = datetime.combine(date.today(), datetime.min.time())
    today_end   = datetime.combine(date.today(), datetime.max.time())

    existing = (
        db.query(Evenement)
        .filter(
            Evenement.type_action   == "observation",
            Evenement.texte_original == "[AUTO-METEO]",
            Evenement.date.between(today_start, today_end),
        )
        .first()
    )
    if existing:
        log.info(f"⏭️  MÉTÉO DOUBLON   : observation déjà présente pour aujourd'hui (id={existing.id})")
        return None

    # ── Appel API
    meteo = fetch_meteo()
    if not meteo:
        return None

    commentaire = format_meteo_commentaire(meteo)

    # ── Enregistrement en base
    event = Evenement(
        type_action    = "observation",
        culture        = None,
        variete        = None,
        quantite       = None,
        unite          = None,
        parcelle       = None,
        rang           = None,
        duree          = None,
        traitement     = None,
        commentaire    = commentaire,
        texte_original = "[AUTO-METEO]",
        date           = parse_date(meteo["date"]),
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    log.info(f"🌤️  MÉTÉO SAUVÉE    : id={event.id} | {commentaire[:80]}...")
    return meteo
