"""
tests/test_us001_003.py — Tests US-001, US-002, US-003
-------------------------------------------------------
Couverture :
  - US-001 : modèle CultureConfig, héritage type_organe_recolte
  - US-002 : calcul stock différencié végétatif / reproducteur
  - US-003 : format affichage Telegram
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.db import Base
from database.models import Evenement, CultureConfig
from utils.stock import (
    calcul_stock_cultures,
    format_stock_ligne_telegram,
    format_stock_stats_json,
    StockCulture,
    get_type_organe,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def engine():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=eng)
    return eng


@pytest.fixture
def db(engine):
    """Session de test avec remise à zéro entre tests."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.rollback()
    session.close()


def _seed_cultures(db):
    """Pré-popule culture_config avec les deux types."""
    db.add(CultureConfig(nom="tomate",  type_organe_recolte="reproducteur",  description_agronomique="Fruit"))
    db.add(CultureConfig(nom="courgette", type_organe_recolte="reproducteur", description_agronomique="Fruit"))
    db.add(CultureConfig(nom="salade",  type_organe_recolte="végétatif",     description_agronomique="Feuille"))
    db.add(CultureConfig(nom="carotte", type_organe_recolte="végétatif",     description_agronomique="Racine"))
    db.commit()


# ══════════════════════════════════════════════════════════════════════════════
# US-001 — Modèle CultureConfig
# ══════════════════════════════════════════════════════════════════════════════

class TestUS001CultureConfig:

    def test_us001_ca2_culture_config_existe(self, db):
        """[US-001/CA2] La table culture_config existe et accepte les deux types."""
        db.add(CultureConfig(nom="tomate", type_organe_recolte="reproducteur"))
        db.add(CultureConfig(nom="salade", type_organe_recolte="végétatif"))
        db.commit()
        assert db.query(CultureConfig).count() == 2

    def test_us001_ca2_unique_nom(self, db):
        """[US-001/CA2] Le nom de culture est unique dans culture_config."""
        from sqlalchemy.exc import IntegrityError
        db.add(CultureConfig(nom="tomate", type_organe_recolte="reproducteur"))
        db.commit()
        db.add(CultureConfig(nom="tomate", type_organe_recolte="végétatif"))
        with pytest.raises(IntegrityError):
            db.commit()

    def test_us001_ca1_type_organe_recolte_sur_evenement(self, db):
        """[US-001/CA1] La colonne type_organe_recolte existe sur Evenement."""
        e = Evenement(type_action="plantation", culture="tomate", type_organe_recolte="reproducteur")
        db.add(e)
        db.commit()
        db.refresh(e)
        assert e.type_organe_recolte == "reproducteur"

    def test_us001_get_type_organe_connu(self, db):
        """[US-001] get_type_organe retourne le bon type pour une culture connue."""
        _seed_cultures(db)
        assert get_type_organe(db, "tomate")  == "reproducteur"
        assert get_type_organe(db, "salade")  == "végétatif"

    def test_us001_get_type_organe_inconnu(self, db):
        """[US-001] get_type_organe retourne None pour une culture inconnue."""
        assert get_type_organe(db, "plante_inconnue") is None


# ══════════════════════════════════════════════════════════════════════════════
# US-002 — Calcul stock différencié
# ══════════════════════════════════════════════════════════════════════════════

class TestUS002StockCalcul:

    def test_us002_ca1_vegetatif_recolte_reduit_stock(self, db):
        """[US-002/CA1] Pour végétatif : récolte réduit le stock de plants."""
        _seed_cultures(db)
        db.add(Evenement(type_action="plantation", culture="salade", quantite=10, rang=1, unite="plants", date=date(2026,3,1)))
        db.add(Evenement(type_action="recolte",    culture="salade", quantite=3,  unite="plants", date=date(2026,3,10)))
        db.commit()

        stocks = calcul_stock_cultures(db)
        assert "salade" in stocks
        s = stocks["salade"]
        assert s.type_organe == "végétatif"
        # [US-002/CA1] 10 plantés - 3 récoltés = 7
        assert s.stock_plants == 7

    def test_us002_ca2_reproducteur_recolte_naffecte_pas_stock(self, db):
        """[US-002/CA2] Pour reproducteur : récolte n'affecte PAS le stock de plants."""
        _seed_cultures(db)
        db.add(Evenement(type_action="plantation", culture="tomate", quantite=5, rang=1, unite="plants", date=date(2026,3,1)))
        db.add(Evenement(type_action="recolte",    culture="tomate", quantite=8, unite="kg", date=date(2026,3,15)))
        db.add(Evenement(type_action="recolte",    culture="tomate", quantite=6, unite="kg", date=date(2026,3,22)))
        db.commit()

        stocks = calcul_stock_cultures(db)
        s = stocks["tomate"]
        assert s.type_organe == "reproducteur"
        # [US-002/CA2] 5 plantés, récoltes ne comptent pas → stock = 5
        assert s.stock_plants == 5
        # Rendement cumulé = 14 kg
        assert s.recoltes_total == 14.0

    def test_us002_ca2_reproducteur_avec_pertes(self, db):
        """[US-002/CA2] Reproducteur : les pertes réduisent bien le stock."""
        _seed_cultures(db)
        db.add(Evenement(type_action="plantation", culture="tomate", quantite=5, rang=1, unite="plants", date=date(2026,3,1)))
        db.add(Evenement(type_action="perte",      culture="tomate", quantite=2, unite="plants", date=date(2026,3,5)))
        db.add(Evenement(type_action="recolte",    culture="tomate", quantite=3, unite="kg", date=date(2026,3,20)))
        db.commit()

        stocks = calcul_stock_cultures(db)
        s = stocks["tomate"]
        # stock = 5 - 2 = 3 (récolte n'affecte pas)
        assert s.stock_plants == 3
        assert s.recoltes_total == 3.0

    def test_us002_ca1_vegetatif_avec_pertes_et_recoltes(self, db):
        """[US-002/CA1] Végétatif : stock = plantations - pertes - récoltes."""
        _seed_cultures(db)
        # 25 plantés, 4 perdus, 2 récoltés → stock = 19
        db.add(Evenement(type_action="plantation", culture="salade", quantite=25, rang=1, unite="plants", date=date(2026,3,1)))
        db.add(Evenement(type_action="perte",      culture="salade", quantite=4,  unite="plants", date=date(2026,3,10)))
        db.add(Evenement(type_action="recolte",    culture="salade", quantite=2,  unite="plants", date=date(2026,3,20)))
        db.commit()

        stocks = calcul_stock_cultures(db)
        s = stocks["salade"]
        assert s.stock_plants == 19

    def test_us002_stock_jamais_negatif(self, db):
        """[US-002] Le stock ne peut pas être négatif (min 0)."""
        _seed_cultures(db)
        db.add(Evenement(type_action="plantation", culture="salade", quantite=5, rang=1, unite="plants", date=date(2026,3,1)))
        db.add(Evenement(type_action="recolte",    culture="salade", quantite=10, unite="plants", date=date(2026,3,10)))
        db.commit()

        stocks = calcul_stock_cultures(db)
        assert stocks["salade"].stock_plants == 0

    def test_us002_calcul_avec_rang(self, db):
        """[US-002] Plantation avec rang : total = quantite × rang."""
        _seed_cultures(db)
        # 10 plants/rang × 3 rangs = 30 plants au total
        db.add(Evenement(type_action="plantation", culture="tomate", quantite=10, rang=3, unite="plants", date=date(2026,3,1)))
        db.commit()

        stocks = calcul_stock_cultures(db)
        assert stocks["tomate"].plants_plantes == 30.0

    def test_us002_ca4_json_champs_distincts_reproducteur(self, db):
        """[US-002/CA4] L'API retourne rendement_total pour les reproductrices."""
        _seed_cultures(db)
        db.add(Evenement(type_action="plantation", culture="tomate", quantite=5, rang=1, unite="plants", date=date(2026,3,1)))
        db.add(Evenement(type_action="recolte",    culture="tomate", quantite=8, unite="kg", date=date(2026,3,15)))
        db.commit()

        stocks = calcul_stock_cultures(db)
        json_out = format_stock_stats_json(stocks)
        tomate_json = next(e for e in json_out if e["culture"] == "tomate")

        assert "rendement_total"  in tomate_json
        assert "nb_recoltes"      in tomate_json
        assert tomate_json["rendement_total"] == 8.0

    def test_us002_ca4_json_champs_distincts_vegetatif(self, db):
        """[US-002/CA4] L'API ne retourne PAS rendement_total pour les végétatives."""
        _seed_cultures(db)
        db.add(Evenement(type_action="plantation", culture="salade", quantite=10, rang=1, unite="plants", date=date(2026,3,1)))
        db.commit()

        stocks = calcul_stock_cultures(db)
        json_out = format_stock_stats_json(stocks)
        salade_json = next(e for e in json_out if e["culture"] == "salade")

        assert "rendement_total" not in salade_json

    def test_us002_culture_inconnue_calcul_conservateur(self, db):
        """[US-002] Culture sans type_organe : traitement identique au végétatif."""
        # Pas de seed culture_config
        db.add(Evenement(type_action="plantation", culture="inconnue", quantite=10, rang=1, unite="plants", date=date(2026,3,1)))
        db.add(Evenement(type_action="recolte",    culture="inconnue", quantite=3,  unite="plants", date=date(2026,3,10)))
        db.commit()

        stocks = calcul_stock_cultures(db)
        s = stocks["inconnue"]
        assert s.type_organe is None
        # Comportement conservateur : récolte réduit le stock (comme végétatif)
        assert s.stock_plants == 7


# ══════════════════════════════════════════════════════════════════════════════
# US-003 — Format affichage Telegram
# ══════════════════════════════════════════════════════════════════════════════

class TestUS003AffichageTelegram:

    def test_us003_ca1_vegetatif_affichage(self):
        """[US-003/CA1] Végétatif : affiche 'X plants (récoltés Y)'."""
        s = StockCulture(
            culture="salade", unite="plants", type_organe="végétatif",
            plants_plantes=25, plants_perdus=4, recoltes_total=2, nb_recoltes=2
        )
        ligne = format_stock_ligne_telegram(s)
        assert "salade" in ligne
        assert "19" in ligne          # stock = 25 - 4 - 2
        assert "planté 25" in ligne
        assert "perdu 4"   in ligne
        assert "récolté 2" in ligne

    def test_us003_ca2_reproducteur_affichage(self):
        """[US-003/CA2] Reproducteur : affiche 'X plants actifs · Y kg récoltés'."""
        s = StockCulture(
            culture="tomate", unite="plants", type_organe="reproducteur",
            plants_plantes=5, plants_perdus=0, recoltes_total=14.0, nb_recoltes=3,
            unite_recolte="kg"
        )
        ligne = format_stock_ligne_telegram(s)
        assert "tomate"  in ligne
        assert "5 plants actifs" in ligne
        assert "14.0 kg" in ligne
        assert "3 fois"  in ligne

    def test_us003_ca1_vegetatif_sans_perte(self):
        """[US-003/CA1] Végétatif sans pertes : n'affiche pas 'perdu'."""
        s = StockCulture(
            culture="radis", unite="plants", type_organe="végétatif",
            plants_plantes=20, plants_perdus=0, recoltes_total=5, nb_recoltes=1
        )
        ligne = format_stock_ligne_telegram(s)
        assert "perdu" not in ligne
        assert "15" in ligne   # 20 - 5

    def test_us003_ca2_reproducteur_sans_recolte(self):
        """[US-003/CA2] Reproducteur sans récolte : n'affiche pas le rendement."""
        s = StockCulture(
            culture="poivron", unite="plants", type_organe="reproducteur",
            plants_plantes=8, plants_perdus=0, recoltes_total=0, nb_recoltes=0
        )
        ligne = format_stock_ligne_telegram(s)
        assert "8 plants actifs" in ligne
        # Pas de rendement affiché si aucune récolte
        assert "kg" not in ligne

    def test_us003_ca3_deux_sections_distinctes(self, db):
        """[US-003/CA3] Le calcul retourne bien des objets séparables par type."""
        _seed_cultures(db)
        db.add(Evenement(type_action="plantation", culture="tomate", quantite=5, rang=1, unite="plants", date=date(2026,3,1)))
        db.add(Evenement(type_action="plantation", culture="salade", quantite=10, rang=1, unite="plants", date=date(2026,3,1)))
        db.commit()

        stocks = calcul_stock_cultures(db)

        veg   = {c: s for c, s in stocks.items() if not s.is_reproducteur}
        repro = {c: s for c, s in stocks.items() if s.is_reproducteur}

        assert "salade" in veg
        assert "tomate" in repro
        assert "tomate" not in veg
        assert "salade" not in repro
