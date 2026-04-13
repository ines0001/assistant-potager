"""
tests/test_us006_renommer_parcelle.py — Tests US-006 : Renommer une parcelle
-----------------------------------------------------------------------------
Couverture :
  - CA2  : nom + nom_normalise mis à jour en base
  - CA3  : propagation sur evenements.parcelle
  - CA4  : LookupError si ancien nom introuvable
  - CA5  : ValueError si nouveau nom déjà utilisé
  - CA6  : retour (parcelle, nb_evenements)
  - CA7  : résolution via nom_normalise (insensible casse/accents)
  - CA1/CA8/CA9 : handler bot.py (cmd_parcelle renommer)
"""
import pytest
from unittest.mock import ANY, AsyncMock, MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.db import Base
from database.models import Evenement, Parcelle
from utils.parcelles import rename_parcelle


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


def _seed_parcelle(db: object, nom: str, ordre: int = 1) -> Parcelle:
    """Crée une parcelle en base et la retourne."""
    from utils.parcelles import normalize_parcelle_name
    p = Parcelle(
        nom=nom,
        nom_normalise=normalize_parcelle_name(nom),
        ordre=ordre,
        actif=True,
    )
    db.add(p)
    db.flush()
    return p


def _seed_evenements(db: object, parcelle_nom: str, nb: int) -> list:
    """Crée nb événements liés à la parcelle (par nom textuel)."""
    evts = []
    for i in range(nb):
        e = Evenement(
            type_action="plantation",
            culture="tomate",
            parcelle=parcelle_nom,
        )
        db.add(e)
        evts.append(e)
    db.flush()
    return evts


# ── Tests unitaires : rename_parcelle ─────────────────────────────────────────

class TestRenameParcelle:
    """[CA2, CA3, CA4, CA5, CA6, CA7] Tests de la fonction rename_parcelle."""

    def test_renommage_nominal(self, db):
        """[CA2, CA3, CA6] Renommage simple avec propagation sur les événements."""
        _seed_parcelle(db, "sud", ordre=1)
        _seed_evenements(db, "sud", 15)

        parc, nb = rename_parcelle(db, "sud", "carré-sud")

        assert parc.nom == "carré-sud"
        assert parc.nom_normalise == "carresud"
        assert nb == 15

        # Vérification en base
        evts = db.query(Evenement).filter(Evenement.parcelle == "carré-sud").all()
        assert len(evts) == 15

    def test_propagation_aucun_evenement(self, db):
        """[CA3] Renommage sans événements → 0 retourné."""
        _seed_parcelle(db, "nord", ordre=1)

        parc, nb = rename_parcelle(db, "nord", "nord-potager")

        assert parc.nom == "nord-potager"
        assert nb == 0

    def test_insensible_casse(self, db):
        """[CA7] La résolution de l'ancien nom est insensible à la casse."""
        _seed_parcelle(db, "Ouest", ordre=1)
        _seed_evenements(db, "Ouest", 3)

        parc, nb = rename_parcelle(db, "OUEST", "ouest-jardin")

        assert parc.nom == "ouest-jardin"
        assert nb == 3

    def test_insensible_accents(self, db):
        """[CA7] La résolution de l'ancien nom ignore les accents."""
        _seed_parcelle(db, "côté-est", ordre=1)

        parc, nb = rename_parcelle(db, "cote-est", "est")

        assert parc.nom == "est"

    def test_ancien_nom_introuvable(self, db):
        """[CA4] LookupError si l'ancien nom n'existe pas."""
        with pytest.raises(LookupError):
            rename_parcelle(db, "inexistante", "nouveau")

    def test_nouveau_nom_deja_utilise(self, db):
        """[CA5] ValueError si le nouveau nom est déjà pris par une autre parcelle."""
        _seed_parcelle(db, "nord", ordre=1)
        _seed_parcelle(db, "sud", ordre=2)

        with pytest.raises(ValueError, match="déjà utilisé"):
            rename_parcelle(db, "nord", "sud")

    def test_transaction_atomique(self, db):
        """[CA2+CA3] Un seul commit — les deux mises à jour sont cohérentes."""
        _seed_parcelle(db, "est", ordre=1)
        _seed_evenements(db, "est", 5)

        parc, nb = rename_parcelle(db, "est", "est-nouveau")

        # Après commit, l'ancienne valeur ne doit plus exister
        anciens_evts = db.query(Evenement).filter(Evenement.parcelle == "est").all()
        nouveaux_evts = db.query(Evenement).filter(Evenement.parcelle == "est-nouveau").all()
        assert len(anciens_evts) == 0
        assert len(nouveaux_evts) == 5

    def test_renommage_meme_nom_normalise_autre_casse(self, db):
        """
        Renommer avec un nouveau nom qui a le même nom_normalise que l'actuel
        (ex : "sud" → "SUD") doit fonctionner sans lever ValueError.
        """
        _seed_parcelle(db, "sud", ordre=1)

        parc, nb = rename_parcelle(db, "sud", "SUD")

        assert parc.nom == "SUD"
        assert parc.nom_normalise == "sud"


# ── Tests handler bot : cmd_parcelle renommer ─────────────────────────────────

class TestCmdParcelleRenommer:
    """[CA1, CA8, CA9] Tests du handler Telegram cmd_parcelle."""

    def _make_update(self):
        update = MagicMock()
        update.message.reply_text = AsyncMock()
        return update

    def _make_ctx(self, args):
        ctx = MagicMock()
        ctx.args = args
        return ctx

    @pytest.mark.asyncio
    async def test_ca9_args_insuffisants_un_seul_arg(self):
        """[CA9] /parcelle renommer sans assez d'arguments → usage + exemple."""
        from bot import cmd_parcelle
        update = self._make_update()
        ctx = self._make_ctx(["renommer"])  # manque ancien ET nouveau

        await cmd_parcelle(update, ctx)

        update.message.reply_text.assert_called_once()
        appel = update.message.reply_text.call_args
        texte = appel[0][0]
        assert "Usage" in texte or "usage" in texte.lower() or "ancien" in texte.lower()

    @pytest.mark.asyncio
    async def test_ca9_args_insuffisants_seul_arg(self):
        """[CA9] /parcelle renommer <seularg> → usage + exemple."""
        from bot import cmd_parcelle
        update = self._make_update()
        ctx = self._make_ctx(["renommer", "seularg"])  # manque le nouveau nom

        await cmd_parcelle(update, ctx)

        update.message.reply_text.assert_called_once()
        appel = update.message.reply_text.call_args
        texte = appel[0][0]
        assert "Usage" in texte or "usage" in texte.lower() or "ancien" in texte.lower()

    @pytest.mark.asyncio
    async def test_ca6_confirmation_succes(self):
        """[CA6] Renommage réussi → confirmation avec nb événements."""
        from bot import cmd_parcelle

        parcelle_mock = MagicMock()
        parcelle_mock.nom = "carré-sud"

        update = self._make_update()
        ctx = self._make_ctx(["renommer", "sud", "carré-sud"])

        with patch("bot.SessionLocal") as MockSession, \
             patch("bot.rename_parcelle", return_value=(parcelle_mock, 15)) as mock_rename:
            db_mock = MagicMock()
            MockSession.return_value = db_mock

            await cmd_parcelle(update, ctx)

            mock_rename.assert_called_once_with(db_mock, "sud", "carré-sud")
            update.message.reply_text.assert_called_once()
            texte = update.message.reply_text.call_args[0][0]
            assert "renommée" in texte.lower() or "Parcelle" in texte
            assert "15" in texte
            assert "carré-sud" in texte

    @pytest.mark.asyncio
    async def test_ca4_ancien_nom_introuvable(self):
        """[CA4] LookupError → message d'erreur 'introuvable'."""
        from bot import cmd_parcelle

        update = self._make_update()
        ctx = self._make_ctx(["renommer", "inexistante", "nouveau"])

        with patch("bot.SessionLocal") as MockSession, \
             patch("bot.rename_parcelle", side_effect=LookupError("inexistante")):
            MockSession.return_value = MagicMock()

            await cmd_parcelle(update, ctx)

            texte = update.message.reply_text.call_args[0][0]
            assert "introuvable" in texte.lower()
            assert "inexistante" in texte

    @pytest.mark.asyncio
    async def test_ca5_nouveau_nom_deja_utilise(self):
        """[CA5] ValueError → message 'déjà utilisé'."""
        from bot import cmd_parcelle

        update = self._make_update()
        ctx = self._make_ctx(["renommer", "nord", "sud"])

        with patch("bot.SessionLocal") as MockSession, \
             patch("bot.rename_parcelle", side_effect=ValueError("déjà utilisé")):
            MockSession.return_value = MagicMock()

            await cmd_parcelle(update, ctx)

            texte = update.message.reply_text.call_args[0][0]
            assert "déjà" in texte.lower() or "utilisé" in texte.lower()

    @pytest.mark.asyncio
    async def test_nom_avec_espaces_reconstitue(self):
        """[CA1] Nouveau nom avec espaces correctement reconstitué depuis ctx.args."""
        from bot import cmd_parcelle

        parcelle_mock = MagicMock()
        parcelle_mock.nom = "grand nord"

        update = self._make_update()
        ctx = self._make_ctx(["renommer", "nord", "grand", "nord"])

        with patch("bot.SessionLocal") as MockSession, \
             patch("bot.rename_parcelle", return_value=(parcelle_mock, 0)) as mock_rename:
            MockSession.return_value = MagicMock()

            await cmd_parcelle(update, ctx)

            # Le nouveau nom doit être "grand nord" (espace reconstitué)
            mock_rename.assert_called_once_with(ANY, "nord", "grand nord")
