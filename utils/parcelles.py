"""
utils/parcelles.py — Gestion des parcelles du potager
-------------------------------------------------------
[US_Plan_occupation_parcelles]

Fonctions :
- normalize_parcelle_name  : forme canonique (CA11)
- levenshtein_distance     : distance pure Python (CA12)
- find_doublon             : détection doublons exact / proche (CA10, CA12)
- create_parcelle          : création avec vérification doublon (CA13)
- get_all_parcelles        : liste triée par ordre (CA4)
- calcul_occupation_parcelles : structure d'occupation par parcelle (CA1-CA7)
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session
from unidecode import unidecode

from database.models import Evenement, Parcelle
from utils.stock import calcul_stock_cultures

log = logging.getLogger("potager")


# ──────────────────────────────────────────────────────────────────────────────
# [US_Plan_occupation_parcelles / CA11] Normalisation du nom de parcelle
# ──────────────────────────────────────────────────────────────────────────────

def normalize_parcelle_name(nom: str) -> str:
    """
    [CA11] Normalise un nom de parcelle : strip + lower + suppression accents
    + suppression tirets et espaces.

    Exemples :
      "Nord"    → "nord"
      "Côté Est" → "cotéest" → "coteest"
      "nord-est"→ "nordest"
    """
    s = nom.strip().lower()
    s = unidecode(s)               # suppression accents
    s = re.sub(r"[\s\-]+", "", s)  # suppression tirets et espaces
    return s


# ──────────────────────────────────────────────────────────────────────────────
# [US_Plan_occupation_parcelles / CA12] Distance de Levenshtein (pure Python)
# ──────────────────────────────────────────────────────────────────────────────

def levenshtein_distance(a: str, b: str) -> int:
    """
    [CA12] Calcule la distance de Levenshtein entre deux chaînes.
    Implémentation pure Python — pas de dépendance externe.
    """
    if a == b:
        return 0
    len_a, len_b = len(a), len(b)
    if len_a == 0:
        return len_b
    if len_b == 0:
        return len_a

    # Optimisation : n'utiliser que deux lignes
    prev = list(range(len_b + 1))
    curr = [0] * (len_b + 1)

    for i in range(1, len_a + 1):
        curr[0] = i
        for j in range(1, len_b + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr[j] = min(
                prev[j] + 1,        # suppression
                curr[j - 1] + 1,    # insertion
                prev[j - 1] + cost, # substitution
            )
        prev, curr = curr, [0] * (len_b + 1)

    return prev[len_b]


# ──────────────────────────────────────────────────────────────────────────────
# [US_Plan_occupation_parcelles / CA10, CA12] Détection doublons
# ──────────────────────────────────────────────────────────────────────────────

def find_doublon(
    db: Session, nom_normalise: str
) -> Tuple[Optional[Parcelle], Optional[Parcelle]]:
    """
    [CA10, CA12] Recherche un doublon exact ou une variante proche (Levenshtein ≤ 2).

    Retourne (exact_match, proche_match) :
    - exact_match  : Parcelle dont nom_normalise == nom_normalise fourni
    - proche_match : Parcelle dont la distance Levenshtein ≤ 2 (si pas d'exact)
    """
    # Doublon exact
    exact = (
        db.query(Parcelle)
        .filter(Parcelle.nom_normalise == nom_normalise)
        .first()
    )
    if exact:
        return exact, None

    # Variante proche (Levenshtein ≤ 2)
    toutes = db.query(Parcelle).filter(Parcelle.actif.is_(True)).all()
    for p in toutes:
        if levenshtein_distance(nom_normalise, p.nom_normalise) <= 2:
            return None, p

    return None, None


# ──────────────────────────────────────────────────────────────────────────────
# [US_Plan_occupation_parcelles / CA13] Création d'une parcelle
# ──────────────────────────────────────────────────────────────────────────────

def resolve_parcelle(db: Session, nom: str) -> Optional[Parcelle]:
    """
    Résout un nom de parcelle libre (issu du LLM) vers l'objet Parcelle en base.

    Stratégie :
    1. Correspondance exacte sur nom_normalise → retourne immédiatement
    2. Correspondance proche (Levenshtein ≤ 2) → retourne la variante (log warning)
    3. Aucune correspondance → retourne None

    Args:
        db  : session SQLAlchemy
        nom : nom brut extrait par le LLM (ex : "Ouest", "NORD", "cote est")

    Returns:
        Parcelle correspondante ou None
    """
    if not nom or not nom.strip():
        return None
    nom_normalise = normalize_parcelle_name(nom)
    exact, proche = find_doublon(db, nom_normalise)
    if exact:
        return exact
    if proche:
        log.warning(
            f"[resolve_parcelle] Correspondance approchée : "
            f"{nom!r} → {proche.nom!r} (distance Levenshtein ≤ 2)"
        )
        return proche
    return None


def create_parcelle(
    db: Session,
    nom: str,
    exposition: Optional[str] = None,
    superficie_m2: Optional[float] = None,
) -> Parcelle:
    """
    [CA13] Crée une nouvelle parcelle avec nom_normalise calculé.
    ordre = nombre de parcelles existantes + 1.
    Lève ValueError si un doublon exact existe déjà.
    """
    nom_normalise = normalize_parcelle_name(nom)
    exact, _ = find_doublon(db, nom_normalise)
    if exact:
        raise ValueError(f"La parcelle « {exact.nom.upper()} » existe déjà.")

    nb_existantes = db.query(Parcelle).count()
    parcelle = Parcelle(
        nom=nom,
        nom_normalise=nom_normalise,
        exposition=exposition,
        superficie_m2=superficie_m2,
        ordre=nb_existantes + 1,
        actif=True,
    )
    db.add(parcelle)
    db.commit()
    db.refresh(parcelle)
    log.info(f"[US_Plan_occupation_parcelles] Parcelle créée : {nom!r} (ordre={parcelle.ordre})")
    return parcelle


# ──────────────────────────────────────────────────────────────────────────────
# [US_Plan_occupation_parcelles] Mise à jour des métadonnées d'une parcelle
# ──────────────────────────────────────────────────────────────────────────────

_CHAMPS_MODIFIER = {"exposition", "superficie", "ordre"}


def update_parcelle(
    db: Session, nom: str, **kwargs
) -> Tuple[Parcelle, List[str]]:
    """
    Met à jour les métadonnées d'une parcelle existante.

    Paramètres acceptés via kwargs : exposition, superficie (float m²), ordre (int).
    Lève ValueError  si un paramètre est inconnu ou mal typé.
    Lève LookupError si la parcelle est introuvable.

    Retourne (parcelle_mise_a_jour, liste_des_modifs_texte).
    """
    inconnus = set(kwargs) - _CHAMPS_MODIFIER
    if inconnus:
        raise ValueError(
            f"Paramètre(s) inconnu(s) : {', '.join(sorted(inconnus))}. "
            f"Acceptés : exposition, superficie, ordre"
        )

    nom_normalise = normalize_parcelle_name(nom)
    parcelle = (
        db.query(Parcelle)
        .filter(Parcelle.nom_normalise == nom_normalise)
        .first()
    )
    if parcelle is None:
        raise LookupError(nom)

    modifs: List[str] = []
    if "exposition" in kwargs:
        parcelle.exposition = kwargs["exposition"]
        modifs.append(f"Exposition : {kwargs['exposition']}")
    if "superficie" in kwargs:
        try:
            val = float(kwargs["superficie"])
        except (ValueError, TypeError):
            raise ValueError("superficie doit être un nombre décimal (ex : 8.5)")
        parcelle.superficie_m2 = val
        modifs.append(f"Superficie : {val} m²")
    if "ordre" in kwargs:
        try:
            val_ord = int(kwargs["ordre"])
        except (ValueError, TypeError):
            raise ValueError("ordre doit être un entier (ex : 1)")
        parcelle.ordre = val_ord
        modifs.append(f"Ordre : {val_ord}")

    db.commit()
    db.refresh(parcelle)
    log.info(
        f"[US_Plan_occupation_parcelles] Parcelle mise à jour : {parcelle.nom!r} — {modifs}"
    )
    return parcelle, modifs


# ──────────────────────────────────────────────────────────────────────────────
# [US_Plan_occupation_parcelles / CA4] Liste des parcelles
# ──────────────────────────────────────────────────────────────────────────────

def get_all_parcelles(db: Session) -> List[Parcelle]:
    """
    [CA4] Retourne toutes les parcelles actives triées par ordre croissant.
    """
    return (
        db.query(Parcelle)
        .filter(Parcelle.actif.is_(True))
        .order_by(Parcelle.ordre)
        .all()
    )


# ──────────────────────────────────────────────────────────────────────────────
# [US_Plan_occupation_parcelles / CA1-CA7] Structure d'occupation
# ──────────────────────────────────────────────────────────────────────────────

def calcul_occupation_parcelles(db: Session) -> Dict[Optional[str], list]:
    """
    [CA1-CA7] Calcule la structure d'occupation du potager par parcelle.

    Retourne un dict :
    {
        "NORD": [
            {
                "culture": "tomate",
                "variete": "Cœur de Bœuf",
                "nb_plants": 3.0,
                "unite": "plants",
                "type_organe": "reproducteur",
                "date_plantation": datetime,
                "age_jours": 27,
            },
            ...
        ],
        None: [...]   # [CA7] cultures sans parcelle renseignée
    }

    Seules les cultures avec stock > 0 sont incluses.
    Groupées par (culture, variete, parcelle) depuis les événements de plantation.
    """
    # ── 1. Cultures actives (stock > 0) ──────────────────────────────────────
    stocks = calcul_stock_cultures(db)
    cultures_actives = {c for c, s in stocks.items() if s.stock_plants > 0}

    if not cultures_actives:
        return {}

    # ── 2. Événements de plantation pour cultures actives ────────────────────
    rows = (
        db.query(
            Evenement.culture,
            Evenement.variete,
            Evenement.parcelle,
            Evenement.quantite,
            Evenement.rang,
            Evenement.unite,
            Evenement.date,
        )
        .filter(Evenement.type_action == "plantation")
        .filter(Evenement.culture.in_(list(cultures_actives)))
        .order_by(Evenement.date)
        .all()
    )

    # ── 3. Agrégation par (culture, variete, parcelle) ───────────────────────
    # Clé : (culture, variete_norm, parcelle)
    groupes: Dict[tuple, dict] = {}

    for culture, variete, parcelle, quantite, rang, unite, date_evt in rows:
        variete_norm = variete or ""
        key = (culture, variete_norm, parcelle)
        total = (quantite or 0) * (rang or 1)

        if key not in groupes:
            groupes[key] = {
                "culture": culture,
                "variete": variete_norm,
                "nb_plants": 0.0,
                "unite": unite or "plants",
                "date_premiere": date_evt,
            }

        groupes[key]["nb_plants"] += total

        # Garder la date la plus ancienne
        if date_evt and (
            groupes[key]["date_premiere"] is None
            or date_evt < groupes[key]["date_premiere"]
        ):
            groupes[key]["date_premiere"] = date_evt

    # ── 4. Construction du résultat final ─────────────────────────────────────
    today = datetime.now().date()
    result: Dict[Optional[str], list] = {}

    for (culture, variete, parcelle), data in groupes.items():
        stock = stocks.get(culture)
        # [CA1] Ne garder que les cultures avec stock actif
        if not stock or stock.stock_plants <= 0:
            continue

        date_plantation = data["date_premiere"]
        if date_plantation and hasattr(date_plantation, "date"):
            age_jours = (today - date_plantation.date()).days
        elif date_plantation:
            age_jours = (today - date_plantation).days
        else:
            age_jours = 0

        entree = {
            "culture": culture,
            "variete": variete,
            "nb_plants": data["nb_plants"],
            "unite": data["unite"],
            "type_organe": stock.type_organe,           # [CA3] pour seuil alerte
            "date_plantation": date_plantation,
            "age_jours": max(0, age_jours),
        }

        if parcelle not in result:
            result[parcelle] = []
        result[parcelle].append(entree)

    log.info(
        f"[US_Plan_occupation_parcelles] calcul_occupation_parcelles : "
        f"{sum(len(v) for v in result.values())} cultures actives, "
        f"{len(result)} parcelles"
    )
    return result
