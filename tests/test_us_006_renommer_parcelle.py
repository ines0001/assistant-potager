"""
tests/test_us_006_renommer_parcelle.py — US-006 : Renommer une parcelle
------------------------------------------------------------------------
Couverture des critères d'acceptance :
  CA1 : /parcelle renommer <ancien> <nouveau> est reconnue par le bot
  CA2 : parcelles.nom et nom_normalise mis à jour en base
  CA3 : evenements.parcelle propagé sur tous les enregistrements liés
  CA4 : ancien nom introuvable → LookupError
  CA5 : nouveau nom déjà pris → ValueError
  CA6 : retour (parcelle, nb_evenements)
  CA7 : résolution insensible à la casse et aux accents
  CA9 : appel sans arguments suffisants → message d'aide
"""
import pytest
from unittest.mock import ANY, AsyncMock, MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.db import Base
from database.models import Evenement, Parcelle
from utils.parcelles import normalize_parcelle_name, rename_parcelle


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def engine():
    """Engine SQLite en mémoire, créé une seule fois pour le module."""
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=eng)
    return eng


@pytest.fixture
def db(engine):
    """Session de test réinitialisée entre chaque test."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def mock_telegram_update():
    """Update Telegram minimal avec reply_text mockée."""
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    return update


@pytest.fixture
def mock_ctx():
    """Factory de ContextTypes.DEFAULT_TYPE minimal."""
    def _make(args):
        ctx = MagicMock()
        ctx.args = args
        return ctx
    return _make


# ── Helpers de données ────────────────────────────────────────────────────────


def _cree_parcelle(db, nom: str, ordre: int = 1) -> Parcelle:
    """Insère une parcelle en base et retourne l'objet."""
    p = Parcelle(
        nom=nom,
        nom_normalise=normalize_parcelle_name(nom),
        ordre=ordre,
        actif=True,
    )
    db.add(p)
    db.flush()
    return p


def _cree_evenements(db, parcelle_nom: str, nb: int) -> list[Evenement]:
    """Insère nb événements liés à la parcelle (par nom textuel)."""
    evts = [
        Evenement(type_action="plantation", culture="tomate", parcelle=parcelle_nom)
        for _ in range(nb)
    ]
    db.add_all(evts)
    db.flush()
    return evts


# ── Tests unitaires : rename_parcelle ─────────────────────────────────────────


class TestRenameParcelle:
    """Tests de la fonction utilitaire rename_parcelle."""

    # ── CA2 + CA6 ─────────────────────────────────────────────────────────────

    def test_006_rename_ca2_ca6_retour_et_mise_a_jour_bdd(self, db) -> None:
        """[CA2, CA6] nom + nom_normalise mis à jour ; retour (Parcelle, int)."""
        # Arrange
        _cree_parcelle(db, "sud", ordre=1)

        # Act
        parc, nb = rename_parcelle(db, "sud", "carré-sud")

        # Assert
        assert isinstance(parc, Parcelle)
        assert isinstance(nb, int)
        assert parc.nom == "carré-sud"
        assert parc.nom_normalise == "carresud"

    def test_006_rename_ca2_persistance_en_base(self, db) -> None:
        """[CA2] Les changements sont persistés après commit (vérif. via requête)."""
        # Arrange
        _cree_parcelle(db, "nord", ordre=1)

        # Act
        rename_parcelle(db, "nord", "grand-nord")
        parc_en_base = db.query(Parcelle).filter(Parcelle.nom == "grand-nord").first()

        # Assert
        assert parc_en_base is not None
        assert parc_en_base.nom_normalise == "grandnord"

    # ── CA3 ───────────────────────────────────────────────────────────────────

    def test_006_rename_ca3_propagation_evenements(self, db) -> None:
        """[CA3] Tous les événements sont mis à jour avec le nouveau nom."""
        # Arrange
        _cree_parcelle(db, "est", ordre=1)
        _cree_evenements(db, "est", 5)

        # Act
        parc, nb = rename_parcelle(db, "est", "est-jardin")

        # Assert
        assert nb == 5
        anciens = db.query(Evenement).filter(Evenement.parcelle == "est").count()
        nouveaux = db.query(Evenement).filter(Evenement.parcelle == "est-jardin").count()
        assert anciens == 0
        assert nouveaux == 5

    def test_006_rename_ca3_zero_evenement(self, db) -> None:
        """[CA3] Parcelle sans événements → nb retourné vaut 0."""
        # Arrange
        _cree_parcelle(db, "ouest", ordre=1)

        # Act
        _, nb = rename_parcelle(db, "ouest", "ouest-potager")

        # Assert
        assert nb == 0

    def test_006_rename_ca3_propagation_partielle(self, db) -> None:
        """[CA3] Seuls les événements de la parcelle renommée sont modifiés."""
        # Arrange
        _cree_parcelle(db, "nord", ordre=1)
        _cree_parcelle(db, "sud", ordre=2)
        _cree_evenements(db, "nord", 3)
        _cree_evenements(db, "sud", 7)

        # Act
        _, nb = rename_parcelle(db, "nord", "nord-nouveau")

        # Assert — les événements "sud" ne bougent pas
        assert nb == 3
        assert db.query(Evenement).filter(Evenement.parcelle == "sud").count() == 7

    # ── CA4 ───────────────────────────────────────────────────────────────────

    def test_006_rename_ca4_lookup_error_si_inconnu(self, db) -> None:
        """[CA4] LookupError levée si l'ancien nom ne correspond à aucune parcelle."""
        # Arrange — base vide

        # Act / Assert
        with pytest.raises(LookupError):
            rename_parcelle(db, "inexistante", "nouveau")

    def test_006_rename_ca4_message_contient_nom(self, db) -> None:
        """[CA4] L'exception LookupError contient le nom introuvable."""
        # Arrange — base vide

        # Act / Assert
        with pytest.raises(LookupError, match="fantome"):
            rename_parcelle(db, "fantome", "test")

    # ── CA5 ───────────────────────────────────────────────────────────────────

    def test_006_rename_ca5_value_error_si_conflit(self, db) -> None:
        """[CA5] ValueError si le nouveau nom est déjà pris par une autre parcelle."""
        # Arrange
        _cree_parcelle(db, "nord", ordre=1)
        _cree_parcelle(db, "sud", ordre=2)

        # Act / Assert
        with pytest.raises(ValueError, match="déjà utilisé"):
            rename_parcelle(db, "nord", "sud")

    def test_006_rename_ca5_conflit_insensible_casse(self, db) -> None:
        """[CA5] Le conflit est détecté même si la casse diffère (SUD vs sud)."""
        # Arrange
        _cree_parcelle(db, "nord", ordre=1)
        _cree_parcelle(db, "sud", ordre=2)

        # Act / Assert
        with pytest.raises(ValueError):
            rename_parcelle(db, "nord", "SUD")

    # ── CA6 ───────────────────────────────────────────────────────────────────

    def test_006_rename_ca6_retour_tuple(self, db) -> None:
        """[CA6] La fonction retourne bien un tuple (Parcelle, int)."""
        # Arrange
        _cree_parcelle(db, "parcelle-test", ordre=1)
        _cree_evenements(db, "parcelle-test", 12)

        # Act
        resultat = rename_parcelle(db, "parcelle-test", "nouveau-nom")

        # Assert
        assert isinstance(resultat, tuple)
        assert len(resultat) == 2
        assert isinstance(resultat[0], Parcelle)
        assert resultat[1] == 12

    # ── CA7 ───────────────────────────────────────────────────────────────────

    def test_006_rename_ca7_insensible_casse(self, db) -> None:
        """[CA7] L'ancien nom est résolu même si la casse est différente."""
        # Arrange
        _cree_parcelle(db, "Ouest", ordre=1)
        _cree_evenements(db, "Ouest", 3)

        # Act
        parc, nb = rename_parcelle(db, "OUEST", "ouest-jardin")

        # Assert
        assert parc.nom == "ouest-jardin"
        assert nb == 3

    def test_006_rename_ca7_insensible_accents(self, db) -> None:
        """[CA7] L'ancien nom est résolu même si les accents sont absents."""
        # Arrange
        _cree_parcelle(db, "côté-est", ordre=1)

        # Act
        parc, _ = rename_parcelle(db, "cote-est", "est")

        # Assert
        assert parc.nom == "est"

    def test_006_rename_ca7_insensible_tirets(self, db) -> None:
        """[CA7] Les tirets sont ignorés lors de la normalisation."""
        # Arrange
        _cree_parcelle(db, "nord-est", ordre=1)

        # Act — recherche sans tiret
        parc, _ = rename_parcelle(db, "nordest", "nord-est-v2")

        # Assert
        assert parc.nom == "nord-est-v2"

    # ── Edge cases ────────────────────────────────────────────────────────────

    def test_006_rename_edge_meme_normalise_propre_parcelle(self, db) -> None:
        """
        Renommer "sud" → "SUD" (même nom_normalise) ne doit pas lever ValueError
        car la parcelle cible EST la même.
        """
        # Arrange
        _cree_parcelle(db, "sud", ordre=1)

        # Act / Assert — pas d'exception attendue
        parc, _ = rename_parcelle(db, "sud", "SUD")
        assert parc.nom == "SUD"
        assert parc.nom_normalise == "sud"

    def test_006_rename_edge_atomique(self, db) -> None:
        """[CA2+CA3] Un seul commit : parcelle et événements cohérents."""
        # Arrange
        _cree_parcelle(db, "milieu", ordre=1)
        _cree_evenements(db, "milieu", 4)

        # Act
        rename_parcelle(db, "milieu", "centre")

        # Assert — ancienne valeur effacée, nouvelle présente
        assert db.query(Evenement).filter(Evenement.parcelle == "milieu").count() == 0
        assert db.query(Evenement).filter(Evenement.parcelle == "centre").count() == 4


# ── Tests handler bot : cmd_parcelle renommer ─────────────────────────────────


class TestCmdParcelleRenommerBot:
    """Tests du handler Telegram pour la sous-commande 'renommer'."""

    # ── CA9 ───────────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_006_bot_ca9_aucun_arg(self, mock_telegram_update, mock_ctx) -> None:
        """[CA9] /parcelle renommer (sans args) → message d'aide."""
        # Arrange
        from bot import cmd_parcelle
        ctx = mock_ctx(["renommer"])

        # Act
        await cmd_parcelle(mock_telegram_update, ctx)

        # Assert
        mock_telegram_update.message.reply_text.assert_called_once()
        texte = mock_telegram_update.message.reply_text.call_args[0][0]
        assert any(mot in texte.lower() for mot in ["usage", "ancien", "nouveau"])

    @pytest.mark.asyncio
    async def test_006_bot_ca9_un_seul_arg(self, mock_telegram_update, mock_ctx) -> None:
        """[CA9] /parcelle renommer <ancien> (sans nouveau) → message d'aide."""
        # Arrange
        from bot import cmd_parcelle
        ctx = mock_ctx(["renommer", "sud"])

        # Act
        await cmd_parcelle(mock_telegram_update, ctx)

        # Assert
        mock_telegram_update.message.reply_text.assert_called_once()
        texte = mock_telegram_update.message.reply_text.call_args[0][0]
        assert any(mot in texte.lower() for mot in ["usage", "ancien", "nouveau"])

    # ── CA1 ───────────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_006_bot_ca1_commande_renommer_reconnue(
        self, mock_telegram_update, mock_ctx
    ) -> None:
        """[CA1] /parcelle renommer <ancien> <nouveau> déclenche rename_parcelle."""
        # Arrange
        from bot import cmd_parcelle
        parc_mock = MagicMock()
        parc_mock.nom = "nouveau-nom"
        ctx = mock_ctx(["renommer", "ancien-nom", "nouveau-nom"])

        # Act
        with patch("bot.SessionLocal") as MockSession, \
             patch("bot.rename_parcelle", return_value=(parc_mock, 0)) as mock_rename:
            MockSession.return_value = MagicMock()
            await cmd_parcelle(mock_telegram_update, ctx)

        # Assert — rename_parcelle a bien été appelée avec les bons arguments
        mock_rename.assert_called_once_with(ANY, "ancien-nom", "nouveau-nom")

    @pytest.mark.asyncio
    async def test_006_bot_ca1_nouveau_nom_multimots_reconstitue(
        self, mock_telegram_update, mock_ctx
    ) -> None:
        """[CA1] Nouveau nom multi-mots reconstitué depuis ctx.args (ex: 'grand nord')."""
        # Arrange
        from bot import cmd_parcelle
        parc_mock = MagicMock()
        parc_mock.nom = "grand nord"
        ctx = mock_ctx(["renommer", "nord", "grand", "nord"])

        # Act
        with patch("bot.SessionLocal") as MockSession, \
             patch("bot.rename_parcelle", return_value=(parc_mock, 0)) as mock_rename:
            MockSession.return_value = MagicMock()
            await cmd_parcelle(mock_telegram_update, ctx)

        # Assert — les mots sont joints avec espace
        mock_rename.assert_called_once_with(ANY, "nord", "grand nord")

    # ── CA6 ───────────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_006_bot_ca6_succes_pluriel(
        self, mock_telegram_update, mock_ctx
    ) -> None:
        """[CA6] Renommage réussi avec événements pluriel → confirmation détaillée."""
        # Arrange
        from bot import cmd_parcelle
        parc_mock = MagicMock()
        parc_mock.nom = "carré-sud"
        ctx = mock_ctx(["renommer", "sud", "carré-sud"])

        # Act
        with patch("bot.SessionLocal") as MockSession, \
             patch("bot.rename_parcelle", return_value=(parc_mock, 5)):
            MockSession.return_value = MagicMock()
            await cmd_parcelle(mock_telegram_update, ctx)

        # Assert
        mock_telegram_update.message.reply_text.assert_called_once()
        texte = mock_telegram_update.message.reply_text.call_args[0][0]
        assert "carré-sud" in texte
        assert "5" in texte
        assert "événements" in texte  # pluriel

    @pytest.mark.asyncio
    async def test_006_bot_ca6_succes_singulier(
        self, mock_telegram_update, mock_ctx
    ) -> None:
        """[CA6] Renommage réussi avec 1 événement → forme singulier."""
        # Arrange
        from bot import cmd_parcelle
        parc_mock = MagicMock()
        parc_mock.nom = "est"
        ctx = mock_ctx(["renommer", "est-jardin", "est"])

        # Act
        with patch("bot.SessionLocal") as MockSession, \
             patch("bot.rename_parcelle", return_value=(parc_mock, 1)):
            MockSession.return_value = MagicMock()
            await cmd_parcelle(mock_telegram_update, ctx)

        # Assert
        texte = mock_telegram_update.message.reply_text.call_args[0][0]
        assert "1" in texte
        assert "événement" in texte  # singulier (pas "événements")

    # ── CA4 ───────────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_006_bot_ca4_introuvable(
        self, mock_telegram_update, mock_ctx
    ) -> None:
        """[CA4] LookupError → message indiquant que la parcelle est introuvable."""
        # Arrange
        from bot import cmd_parcelle
        ctx = mock_ctx(["renommer", "fantome", "nouveau"])

        # Act
        with patch("bot.SessionLocal") as MockSession, \
             patch("bot.rename_parcelle", side_effect=LookupError("fantome")):
            MockSession.return_value = MagicMock()
            await cmd_parcelle(mock_telegram_update, ctx)

        # Assert
        texte = mock_telegram_update.message.reply_text.call_args[0][0]
        assert "introuvable" in texte.lower()
        assert "fantome" in texte

    # ── CA5 ───────────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_006_bot_ca5_conflit_nom(
        self, mock_telegram_update, mock_ctx
    ) -> None:
        """[CA5] ValueError → message indiquant que le nom est déjà utilisé."""
        # Arrange
        from bot import cmd_parcelle
        ctx = mock_ctx(["renommer", "nord", "sud"])

        # Act
        with patch("bot.SessionLocal") as MockSession, \
             patch("bot.rename_parcelle", side_effect=ValueError("déjà utilisé")):
            MockSession.return_value = MagicMock()
            await cmd_parcelle(mock_telegram_update, ctx)

        # Assert
        texte = mock_telegram_update.message.reply_text.call_args[0][0]
        assert any(mot in texte.lower() for mot in ["déjà", "utilisé"])

    # ── Erreur générique ──────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_006_bot_erreur_generique(
        self, mock_telegram_update, mock_ctx
    ) -> None:
        """Exception inattendue → message d'erreur générique envoyé à l'utilisateur."""
        # Arrange
        from bot import cmd_parcelle
        ctx = mock_ctx(["renommer", "nord", "nouveau"])

        # Act
        with patch("bot.SessionLocal") as MockSession, \
             patch("bot.rename_parcelle", side_effect=RuntimeError("DB crash")):
            MockSession.return_value = MagicMock()
            await cmd_parcelle(mock_telegram_update, ctx)

        # Assert — une réponse est quand même envoyée
        mock_telegram_update.message.reply_text.assert_called_once()
        texte = mock_telegram_update.message.reply_text.call_args[0][0]
        assert "❌" in texte or "erreur" in texte.lower()

    # ── Nettoyage ressources ──────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_006_bot_db_ferme_apres_succes(
        self, mock_telegram_update, mock_ctx
    ) -> None:
        """La session DB est fermée (finally) même en cas de succès."""
        # Arrange
        from bot import cmd_parcelle
        parc_mock = MagicMock()
        parc_mock.nom = "est"
        ctx = mock_ctx(["renommer", "ouest", "est"])
        db_mock = MagicMock()

        # Act
        with patch("bot.SessionLocal", return_value=db_mock), \
             patch("bot.rename_parcelle", return_value=(parc_mock, 0)):
            await cmd_parcelle(mock_telegram_update, ctx)

        # Assert
        db_mock.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_006_bot_db_ferme_apres_erreur(
        self, mock_telegram_update, mock_ctx
    ) -> None:
        """La session DB est fermée (finally) même en cas d'erreur."""
        # Arrange
        from bot import cmd_parcelle
        ctx = mock_ctx(["renommer", "nord", "sud"])
        db_mock = MagicMock()

        # Act
        with patch("bot.SessionLocal", return_value=db_mock), \
             patch("bot.rename_parcelle", side_effect=LookupError("nord")):
            await cmd_parcelle(mock_telegram_update, ctx)

        # Assert
        db_mock.close.assert_called_once()
