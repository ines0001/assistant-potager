"""
utils/stock.py — Calcul du stock réel des cultures
---------------------------------------------------
[US-002] Adapte le calcul selon le type d'organe récolté :

- "végétatif"    : récolte DESTRUCTIVE
                   stock_plants = plantations - pertes - récoltes
                   Ex : salade, carotte, radis — 1 récolte = 1 plant en moins

- "reproducteur" : récolte CONTINUE
                   stock_plants = plantations - pertes  (récoltes n'affectent PAS le stock)
                   rendement_kg = SUM(récoltes en kg/g)
                   Ex : tomate, courgette — la plante reste vivante

Cette logique est centralisée ici pour être partagée entre bot.py et main.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

from database.models import Evenement, CultureConfig


@dataclass
class StockCulture:
    """[US-002] Données de stock agronomique pour une culture donnée."""
    culture:             str
    unite:               str
    type_organe:         Optional[str]   # "végétatif" | "reproducteur" | None

    # Plantations
    plants_plantes:      float = 0.0

    # Pertes (tous types)
    plants_perdus:       float = 0.0

    # Récoltes
    nb_recoltes:         int   = 0
    recoltes_total:      float = 0.0    # somme quantités récoltées
    unite_recolte:       str   = ""

    @property
    def stock_plants(self) -> float:
        """
        [US-002 / CA1 & CA2]
        - végétatif    : stock = plantations - pertes - récoltes
        - reproducteur : stock = plantations - pertes  (récoltes indépendantes)
        - inconnu      : même logique que végétatif (conservateur)
        """
        if self.type_organe == "reproducteur":
            return max(0.0, self.plants_plantes - self.plants_perdus)
        # végétatif ou inconnu
        return max(0.0, self.plants_plantes - self.plants_perdus - self.recoltes_total)

    @property
    def is_reproducteur(self) -> bool:
        return self.type_organe == "reproducteur"


def get_type_organe(db: Session, culture: str) -> Optional[str]:
    """Retourne le type d'organe pour une culture depuis culture_config."""
    cfg = db.query(CultureConfig).filter(CultureConfig.nom == culture).first()
    return cfg.type_organe_recolte if cfg else None


def calcul_stock_cultures(db: Session) -> Dict[str, StockCulture]:
    """
    [US-002] Calcule le stock réel de toutes les cultures plantées.

    Retourne un dict { culture: StockCulture } trié par culture.

    Algorithme :
    1. Agréger plantations par (culture, unite) avec rang
    2. Agréger pertes par culture
    3. Agréger récoltes par (culture, unite)
    4. Récupérer le type_organe depuis culture_config
    5. Appliquer la règle végétatif / reproducteur
    """
    # ── 1. Plantations : total = quantite × rang ────────────────────────────
    plantations_raw = (
        db.query(
            Evenement.culture,
            Evenement.unite,
            Evenement.quantite,
            Evenement.rang
        )
        .filter(Evenement.type_action == "plantation")
        .filter(Evenement.culture.isnot(None))
        .all()
    )

    plantes: Dict[str, tuple] = {}   # culture → (total_plants, unite)
    for culture, unite, qte, rang in plantations_raw:
        total = (qte or 0) * (rang or 1)
        key = culture
        cur_total, cur_unite = plantes.get(key, (0.0, unite or "plants"))
        plantes[key] = (cur_total + total, unite or cur_unite)

    if not plantes:
        return {}

    # ── 2. Pertes par culture ───────────────────────────────────────────────
    pertes_raw = (
        db.query(Evenement.culture, func.sum(Evenement.quantite))
        .filter(Evenement.type_action == "perte")
        .filter(Evenement.culture.isnot(None))
        .group_by(Evenement.culture)
        .all()
    )
    pertes: Dict[str, float] = {c: (q or 0) for c, q in pertes_raw}

    # ── 3. Récoltes par (culture, unite) ───────────────────────────────────
    recoltes_raw = (
        db.query(
            Evenement.culture,
            Evenement.unite,
            func.count(Evenement.id),
            func.sum(Evenement.quantite)
        )
        .filter(Evenement.type_action == "recolte")
        .filter(Evenement.culture.isnot(None))
        .group_by(Evenement.culture, Evenement.unite)
        .all()
    )
    recoltes: Dict[str, tuple] = {}  # culture → (nb, total, unite)
    for culture, unite, nb, total in recoltes_raw:
        existing = recoltes.get(culture)
        if existing:
            recoltes[culture] = (existing[0] + nb, existing[1] + (total or 0), unite or existing[2])
        else:
            recoltes[culture] = (nb, total or 0, unite or "")

    # ── 4. Construction des objets StockCulture ─────────────────────────────
    result: Dict[str, StockCulture] = {}
    for culture, (total_plants, unite) in sorted(plantes.items()):
        type_organe = get_type_organe(db, culture)
        rec = recoltes.get(culture, (0, 0.0, ""))

        stock = StockCulture(
            culture         = culture,
            unite           = unite or "plants",
            type_organe     = type_organe,
            plants_plantes  = total_plants,
            plants_perdus   = pertes.get(culture, 0.0),
            nb_recoltes     = rec[0],
            recoltes_total  = rec[1],
            unite_recolte   = rec[2],
        )
        result[culture] = stock

    return result


def format_stock_ligne_telegram(s: StockCulture) -> str:
    """
    [US-002 / CA3] Formate une ligne de stock pour /stats Telegram.

    Exemples attendus :
    - végétatif  : "salade : *19 plants* (planté 25, perdu 4, récolté 2)"
    - reproducteur: "tomate : *5 plants actifs* · 8.5 kg récoltés (3 fois)"
    - inconnu    : "carotte : *50 plants* (planté 50)"
    """
    stock = int(s.stock_plants)
    unite = s.unite

    if s.is_reproducteur:
        # Stock = plantes vivantes ; récoltes = rendement cumulé
        base = f"• {s.culture} : *{stock} {unite} actifs*"
        details = [f"planté {int(s.plants_plantes)}"]
        if s.plants_perdus > 0:
            details.append(f"perdu {int(s.plants_perdus)}")

        if s.recoltes_total > 0:
            r_val  = round(s.recoltes_total, 2)
            r_u    = s.unite_recolte or "unités"
            r_nb   = s.nb_recoltes
            base  += f" · *{r_val} {r_u}* récoltés ({r_nb} fois)"

        return base + f" ({', '.join(details)})"

    else:
        # Végétatif : récolte réduit le stock
        base = f"• {s.culture} : *{stock} {unite}*"
        details = [f"planté {int(s.plants_plantes)}"]
        if s.plants_perdus > 0:
            details.append(f"perdu {int(s.plants_perdus)}")
        if s.recoltes_total > 0:
            details.append(f"récolté {int(s.recoltes_total)}")
        return base + f" ({', '.join(details)})"


def calcul_semis(db: Session) -> Dict[str, dict]:
    """
    Agrège les semis par culture et croise avec les récoltes déjà réalisées.
    Retourne un dict { culture: { nb_semis, total_seme, unite, type_organe,
                                  nb_recoltes, total_recolte, unite_recolte } }
    """
    # Grouper uniquement par culture (pas par unite) pour compter tous les semis
    # même si l'unité varie ou est absente selon les enregistrements
    semis_raw = (
        db.query(
            Evenement.culture,
            func.count(Evenement.id),
            func.sum(Evenement.quantite),
        )
        .filter(Evenement.type_action == "semis")
        .filter(Evenement.culture.isnot(None))
        .group_by(Evenement.culture)
        .all()
    )
    if not semis_raw:
        return {}

    # Récupérer la première unité non-nulle par culture
    unites_raw = (
        db.query(Evenement.culture, Evenement.unite)
        .filter(Evenement.type_action == "semis")
        .filter(Evenement.culture.isnot(None))
        .filter(Evenement.unite.isnot(None))
        .distinct(Evenement.culture)
        .all()
    )
    unites: Dict[str, str] = {c: u for c, u in unites_raw}

    recoltes_raw = (
        db.query(
            Evenement.culture,
            Evenement.unite,
            func.count(Evenement.id),
            func.sum(Evenement.quantite)
        )
        .filter(Evenement.type_action == "recolte")
        .filter(Evenement.culture.isnot(None))
        .group_by(Evenement.culture, Evenement.unite)
        .all()
    )

    # Normalisation des unités en grammes pour pouvoir additionner correctement
    # quand une même culture a des récoltes avec des unités différentes (kg, g, etc.)
    _UNITE_TO_G = {"kg": 1000.0, "g": 1.0, "mg": 0.001}

    def _to_g(val: float, unite: str) -> float:
        return val * _UNITE_TO_G.get((unite or "").lower(), 1.0)

    def _best_unite(total_g: float) -> tuple:
        """Retourne (valeur, unite) la plus lisible."""
        if total_g >= 1000:
            return round(total_g / 1000, 2), "kg"
        return round(total_g, 1), "g"

    recoltes_g: Dict[str, tuple] = {}   # culture → (nb, total_en_grammes, unite_originale)
    for culture, unite, nb, total in recoltes_raw:
        val_g = _to_g(total or 0.0, unite)
        if culture in recoltes_g:
            prev_nb, prev_g, _ = recoltes_g[culture]
            recoltes_g[culture] = (prev_nb + nb, prev_g + val_g, unite or "")
        else:
            recoltes_g[culture] = (nb, val_g, unite or "")

    recoltes: Dict[str, tuple] = {}
    for culture, (nb, total_g, _) in recoltes_g.items():
        val, unite_out = _best_unite(total_g)
        recoltes[culture] = (nb, val, unite_out)

    result: Dict[str, dict] = {}
    for culture, nb, total in semis_raw:
        rec = recoltes.get(culture, (0, 0.0, ""))
        result[culture] = {
            "nb_semis":      nb,
            "total_seme":    total,        # None si toutes les quantites sont absentes
            "unite":         unites.get(culture, "graines"),
            "type_organe":   get_type_organe(db, culture),
            "nb_recoltes":   rec[0],
            "total_recolte": rec[1],
            "unite_recolte": rec[2],
        }
    return dict(sorted(result.items()))


def format_stock_stats_json(stocks: Dict[str, StockCulture]) -> dict:
    """
    [US-002 / CA4] Retourne les données de stock sous forme JSON pour l'API /stats.

    Champs distincts selon le type :
    - stock_plants         : plants actuellement en vie
    - rendement_total      : total récolté (reproducteur uniquement)
    - unite_rendement      : unité du rendement
    """
    result = []
    for culture, s in stocks.items():
        entry = {
            "culture"            : culture,
            "type_organe"        : s.type_organe or "inconnu",
            "plants_plantes"     : int(s.plants_plantes),
            "plants_perdus"      : int(s.plants_perdus),
            "stock_plants"       : int(s.stock_plants),
            "unite"              : s.unite,
        }
        if s.is_reproducteur:
            entry["rendement_total"] = round(s.recoltes_total, 3)
            entry["unite_rendement"] = s.unite_recolte or ""
            entry["nb_recoltes"]     = s.nb_recoltes
        result.append(entry)
    return result


# ══════════════════════════════════════════════════════════════════════════════
# [US_Stats_detail_par_variete] Détail par variété
# ══════════════════════════════════════════════════════════════════════════════

def calcul_stock_par_variete(db: Session, culture: str) -> List[dict]:
    """
    [US_Stats_detail_par_variete / CA3, CA4, CA5, CA6, CA7]
    Agrège les événements par variété pour une culture donnée.

    Filtre insensible à la casse via func.lower().
    Retourne [] si aucune plantation trouvée pour cette culture.

    Champs de chaque dict :
      variete, plants_plantes, plants_perdus, nb_recoltes, recoltes_total,
      unite_recolte, unite_plant, type_organe,
      date_premiere_plantation, date_derniere_recolte
    """
    culture_lower = culture.lower()

    # ── 1. Plantations brutes (pour recalculer qte × rang en Python) ────────
    plantations_raw = (
        db.query(
            Evenement.variete,
            Evenement.unite,
            Evenement.quantite,
            Evenement.rang,
            Evenement.date,
        )
        .filter(func.lower(Evenement.culture) == culture_lower)
        .filter(Evenement.type_action == "plantation")
        .all()
    )

    # [CA6] Culture inconnue → liste vide
    if not plantations_raw:
        return []

    # ── 2. Pertes par variété ────────────────────────────────────────────────
    pertes_raw = (
        db.query(Evenement.variete, func.sum(Evenement.quantite))
        .filter(func.lower(Evenement.culture) == culture_lower)
        .filter(Evenement.type_action == "perte")
        .group_by(Evenement.variete)
        .all()
    )
    pertes: Dict[Optional[str], float] = {v: (q or 0) for v, q in pertes_raw}

    # ── 3. Récoltes brutes par variété (agrégation Python pour gérer multi-unités) ──
    recoltes_raw = (
        db.query(
            Evenement.variete,
            Evenement.unite,
            Evenement.quantite,
            Evenement.date,
        )
        .filter(func.lower(Evenement.culture) == culture_lower)
        .filter(Evenement.type_action == "recolte")
        .all()
    )

    # ── 4. type_organe depuis culture_config ────────────────────────────────
    cfg = (
        db.query(CultureConfig)
        .filter(func.lower(CultureConfig.nom) == culture_lower)
        .first()
    )
    type_organe: Optional[str] = cfg.type_organe_recolte if cfg else None

    # ── 5. Agrégation plantations par variété ───────────────────────────────
    plantes: Dict[Optional[str], dict] = {}
    for variete, unite, qte, rang, date_ev in plantations_raw:
        total = (qte or 0) * (rang or 1)
        if variete in plantes:
            plantes[variete]["total"] += total
            if date_ev and (
                plantes[variete]["date_min"] is None
                or date_ev < plantes[variete]["date_min"]
            ):
                plantes[variete]["date_min"] = date_ev
        else:
            plantes[variete] = {
                "total":    total,
                "unite":    unite or "plants",
                "date_min": date_ev,
            }

    # ── 6. Agrégation récoltes par variété ───────────────────────────────────
    recoltes: Dict[Optional[str], dict] = {}
    for variete, unite, qte, date_ev in recoltes_raw:
        val = qte or 0
        if variete in recoltes:
            recoltes[variete]["nb"]    += 1
            recoltes[variete]["total"] += val
            if date_ev and (
                recoltes[variete]["date_max"] is None
                or date_ev > recoltes[variete]["date_max"]
            ):
                recoltes[variete]["date_max"] = date_ev
        else:
            recoltes[variete] = {
                "nb":       1,
                "total":    val,
                "unite":    unite or "",
                "date_max": date_ev,
            }

    # ── 7. Construction de la liste de résultats ─────────────────────────────
    # [CA5] None regroupé comme "Variété non précisée"
    result: List[dict] = []
    for vkey in sorted(plantes.keys(), key=lambda v: ("" if v is None else v)):
        p = plantes[vkey]
        r = recoltes.get(vkey, {"nb": 0, "total": 0.0, "unite": "", "date_max": None})
        result.append({
            "variete":                  vkey if vkey is not None else "Variété non précisée",
            "plants_plantes":           p["total"],
            "plants_perdus":            pertes.get(vkey, 0.0),
            "nb_recoltes":              r["nb"],
            "recoltes_total":           r["total"],
            "unite_recolte":            r["unite"],
            "unite_plant":              p["unite"],
            "type_organe":              type_organe,
            "date_premiere_plantation": p["date_min"],
            "date_derniere_recolte":    r["date_max"],
        })

    return result


_MOIS_FR = [
    "jan", "fév", "mar", "avr", "mai", "juin",
    "juil", "aoû", "sep", "oct", "nov", "déc",
]


def _fmt_date_variete(dt: Optional[datetime], current_year: int) -> str:
    """Formate une date en 'dd mmm' (même année) ou 'dd mmm YYYY'."""
    if dt is None:
        return "?"
    mois = _MOIS_FR[dt.month - 1]
    if dt.year == current_year:
        return f"{dt.day:02d} {mois}"
    return f"{dt.day:02d} {mois} {dt.year}"


def format_variete_bloc_telegram(v: dict) -> str:
    """
    [US_Stats_detail_par_variete / CA4]
    Formate un bloc variété pour /stats [culture] Telegram.

    Respecte la logique reproducteur (récolte continue) vs végétatif (récolte destructive).
    Format date : 'dd mmm' si même année, 'dd mmm YYYY' sinon.
    'en cours' si date_derniere_recolte est None.
    """
    nom            = v["variete"]
    plants_plantes = int(v["plants_plantes"])
    plants_perdus  = int(v["plants_perdus"])
    nb_recoltes    = v["nb_recoltes"]
    recoltes_total = v["recoltes_total"]
    unite_recolte  = v["unite_recolte"] or "unités"
    unite_plant    = v["unite_plant"] or "plants"
    type_organe    = v["type_organe"]
    date_plantation = v["date_premiere_plantation"]
    date_recolte    = v["date_derniere_recolte"]

    is_repr      = (type_organe == "reproducteur")
    current_year = datetime.now().year

    lines = [f"🔸 *{nom}*"]

    if is_repr:
        # [CA4] Reproducteur : plants actifs + rendement kg
        stock = max(0, plants_plantes - plants_perdus)
        base  = f"  • {stock} {unite_plant} actifs"
        if recoltes_total > 0:
            r_val  = round(recoltes_total, 2)
            base  += f" · {r_val} {unite_recolte} récoltés ({nb_recoltes} fois)"
        lines.append(base)
        details = [f"planté {plants_plantes}"]
        if plants_perdus > 0:
            details.append(f"perdu {plants_perdus}")
        lines.append(f"    ({', '.join(details)})")
    else:
        # [CA4] Végétatif : récolte est destructive (réduit le stock)
        stock = max(0, plants_plantes - plants_perdus - int(recoltes_total))
        base  = f"  • {stock} {unite_plant}"
        details = [f"planté {plants_plantes}"]
        if plants_perdus > 0:
            details.append(f"perdu {plants_perdus}")
        if recoltes_total > 0:
            details.append(f"récolté {int(recoltes_total)}")
        lines.append(base + f" ({', '.join(details)})")

    # [CA4] Période plantation → dernière récolte (ou "en cours")
    if date_plantation:
        date_debut = _fmt_date_variete(date_plantation, current_year)
        date_fin   = _fmt_date_variete(date_recolte, current_year) if date_recolte else "en cours"
        lines.append(f"  📅 {date_debut} → {date_fin}")

    return "\n".join(lines)
