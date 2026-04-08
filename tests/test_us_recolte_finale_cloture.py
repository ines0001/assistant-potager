"""
tests/test_us_recolte_finale_cloture.py
-----------------------------------------
Tests US "Enregistrer récolte finale et clôture de culture"

CA1 : `recolte_finale` est reconnu dans ACTION_MAP et distingué de `recolte`
CA2 : stock_plants passe à 0 et cloturee=True après recolte_finale
CA3 : La quantité de la récolte finale est bien comptabilisée dans le bilan
CA4 : Une culture clôturée n'apparaît pas dans les stocks actifs
CA5 : Le rendement total = récoltes partielles + récolte finale ; durée calculée
"""
from __future__ import annotations

import pytest
from datetime import date, timedelta
from unittest.mock import MagicMock, patch, call
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from utils.actions import ACTION_MAP, normalize_action
from utils.stock import StockCulture, calcul_stock_cultures, format_stock_ligne_telegram
from database.models import Evenement, CultureConfig
from llm.groq_client import PARSE_PROMPT
from database.db import Base


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def engine():
    """Engine SQLite en mémoire pour les tests d'intégration."""
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=eng)
    return eng


@pytest.fixture
def db(engine):
    """Session de test isolée — rollback après chaque test."""
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()


# ──────────────────────────────────────────────────────────────────────────────
# CA1 — recolte_finale reconnu et distingué de recolte
# ──────────────────────────────────────────────────────────────────────────────

class TestCA1ActionMap:
    def test_recolte_finale_present_in_action_map(self) -> None:
        """CA1 — La clé 'recolte_finale' existe dans ACTION_MAP."""
        assert "recolte_finale" in ACTION_MAP

    def test_recolte_finale_precede_recolte_in_action_map(self) -> None:
        """CA1 — recolte_finale est déclaré avant recolte pour éviter faux match startswith."""
        keys = list(ACTION_MAP.keys())
        assert keys.index("recolte_finale") < keys.index("recolte")

    def test_synonyme_fin_de_culture_normalise(self) -> None:
        """CA1 — 'fin de culture' → 'recolte_finale'."""
        assert normalize_action("fin de culture") == "recolte_finale"

    def test_synonyme_derniere_recolte_normalise(self) -> None:
        """CA1 — 'derniere recolte' → 'recolte_finale'."""
        assert normalize_action("derniere recolte") == "recolte_finale"

    def test_synonyme_recolte_definitive_normalise(self) -> None:
        """CA1 — 'recolte definitive' → 'recolte_finale'."""
        assert normalize_action("recolte definitive") == "recolte_finale"

    def test_canonical_direct_normalise(self) -> None:
        """CA1 — La chaîne 'recolte_finale' est normalisée correctement."""
        assert normalize_action("recolte_finale") == "recolte_finale"

    def test_recolte_partielle_non_confondue(self) -> None:
        """CA1 — 'recolte' simple reste 'recolte', pas 'recolte_finale'."""
        assert normalize_action("recolte") == "recolte"

    def test_recolte_kg_non_confondue(self) -> None:
        """CA1 — 'recolter 2 kg tomates' → 'recolte', pas 'recolte_finale'."""
        assert normalize_action("recolter 2 kg tomates") == "recolte"


# ──────────────────────────────────────────────────────────────────────────────
# CA2 — stock_plants=0 et cloturee=True après recolte_finale
# ──────────────────────────────────────────────────────────────────────────────

class TestCA2StockCloture:
    def test_stock_plants_zero_quand_cloturee(self) -> None:
        """CA2 — stock_plants retourne 0.0 si cloturee=True."""
        s = StockCulture(
            culture="tomate cerise", unite="plants", type_organe="reproducteur",
            plants_plantes=6.0, plants_perdus=0.0, cloturee=True,
        )
        assert s.stock_plants == 0.0

    def test_stock_plants_non_zero_quand_non_cloturee(self) -> None:
        """CA2 — stock_plants > 0 si la culture est active."""
        s = StockCulture(
            culture="tomate cerise", unite="plants", type_organe="reproducteur",
            plants_plantes=6.0, plants_perdus=0.0, cloturee=False,
        )
        assert s.stock_plants == 6.0

    def test_stock_plants_zero_vegetatif_cloture(self) -> None:
        """CA2 — culture végétative clôturée : stock = 0 même si récoltes < plantations."""
        s = StockCulture(
            culture="salade", unite="plants", type_organe="végétatif",
            plants_plantes=10.0, plants_perdus=0.0, recoltes_total=3.0, cloturee=True,
        )
        assert s.stock_plants == 0.0

    def test_calcul_stock_cultures_marque_cloturee(self, db) -> None:
        """CA2 — calcul_stock_cultures marque cloturee=True si recolte_finale existe."""
        date_plantation = date(2025, 4, 1)
        date_finale = date(2025, 8, 15)

        db.add(Evenement(
            type_action="plantation", culture="tomate cerise",
            quantite=6.0, unite="plants", rang=1,
            date=date_plantation,
        ))
        db.add(Evenement(
            type_action="recolte_finale", culture="tomate cerise",
            quantite=1.2, unite="kg",
            date=date_finale,
        ))
        db.commit()

        stocks = calcul_stock_cultures(db)
        assert "tomate cerise" in stocks
        s = stocks["tomate cerise"]
        assert s.cloturee is True
        assert s.stock_plants == 0.0


# ──────────────────────────────────────────────────────────────────────────────
# CA3 — Quantité récolte finale comptabilisée
# ──────────────────────────────────────────────────────────────────────────────

class TestCA3QuantiteFinale:
    def test_recolte_finale_qte_stockee(self, db) -> None:
        """CA3 — recolte_finale_qte est bien la quantité de la récolte finale."""
        db.add(Evenement(
            type_action="plantation", culture="courgette",
            quantite=3.0, unite="plants", rang=1,
            date=date(2025, 5, 1),
        ))
        db.add(Evenement(
            type_action="recolte_finale", culture="courgette",
            quantite=2.5, unite="kg",
            date=date(2025, 9, 1),
        ))
        db.commit()

        stocks = calcul_stock_cultures(db)
        s = stocks["courgette"]
        assert s.recolte_finale_qte == 2.5

    def test_rendement_total_inclut_partielles_et_finale(self, db) -> None:
        """CA3 — rendement total = somme récoltes partielles + récolte finale."""
        db.add(Evenement(
            type_action="plantation", culture="courgette",
            quantite=3.0, unite="plants", rang=1,
            date=date(2025, 5, 1),
        ))
        db.add(Evenement(
            type_action="recolte", culture="courgette",
            quantite=1.0, unite="kg", date=date(2025, 7, 1),
        ))
        db.add(Evenement(
            type_action="recolte", culture="courgette",
            quantite=0.8, unite="kg", date=date(2025, 8, 1),
        ))
        db.add(Evenement(
            type_action="recolte_finale", culture="courgette",
            quantite=2.5, unite="kg", date=date(2025, 9, 1),
        ))
        db.commit()

        stocks = calcul_stock_cultures(db)
        s = stocks["courgette"]
        total = round(s.recoltes_total + s.recolte_finale_qte, 2)
        assert total == 4.3  # 1.0 + 0.8 + 2.5


# ──────────────────────────────────────────────────────────────────────────────
# CA4 — Culture clôturée absente des stocks actifs
# ──────────────────────────────────────────────────────────────────────────────

class TestCA4CulturesActives:
    def test_culture_cloturee_exclue_des_actives(self, db) -> None:
        """CA4 — Une culture clôturée est marquée cloturee=True dans le dict retourné."""
        db.add(Evenement(
            type_action="plantation", culture="radis",
            quantite=20.0, unite="plants", rang=1,
            date=date(2025, 3, 1),
        ))
        db.add(Evenement(
            type_action="recolte_finale", culture="radis",
            quantite=20.0, unite="plants", date=date(2025, 4, 1),
        ))
        db.commit()

        stocks = calcul_stock_cultures(db)
        closed = {c: s for c, s in stocks.items() if s.cloturee}
        active = {c: s for c, s in stocks.items() if not s.cloturee}

        assert "radis" in closed
        assert "radis" not in active

    def test_culture_active_non_marquee_cloturee(self, db) -> None:
        """CA4 — Une culture sans recolte_finale reste active (cloturee=False)."""
        db.add(Evenement(
            type_action="plantation", culture="carotte",
            quantite=10.0, unite="plants", rang=1,
            date=date(2025, 4, 1),
        ))
        db.commit()

        stocks = calcul_stock_cultures(db)
        assert stocks["carotte"].cloturee is False


# ──────────────────────────────────────────────────────────────────────────────
# CA5 — Rendement total et durée de culture dans /stats
# ──────────────────────────────────────────────────────────────────────────────

class TestCA5BilanSaison:
    def test_duree_culture_calculee(self, db) -> None:
        """CA5 — La durée = date_cloture - date_plantation en jours."""
        d_plant = date(2025, 4, 1)
        d_cloture = date(2025, 8, 15)
        expected_duree = (d_cloture - d_plant).days  # 136 jours

        db.add(Evenement(
            type_action="plantation", culture="haricot",
            quantite=5.0, unite="plants", rang=1,
            date=d_plant,
        ))
        db.add(Evenement(
            type_action="recolte_finale", culture="haricot",
            quantite=0.5, unite="kg", date=d_cloture,
        ))
        db.commit()

        stocks = calcul_stock_cultures(db)
        s = stocks["haricot"]
        assert s.date_plantation == d_plant.isoformat()
        assert s.date_cloture == d_cloture.isoformat()

        # Vérification dans le formateur
        ligne = format_stock_ligne_telegram(s)
        assert f"durée *{expected_duree} j*" in ligne

    def test_format_cloturee_contient_rendement_total(self, db) -> None:
        """CA5 — format_stock_ligne_telegram affiche le rendement total (partielles + finale)."""
        db.add(Evenement(
            type_action="plantation", culture="poivron",
            quantite=4.0, unite="plants", rang=1,
            date=date(2025, 5, 1),
        ))
        db.add(Evenement(
            type_action="recolte", culture="poivron",
            quantite=0.3, unite="kg", date=date(2025, 7, 1),
        ))
        db.add(Evenement(
            type_action="recolte_finale", culture="poivron",
            quantite=0.7, unite="kg", date=date(2025, 9, 10),
        ))
        db.commit()

        stocks = calcul_stock_cultures(db)
        s = stocks["poivron"]
        ligne = format_stock_ligne_telegram(s)

        assert "_(clôturée)_" in ligne
        assert "1.0 kg" in ligne       # 0.3 + 0.7

    def test_format_cloturee_nb_recoltes_correct(self, db) -> None:
        """CA5 — Le nombre de récoltes affiché inclut la récolte finale."""
        db.add(Evenement(
            type_action="plantation", culture="aubergine",
            quantite=2.0, unite="plants", rang=1,
            date=date(2025, 5, 1),
        ))
        db.add(Evenement(
            type_action="recolte", culture="aubergine",
            quantite=0.4, unite="kg", date=date(2025, 7, 10),
        ))
        db.add(Evenement(
            type_action="recolte_finale", culture="aubergine",
            quantite=0.6, unite="kg", date=date(2025, 9, 5),
        ))
        db.commit()

        stocks = calcul_stock_cultures(db)
        s = stocks["aubergine"]
        ligne = format_stock_ligne_telegram(s)

        assert "2 récoltes" in ligne  # 1 partielle + 1 finale


# ──────────────────────────────────────────────────────────────────────────────
# PARSE_PROMPT — recolte_finale dans le prompt LLM
# ──────────────────────────────────────────────────────────────────────────────

class TestParsePrompt:
    def test_parse_prompt_contient_recolte_finale(self) -> None:
        """CA1 — PARSE_PROMPT liste 'recolte_finale' comme valeur d'action valide."""
        assert "recolte_finale" in PARSE_PROMPT

    def test_parse_prompt_contient_exemple_recolte_finale(self) -> None:
        """CA1 — PARSE_PROMPT contient un exemple de récolte finale."""
        assert "Récolte finale" in PARSE_PROMPT or "recolte_finale" in PARSE_PROMPT
