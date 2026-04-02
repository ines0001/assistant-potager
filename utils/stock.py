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
from typing import Dict, Optional
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
