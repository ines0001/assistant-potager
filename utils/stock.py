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
from datetime import date as _date
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
    recoltes_total:      float = 0.0    # somme quantités récoltées (partielles)
    unite_recolte:       str   = ""

    # [US-recolte_finale] Clôture de culture
    cloturee:            bool         = False  # True si recolte_finale enregistrée
    date_plantation:     Optional[str] = None  # date plantation la plus ancienne (ISO)
    date_cloture:        Optional[str] = None  # date recolte_finale pour durée CA5
    recolte_finale_qte:  float        = 0.0    # quantité récoltée lors de la clôture

    @property
    def stock_plants(self) -> float:
        """
        [US-002 / CA1 & CA2]
        - clôturée     : stock = 0 (culture terminée)
        - végétatif    : stock = plantations - pertes - récoltes
        - reproducteur : stock = plantations - pertes  (récoltes indépendantes)
        - inconnu      : même logique que végétatif (conservateur)
        """
        if self.cloturee:
            return 0.0
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

    # ── 1b. Date de plantation la plus ancienne par culture ─────────────────
    dates_plantation_raw = (
        db.query(Evenement.culture, func.min(Evenement.date))
        .filter(Evenement.type_action == "plantation")
        .filter(Evenement.culture.isnot(None))
        .group_by(Evenement.culture)
        .all()
    )
    dates_plantation: Dict[str, Optional[str]] = {
        c: (str(d)[:10] if d else None) for c, d in dates_plantation_raw
    }

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

    # ── 3b. Récoltes finales par culture (clôture) ──────────────────────────
    recoltes_finales_raw = (
        db.query(
            Evenement.culture,
            Evenement.unite,
            func.sum(Evenement.quantite),
            func.max(Evenement.date)
        )
        .filter(Evenement.type_action == "recolte_finale")
        .filter(Evenement.culture.isnot(None))
        .group_by(Evenement.culture, Evenement.unite)
        .all()
    )
    recoltes_finales: Dict[str, tuple] = {}  # culture → (qte, unite, date_cloture)
    for culture, unite, total, date_rec in recoltes_finales_raw:
        existing = recoltes_finales.get(culture)
        if existing:
            date_max = max(existing[2], date_rec) if existing[2] and date_rec else (existing[2] or date_rec)
            recoltes_finales[culture] = (existing[0] + (total or 0), unite or existing[1], date_max)
        else:
            recoltes_finales[culture] = (total or 0, unite or "", date_rec)

    # ── 4. Construction des objets StockCulture ─────────────────────────────
    result: Dict[str, StockCulture] = {}
    for culture, (total_plants, unite) in sorted(plantes.items()):
        type_organe = get_type_organe(db, culture)
        rec = recoltes.get(culture, (0, 0.0, ""))
        rec_finale = recoltes_finales.get(culture)

        stock = StockCulture(
            culture            = culture,
            unite              = unite or "plants",
            type_organe        = type_organe,
            plants_plantes     = total_plants,
            plants_perdus      = pertes.get(culture, 0.0),
            nb_recoltes        = rec[0],
            recoltes_total     = rec[1],
            unite_recolte      = rec_finale[1] if rec_finale and rec_finale[1] else rec[2],
            # [US-recolte_finale] champs clôture
            cloturee           = rec_finale is not None,
            date_plantation    = dates_plantation.get(culture),
            date_cloture       = (str(rec_finale[2])[:10] if rec_finale and rec_finale[2] else None),
            recolte_finale_qte = rec_finale[0] if rec_finale else 0.0,
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

    # [US-recolte_finale / CA4&CA5] Culture clôturée : bilan de saison
    if s.cloturee:
        nb_total  = s.nb_recoltes + (1 if s.recolte_finale_qte > 0 else 0)
        total_rec = round(s.recoltes_total + s.recolte_finale_qte, 2)
        u         = s.unite_recolte or "unités"
        base      = f"• {s.culture} : _(clôturée)_ · rendement *{total_rec} {u}* ({nb_total} récoltes)"
        if s.date_plantation and s.date_cloture:
            d1    = _date.fromisoformat(s.date_plantation[:10])
            d2    = _date.fromisoformat(s.date_cloture[:10])
            duree = (d2 - d1).days
            base += f", durée *{duree} j*"
        return base

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
