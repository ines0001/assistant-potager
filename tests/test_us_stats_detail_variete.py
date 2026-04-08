"""
tests/test_us_stats_detail_variete.py — Tests US_Stats_detail_par_variete
--------------------------------------------------------------------------
Couverture :
  - CA1 : /stats sans argument → synthèse inchangée + hint
  - CA2 : hint en pied de message synthèse
  - CA3 : /stats tomate → détail par variété
  - CA4 : blocs variété avec indicateurs
  - CA5 : variété None regroupée comme "Variété non précisée"
  - CA6 : culture inconnue → "Aucune donnée pour …"
  - CA7 : insensibilité à la casse
  - CA8 : _extract_stats_culture détecte "stats tomate"
"""
import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock, AsyncMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.db import Base
from database.models import Evenement, CultureConfig
from utils.stock import (
    calcul_stock_par_variete,
    format_variete_bloc_telegram,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def engine():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=eng)
    return eng


@pytest.fixture
def db(engine):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.rollback()
    session.close()


def _seed_config(db):
    db.add(CultureConfig(nom="tomate",  type_organe_recolte="reproducteur"))
    db.add(CultureConfig(nom="salade",  type_organe_recolte="végétatif"))
    db.commit()


# ══════════════════════════════════════════════════════════════════════════════
# calcul_stock_par_variete
# ══════════════════════════════════════════════════════════════════════════════

class TestCalcStockParVariete:

    def test_ca6_culture_inconnue_retourne_liste_vide(self, db):
        """[CA6] Culture absente de la base → []."""
        assert calcul_stock_par_variete(db, "inexistant") == []

    def test_ca7_insensible_casse(self, db):
        """[CA7] 'Tomate' et 'tomate' donnent le même résultat."""
        _seed_config(db)
        db.add(Evenement(
            type_action="plantation", culture="tomate", variete="cerise",
            quantite=3, unite="plants", date=datetime(2025, 4, 1),
        ))
        db.commit()
        r1 = calcul_stock_par_variete(db, "tomate")
        r2 = calcul_stock_par_variete(db, "Tomate")
        assert len(r1) == len(r2) == 1
        assert r1[0]["plants_plantes"] == r2[0]["plants_plantes"]

    def test_ca3_une_variete_reproducteur(self, db):
        """[CA3] Une variété reproducteur retourne la bonne structure."""
        _seed_config(db)
        db.add(Evenement(
            type_action="plantation", culture="tomate", variete="cœur de bœuf",
            quantite=3, unite="plants", date=datetime(2025, 4, 15),
        ))
        db.add(Evenement(
            type_action="recolte", culture="tomate", variete="cœur de bœuf",
            quantite=4.2, unite="kg", date=datetime(2025, 9, 12),
        ))
        db.commit()
        result = calcul_stock_par_variete(db, "tomate")
        assert len(result) == 1
        v = result[0]
        assert v["variete"] == "cœur de bœuf"
        assert v["plants_plantes"] == 3
        assert v["recoltes_total"] == 4.2
        assert v["type_organe"] == "reproducteur"
        assert v["date_premiere_plantation"] == datetime(2025, 4, 15)
        assert v["date_derniere_recolte"] == datetime(2025, 9, 12)

    def test_ca5_variete_none_groupe_comme_non_precisee(self, db):
        """[CA5] variete=None est regroupé sous 'Variété non précisée'."""
        _seed_config(db)
        db.add(Evenement(
            type_action="plantation", culture="tomate", variete=None,
            quantite=1, unite="plants", date=datetime(2025, 4, 20),
        ))
        db.commit()
        result = calcul_stock_par_variete(db, "tomate")
        noms = [v["variete"] for v in result]
        assert "Variété non précisée" in noms

    def test_ca4_plusieurs_varietes(self, db):
        """[CA4] Deux variétés → deux entrées distinctes."""
        _seed_config(db)
        db.add(Evenement(
            type_action="plantation", culture="tomate", variete="cerise",
            quantite=2, unite="plants", date=datetime(2025, 4, 20),
        ))
        db.add(Evenement(
            type_action="plantation", culture="tomate", variete="cœur de bœuf",
            quantite=3, unite="plants", date=datetime(2025, 4, 15),
        ))
        db.commit()
        result = calcul_stock_par_variete(db, "tomate")
        assert len(result) == 2
        varietes = {v["variete"] for v in result}
        assert "cerise" in varietes
        assert "cœur de bœuf" in varietes

    def test_ca4_date_derniere_recolte_none_si_pas_de_recolte(self, db):
        """[CA4] Pas de récolte → date_derniere_recolte is None (= 'en cours')."""
        _seed_config(db)
        db.add(Evenement(
            type_action="plantation", culture="tomate", variete="cerise",
            quantite=2, unite="plants", date=datetime(2026, 4, 1),
        ))
        db.commit()
        result = calcul_stock_par_variete(db, "tomate")
        assert result[0]["date_derniere_recolte"] is None

    def test_perte_deduite_correctement(self, db):
        """Les pertes par variété sont intégrées dans le calcul."""
        _seed_config(db)
        db.add(Evenement(
            type_action="plantation", culture="tomate", variete="cerise",
            quantite=5, unite="plants", date=datetime(2025, 4, 1),
        ))
        db.add(Evenement(
            type_action="perte", culture="tomate", variete="cerise",
            quantite=1, unite="plants", date=datetime(2025, 4, 15),
        ))
        db.commit()
        result = calcul_stock_par_variete(db, "tomate")
        assert result[0]["plants_perdus"] == 1

    def test_vegetatif_structure(self, db):
        """[CA4] Végétatif retourne le bon type_organe et les bonnes quantités."""
        _seed_config(db)
        db.add(Evenement(
            type_action="plantation", culture="salade", variete="batavia",
            quantite=12, unite="plants", date=datetime(2026, 3, 10),
        ))
        db.add(Evenement(
            type_action="recolte", culture="salade", variete="batavia",
            quantite=3, unite="plants", date=datetime(2026, 5, 15),
        ))
        db.commit()
        result = calcul_stock_par_variete(db, "salade")
        assert result[0]["type_organe"] == "végétatif"
        assert result[0]["recoltes_total"] == 3   # somme des quantités
        assert result[0]["nb_recoltes"] == 1       # 1 événement de récolte


# ══════════════════════════════════════════════════════════════════════════════
# format_variete_bloc_telegram
# ══════════════════════════════════════════════════════════════════════════════

class TestFormatVarieteBlocTelegram:

    def _data(self, **kwargs):
        base = {
            "variete":                  "Cerise",
            "plants_plantes":           2.0,
            "plants_perdus":            0.0,
            "nb_recoltes":              12,
            "recoltes_total":           3.8,
            "unite_recolte":            "kg",
            "unite_plant":              "plants",
            "type_organe":              "reproducteur",
            "date_premiere_plantation": datetime(2025, 4, 20),
            "date_derniere_recolte":    None,
        }
        base.update(kwargs)
        return base

    def test_ca4_reproducteur_en_cours(self):
        """[CA4] Reproducteur sans récolte finale → 'en cours'."""
        bloc = format_variete_bloc_telegram(self._data())
        assert "en cours" in bloc
        assert "plants actifs" in bloc

    def test_ca4_reproducteur_avec_recolte(self):
        """[CA4] Reproducteur avec récolte finale → date affichée."""
        data = self._data(date_derniere_recolte=datetime(2025, 9, 12))
        bloc = format_variete_bloc_telegram(data)
        assert "en cours" not in bloc
        assert "📅" in bloc

    def test_ca4_vegetatif_stock_calcul(self):
        """[CA4] Végétatif : stock = planté - perdu - récolté."""
        data = self._data(
            type_organe="végétatif",
            plants_plantes=12.0,
            plants_perdus=1.0,
            recoltes_total=3.0,
            nb_recoltes=3,
            unite_recolte="plants",
            date_derniere_recolte=datetime(2025, 5, 18),
        )
        bloc = format_variete_bloc_telegram(data)
        # stock attendu = 12 - 1 - 3 = 8
        assert "8 plants" in bloc
        assert "planté 12" in bloc
        assert "récolté 3" in bloc

    def test_ca5_nom_variete_non_precisee(self):
        """[CA5] 'Variété non précisée' apparaît dans le bloc."""
        data = self._data(variete="Variété non précisée")
        bloc = format_variete_bloc_telegram(data)
        assert "Variété non précisée" in bloc

    def test_date_meme_annee_sans_annee(self):
        """Date de la même année que maintenant → sans l'année."""
        from datetime import datetime
        current_year = datetime.now().year
        data = self._data(
            date_premiere_plantation=datetime(current_year, 4, 15),
            date_derniere_recolte=datetime(current_year, 9, 12),
        )
        bloc = format_variete_bloc_telegram(data)
        assert str(current_year) not in bloc

    def test_date_annee_differente_avec_annee(self):
        """Date d'une année passée → avec l'année."""
        data = self._data(
            date_premiere_plantation=datetime(2024, 4, 15),
            date_derniere_recolte=datetime(2024, 9, 12),
        )
        bloc = format_variete_bloc_telegram(data)
        assert "2024" in bloc


# ══════════════════════════════════════════════════════════════════════════════
# _extract_stats_culture (CA8)
# ══════════════════════════════════════════════════════════════════════════════

class TestExtractStatsCulture:

    def _call(self, texte):
        from bot import _extract_stats_culture
        return _extract_stats_culture(texte)

    def test_ca8_stats_culture_simple(self):
        """[CA8] 'stats tomate' → 'tomate'."""
        assert self._call("stats tomate") == "tomate"

    def test_ca8_statistiques_culture(self):
        """[CA8] 'statistiques salade' → 'salade'."""
        assert self._call("statistiques salade") == "salade"

    def test_ca8_stats_de_la_culture(self):
        """[CA8] 'stats de la tomate' → 'tomate'."""
        assert self._call("stats de la tomate") == "tomate"

    def test_ca8_stats_seul_retourne_none(self):
        """[CA8] 'stats' seul → None."""
        assert self._call("stats") is None

    def test_ca8_phrase_irrelevante_retourne_none(self):
        """[CA8] Phrase sans pattern → None."""
        assert self._call("j'ai récolté des tomates") is None

    def test_ca1_cmd_stats_sans_arg_hint_present(self):
        """[CA1 + CA2] /stats sans argument → synthèse + hint variété."""
        # Import inline pour éviter la dépendance à la DB réelle
        # via le mock de SessionLocal
        pass  # couvert par test_bot.py::TestCmdStats avec patch SessionLocal


# ══════════════════════════════════════════════════════════════════════════════
# cmd_stats avec argument (intégration légère)
# ══════════════════════════════════════════════════════════════════════════════

class TestCmdStatsAvecArg:

    @patch("bot.send_voice_reply", new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_ca6_culture_inconnue(self, mock_voice, db):
        """[CA6] /stats [culture_inconnue] → 'Aucune donnée pour …'."""
        from bot import cmd_stats

        mock_update = MagicMock()
        mock_update.message.reply_text = AsyncMock()

        mock_ctx = MagicMock()
        mock_ctx.args = ["marsien"]

        with patch("bot.SessionLocal", return_value=db):
            await cmd_stats(mock_update, mock_ctx)

        call_args = mock_update.message.reply_text.call_args[0][0]
        assert "marsien" in call_args.lower()

    @patch("bot.send_voice_reply", new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_ca3_culture_connue(self, mock_voice, db):
        """[CA3] /stats tomate → message détail variété."""
        from bot import cmd_stats

        _seed_config(db)
        db.add(Evenement(
            type_action="plantation", culture="tomate", variete="cerise",
            quantite=3, unite="plants", date=datetime(2025, 4, 20),
        ))
        db.commit()

        mock_update = MagicMock()
        mock_update.message.reply_text = AsyncMock()

        mock_ctx = MagicMock()
        mock_ctx.args = ["tomate"]

        with patch("bot.SessionLocal", return_value=db):
            await cmd_stats(mock_update, mock_ctx)

        call_args = mock_update.message.reply_text.call_args[0][0]
        assert "détail par variété" in call_args
        assert "Pour revenir à la synthèse" in call_args

    @patch("bot.send_voice_reply", new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_ca2_hint_dans_synthese(self, mock_voice, db):
        """[CA2] /stats sans argument → hint 'Pour le détail d'une variété' présent."""
        from bot import cmd_stats

        mock_update = MagicMock()
        mock_update.message.reply_text = AsyncMock()

        mock_ctx = MagicMock()
        mock_ctx.args = []

        with patch("bot.SessionLocal", return_value=db):
            await cmd_stats(mock_update, mock_ctx)

        call_args = mock_update.message.reply_text.call_args[0][0]
        assert "Pour le détail d'une variété" in call_args
