"""
tests/test_us_aide_contextuelle_parcelle.py
--------------------------------------------
Tests US Aide contextuelle /help [commande]        (CA1–CA10)
Tests US /parcelle sous-commandes modifier/lister  (CA1–CA10)
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from bot import cmd_help, cmd_parcelle, _cmd_parcelles_lister
from utils.parcelles import update_parcelle
from database.models import Parcelle


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures communes
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_update():
    """Update Telegram minimaliste avec reply_text mocké."""
    upd = MagicMock()
    upd.message.reply_text = AsyncMock()
    return upd


@pytest.fixture
def mock_ctx():
    """ContextTypes mocké avec args vide par défaut."""
    ctx = MagicMock()
    ctx.args = []
    return ctx


# ──────────────────────────────────────────────────────────────────────────────
# Fixture SQLite in-memory : parcelle de test
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def parcelle_nord(test_db):
    """Crée une parcelle 'nord' dans la base SQLite de test."""
    p = Parcelle(
        nom="nord",
        nom_normalise="nord",
        exposition="est",
        superficie_m2=10.0,
        ordre=1,
        actif=True,
    )
    test_db.add(p)
    test_db.commit()
    test_db.refresh(p)
    return p


# ═══════════════════════════════════════════════════════════════════════════════
# US 1 — Aide contextuelle /help [commande]
# ═══════════════════════════════════════════════════════════════════════════════

class TestHelpCA1Parcelle:
    @pytest.mark.asyncio
    async def test_us_help_ca1_parcelle_message_dedie(self, mock_update, mock_ctx) -> None:
        """CA1 — /help parcelle → message dédié parcelles (Parcelles, /plan, /parcelle ajouter)."""
        # Arrange
        mock_ctx.args = ["parcelle"]
        # Act
        await cmd_help(mock_update, mock_ctx)
        # Assert
        texte = mock_update.message.reply_text.call_args[0][0]
        assert "Parcelles" in texte
        assert "/plan" in texte
        assert "/parcelle ajouter" in texte


class TestHelpCA2Semis:
    @pytest.mark.asyncio
    async def test_us_help_ca2_semis_message_dedie(self, mock_update, mock_ctx) -> None:
        """CA2 — /help semis → message dédié semis (Semis, pépinière, pleine terre)."""
        # Arrange
        mock_ctx.args = ["semis"]
        # Act
        await cmd_help(mock_update, mock_ctx)
        # Assert
        texte = mock_update.message.reply_text.call_args[0][0]
        assert "Semis" in texte
        assert "pépinière" in texte
        assert "pleine terre" in texte


class TestHelpCA3Godet:
    @pytest.mark.asyncio
    async def test_us_help_ca3_godet_message_dedie(self, mock_update, mock_ctx) -> None:
        """CA3 — /help godet → message dédié godet."""
        # Arrange
        mock_ctx.args = ["godet"]
        # Act
        await cmd_help(mock_update, mock_ctx)
        # Assert
        texte = mock_update.message.reply_text.call_args[0][0]
        assert "godet" in texte.lower()


class TestHelpCA4Recolte:
    @pytest.mark.asyncio
    async def test_us_help_ca4_recolte_message_dedie(self, mock_update, mock_ctx) -> None:
        """CA4 — /help recolte → message dédié récoltes."""
        # Arrange
        mock_ctx.args = ["recolte"]
        # Act
        await cmd_help(mock_update, mock_ctx)
        # Assert
        texte = mock_update.message.reply_text.call_args[0][0]
        assert "écolte" in texte  # couvre "Récolte" et "récolte"


class TestHelpCA5Stock:
    @pytest.mark.asyncio
    async def test_us_help_ca5_stock_message_dedie(self, mock_update, mock_ctx) -> None:
        """CA5 — /help stock → message dédié stock."""
        # Arrange
        mock_ctx.args = ["stock"]
        # Act
        await cmd_help(mock_update, mock_ctx)
        # Assert
        texte = mock_update.message.reply_text.call_args[0][0]
        assert "Stock" in texte


class TestHelpCA6Stats:
    @pytest.mark.asyncio
    async def test_us_help_ca6_stats_message_dedie(self, mock_update, mock_ctx) -> None:
        """CA6 — /help stats → message dédié statistiques."""
        # Arrange
        mock_ctx.args = ["stats"]
        # Act
        await cmd_help(mock_update, mock_ctx)
        # Assert
        texte = mock_update.message.reply_text.call_args[0][0]
        assert "Statistiques" in texte


class TestHelpCA7MotCleInconnu:
    @pytest.mark.asyncio
    async def test_us_help_ca7_mot_cle_inconnu_message_non_reconnu(
        self, mock_update, mock_ctx
    ) -> None:
        """CA7 — /help truc → message 'non reconnu' + liste des mots-clés."""
        # Arrange
        mock_ctx.args = ["truc"]
        # Act
        await cmd_help(mock_update, mock_ctx)
        # Assert
        texte = mock_update.message.reply_text.call_args[0][0]
        assert "non reconnu" in texte or "truc" in texte
        assert "parcelle" in texte  # liste des mots-clés contient "parcelle"

    @pytest.mark.asyncio
    async def test_us_help_ca7_mot_cle_inconnu_appel_unique(
        self, mock_update, mock_ctx
    ) -> None:
        """CA7 (edge) — un seul reply_text est envoyé pour un mot-clé inconnu."""
        # Arrange
        mock_ctx.args = ["motinconnu"]
        # Act
        await cmd_help(mock_update, mock_ctx)
        # Assert
        assert mock_update.message.reply_text.call_count == 1


class TestHelpCA8SansArgument:
    @pytest.mark.asyncio
    async def test_us_help_ca8_aide_generale_contient_sections(
        self, mock_update, mock_ctx
    ) -> None:
        """CA8 — /help sans argument → aide générale (AIDE, /stats, /historique)."""
        # Arrange
        mock_ctx.args = []
        # Act
        await cmd_help(mock_update, mock_ctx)
        # Assert
        texte = mock_update.message.reply_text.call_args[0][0]
        assert "AIDE" in texte
        assert "/stats" in texte
        assert "/historique" in texte

    @pytest.mark.asyncio
    async def test_us_help_ca8_args_none_aide_generale(
        self, mock_update, mock_ctx
    ) -> None:
        """CA8 (edge) — ctx.args = None → aide générale (pas de crash)."""
        # Arrange
        mock_ctx.args = None
        # Act
        await cmd_help(mock_update, mock_ctx)
        # Assert
        texte = mock_update.message.reply_text.call_args[0][0]
        assert "AIDE" in texte


class TestHelpCA9CasseInsensible:
    @pytest.mark.asyncio
    async def test_us_help_ca9_majuscule_meme_texte_que_minuscule(self) -> None:
        """CA9 — /help Parcelle → même résultat que /help parcelle."""
        # Arrange
        upd_lower, upd_upper = MagicMock(), MagicMock()
        upd_lower.message.reply_text = AsyncMock()
        upd_upper.message.reply_text = AsyncMock()
        ctx_lower, ctx_upper = MagicMock(), MagicMock()
        ctx_lower.args = ["parcelle"]
        ctx_upper.args = ["Parcelle"]
        # Act
        await cmd_help(upd_lower, ctx_lower)
        await cmd_help(upd_upper, ctx_upper)
        # Assert
        assert upd_lower.message.reply_text.call_args[0][0] == \
               upd_upper.message.reply_text.call_args[0][0]


class TestHelpCA10AccentInsensible:
    @pytest.mark.asyncio
    async def test_us_help_ca10_accent_recolte_meme_texte(self) -> None:
        """CA10 — /help récolte (accent) → même résultat que /help recolte."""
        # Arrange
        upd_sans, upd_accent = MagicMock(), MagicMock()
        upd_sans.message.reply_text = AsyncMock()
        upd_accent.message.reply_text = AsyncMock()
        ctx_sans, ctx_accent = MagicMock(), MagicMock()
        ctx_sans.args = ["recolte"]
        ctx_accent.args = ["récolte"]
        # Act
        await cmd_help(upd_sans, ctx_sans)
        await cmd_help(upd_accent, ctx_accent)
        # Assert
        assert upd_sans.message.reply_text.call_args[0][0] == \
               upd_accent.message.reply_text.call_args[0][0]


# ═══════════════════════════════════════════════════════════════════════════════
# US 2a — update_parcelle (fonction directe, SQLite in-memory)
# ═══════════════════════════════════════════════════════════════════════════════

class TestUpdateParcelleCA4Exposition:
    def test_us_parcelle_ca4_modifier_exposition(
        self, test_db, parcelle_nord
    ) -> None:
        """CA4 — update_parcelle met à jour l'exposition."""
        # Act
        parc, modifs = update_parcelle(test_db, "nord", exposition="sud")
        # Assert
        assert parc.exposition == "sud"
        assert any("Exposition" in m for m in modifs)


class TestUpdateParcelleCA5Superficie:
    def test_us_parcelle_ca5_modifier_superficie(
        self, test_db, parcelle_nord
    ) -> None:
        """CA5 — update_parcelle met à jour la superficie."""
        # Act
        parc, modifs = update_parcelle(test_db, "nord", superficie="8.5")
        # Assert
        assert parc.superficie_m2 == pytest.approx(8.5)
        assert any("Superficie" in m for m in modifs)


class TestUpdateParcelleCA6DeuxChamps:
    def test_us_parcelle_ca6_modifier_exposition_et_superficie(
        self, test_db, parcelle_nord
    ) -> None:
        """CA6 — update_parcelle met à jour exposition ET superficie ensemble."""
        # Act
        parc, modifs = update_parcelle(
            test_db, "nord", exposition="ouest", superficie="12.0"
        )
        # Assert
        assert parc.exposition == "ouest"
        assert parc.superficie_m2 == pytest.approx(12.0)
        assert len(modifs) == 2

    def test_us_parcelle_ca6_deux_champs_liste_modifs_distincte(
        self, test_db, parcelle_nord
    ) -> None:
        """CA6 (edge) — chaque champ modifié génère une entrée distincte dans modifs."""
        # Act
        _, modifs = update_parcelle(
            test_db, "nord", exposition="nord", superficie="5.0"
        )
        # Assert
        assert any("Exposition" in m for m in modifs)
        assert any("Superficie" in m for m in modifs)


class TestUpdateParcelleCA7Inexistante:
    def test_us_parcelle_ca7_parcelle_inexistante_lever_lookup_error(
        self, test_db
    ) -> None:
        """CA7 — update_parcelle lève LookupError si la parcelle est inexistante."""
        # Act / Assert
        with pytest.raises(LookupError):
            update_parcelle(test_db, "fantome", exposition="sud")


class TestUpdateParcelleCA8ParamInconnu:
    def test_us_parcelle_ca8_parametre_inconnu_lever_value_error(
        self, test_db, parcelle_nord
    ) -> None:
        """CA8 — update_parcelle lève ValueError pour un paramètre inconnu."""
        # Act / Assert
        with pytest.raises(ValueError, match="inconnu"):
            update_parcelle(test_db, "nord", couleur="verte")

    def test_us_parcelle_ca8_message_erreur_cite_parametre(
        self, test_db, parcelle_nord
    ) -> None:
        """CA8 (edge) — le message d'erreur cite le nom du paramètre inconnu."""
        # Act / Assert
        with pytest.raises(ValueError) as exc_info:
            update_parcelle(test_db, "nord", couleur="verte")
        assert "couleur" in str(exc_info.value)


# ═══════════════════════════════════════════════════════════════════════════════
# US 2b — cmd_parcelle (via bot, SessionLocal mocké)
# ═══════════════════════════════════════════════════════════════════════════════

class TestCmdParcelleListerCA1:
    @pytest.mark.asyncio
    async def test_us_parcelle_ca1_lister_affiche_parcelles(
        self, mock_update, mock_ctx
    ) -> None:
        """CA1 — /parcelle lister → affiche les parcelles enregistrées en BDD."""
        # Arrange
        p = MagicMock(spec=Parcelle)
        p.nom = "nord"
        p.exposition = "sud"
        p.superficie_m2 = 10.0
        mock_ctx.args = ["lister"]
        mock_db = MagicMock()
        mock_db.close = MagicMock()
        # Act
        with patch("bot.SessionLocal", return_value=mock_db), \
             patch("bot.get_all_parcelles", return_value=[p]):
            await cmd_parcelle(mock_update, mock_ctx)
        # Assert
        texte = mock_update.message.reply_text.call_args[0][0]
        assert "NORD" in texte


class TestCmdParcelleListerCA2BddVide:
    @pytest.mark.asyncio
    async def test_us_parcelle_ca2_lister_bdd_vide_aucune_parcelle(
        self, mock_update, mock_ctx
    ) -> None:
        """CA2 — /parcelle lister sur BDD vide → message 'Aucune parcelle'."""
        # Arrange
        mock_ctx.args = ["lister"]
        mock_db = MagicMock()
        mock_db.close = MagicMock()
        # Act
        with patch("bot.SessionLocal", return_value=mock_db), \
             patch("bot.get_all_parcelles", return_value=[]):
            await cmd_parcelle(mock_update, mock_ctx)
        # Assert
        texte = mock_update.message.reply_text.call_args[0][0]
        assert "Aucune parcelle" in texte


class TestCmdParcellesAliasCA3:
    @pytest.mark.asyncio
    async def test_us_parcelle_ca3_alias_parcelles_meme_comportement(
        self, mock_update
    ) -> None:
        """CA3 — /parcelles → même comportement que /parcelle lister (BDD vide)."""
        # Arrange
        ctx = MagicMock()
        ctx.args = []
        mock_db = MagicMock()
        mock_db.close = MagicMock()
        # Act
        with patch("bot.SessionLocal", return_value=mock_db), \
             patch("bot.get_all_parcelles", return_value=[]):
            await _cmd_parcelles_lister(mock_update, ctx)
        # Assert
        texte = mock_update.message.reply_text.call_args[0][0]
        assert "Aucune parcelle" in texte

    @pytest.mark.asyncio
    async def test_us_parcelle_ca3_alias_parcelles_avec_donnees(
        self, mock_update
    ) -> None:
        """CA3 (edge) — /parcelles avec parcelles en base → mêmes noms que /parcelle lister."""
        # Arrange
        p = MagicMock(spec=Parcelle)
        p.nom = "sud"
        p.exposition = None
        p.superficie_m2 = None
        ctx = MagicMock()
        ctx.args = []
        mock_db = MagicMock()
        mock_db.close = MagicMock()
        # Act
        with patch("bot.SessionLocal", return_value=mock_db), \
             patch("bot.get_all_parcelles", return_value=[p]):
            await _cmd_parcelles_lister(mock_update, ctx)
        # Assert
        texte = mock_update.message.reply_text.call_args[0][0]
        assert "SUD" in texte


class TestCmdParcelleModifierCA4Exposition:
    @pytest.mark.asyncio
    async def test_us_parcelle_ca4_modifier_exposition_succes(
        self, mock_update, mock_ctx
    ) -> None:
        """CA4 — /parcelle modifier nord exposition=sud → réponse succès."""
        # Arrange
        mock_ctx.args = ["modifier", "nord", "exposition=sud"]
        p = MagicMock(spec=Parcelle)
        p.nom = "nord"
        mock_db = MagicMock()
        mock_db.close = MagicMock()
        # Act
        with patch("bot.SessionLocal", return_value=mock_db), \
             patch("bot.update_parcelle", return_value=(p, ["Exposition : sud"])):
            await cmd_parcelle(mock_update, mock_ctx)
        # Assert
        texte = mock_update.message.reply_text.call_args[0][0]
        assert "✅" in texte
        assert "Exposition" in texte


class TestCmdParcelleModifierCA5Superficie:
    @pytest.mark.asyncio
    async def test_us_parcelle_ca5_modifier_superficie_succes(
        self, mock_update, mock_ctx
    ) -> None:
        """CA5 — /parcelle modifier nord superficie=8.5 → réponse succès."""
        # Arrange
        mock_ctx.args = ["modifier", "nord", "superficie=8.5"]
        p = MagicMock(spec=Parcelle)
        p.nom = "nord"
        mock_db = MagicMock()
        mock_db.close = MagicMock()
        # Act
        with patch("bot.SessionLocal", return_value=mock_db), \
             patch("bot.update_parcelle", return_value=(p, ["Superficie : 8.5 m²"])):
            await cmd_parcelle(mock_update, mock_ctx)
        # Assert
        texte = mock_update.message.reply_text.call_args[0][0]
        assert "✅" in texte
        assert "Superficie" in texte


class TestCmdParcelleModifierCA6DeuxChamps:
    @pytest.mark.asyncio
    async def test_us_parcelle_ca6_modifier_deux_champs_affiche_les_deux(
        self, mock_update, mock_ctx
    ) -> None:
        """CA6 — /parcelle modifier nord exposition=sud superficie=8.5 → deux lignes de modif."""
        # Arrange
        mock_ctx.args = ["modifier", "nord", "exposition=sud", "superficie=8.5"]
        p = MagicMock(spec=Parcelle)
        p.nom = "nord"
        mock_db = MagicMock()
        mock_db.close = MagicMock()
        # Act
        with patch("bot.SessionLocal", return_value=mock_db), \
             patch("bot.update_parcelle", return_value=(p, ["Exposition : sud", "Superficie : 8.5 m²"])):
            await cmd_parcelle(mock_update, mock_ctx)
        # Assert
        texte = mock_update.message.reply_text.call_args[0][0]
        assert "Exposition" in texte
        assert "Superficie" in texte


class TestCmdParcelleModifierCA7Inexistante:
    @pytest.mark.asyncio
    async def test_us_parcelle_ca7_parcelle_introuvable_message_erreur(
        self, mock_update, mock_ctx
    ) -> None:
        """CA7 — /parcelle modifier inexistante exposition=sud → message 'introuvable'."""
        # Arrange
        mock_ctx.args = ["modifier", "inexistante", "exposition=sud"]
        mock_db = MagicMock()
        mock_db.close = MagicMock()
        # Act
        with patch("bot.SessionLocal", return_value=mock_db), \
             patch("bot.update_parcelle", side_effect=LookupError("inexistante")), \
             patch("bot.get_all_parcelles", return_value=[]):
            await cmd_parcelle(mock_update, mock_ctx)
        # Assert
        texte = mock_update.message.reply_text.call_args[0][0]
        assert "introuvable" in texte.lower()


class TestCmdParcelleModifierCA8ParamInconnu:
    @pytest.mark.asyncio
    async def test_us_parcelle_ca8_parametre_inconnu_message_erreur(
        self, mock_update, mock_ctx
    ) -> None:
        """CA8 — /parcelle modifier nord couleur=verte → message 'Paramètre inconnu'."""
        # Arrange
        mock_ctx.args = ["modifier", "nord", "couleur=verte"]
        mock_db = MagicMock()
        mock_db.close = MagicMock()
        err = ValueError(
            "Paramètre(s) inconnu(s) : couleur. Acceptés : exposition, superficie, ordre"
        )
        # Act
        with patch("bot.SessionLocal", return_value=mock_db), \
             patch("bot.update_parcelle", side_effect=err):
            await cmd_parcelle(mock_update, mock_ctx)
        # Assert
        texte = mock_update.message.reply_text.call_args[0][0]
        assert "❌" in texte
        assert "inconnu" in texte.lower()


class TestCmdParcelleModifierCA9SansArgSuffisant:
    @pytest.mark.asyncio
    async def test_us_parcelle_ca9_modifier_sans_nom_message_usage(
        self, mock_update, mock_ctx
    ) -> None:
        """CA9 — /parcelle modifier sans nom ni valeur → message d'usage."""
        # Arrange
        mock_ctx.args = ["modifier"]
        # Act  (pas de SessionLocal nécessaire : return avant tout appel DB)
        await cmd_parcelle(mock_update, mock_ctx)
        # Assert
        texte = mock_update.message.reply_text.call_args[0][0]
        assert "/parcelle modifier" in texte

    @pytest.mark.asyncio
    async def test_us_parcelle_ca9_modifier_avec_nom_seulement_message_usage(
        self, mock_update, mock_ctx
    ) -> None:
        """CA9 (edge) — /parcelle modifier nord (sans clé=valeur) → message d'usage."""
        # Arrange
        mock_ctx.args = ["modifier", "nord"]
        # Act
        await cmd_parcelle(mock_update, mock_ctx)
        # Assert
        texte = mock_update.message.reply_text.call_args[0][0]
        assert "/parcelle modifier" in texte


class TestCmdParcelleAjouterCA10Pending:
    @pytest.mark.asyncio
    async def test_us_parcelle_ca10_ajouter_stocke_exposition_et_superficie(
        self, mock_update
    ) -> None:
        """CA10 — /parcelle ajouter nord sud 12.5 → pending contient exposition=sud et superficie=12.5."""
        # Arrange
        ctx = MagicMock()
        ctx.args = ["ajouter", "nord", "sud", "12.5"]
        ctx.user_data = {}
        mock_db = MagicMock()
        mock_db.close = MagicMock()
        # Act
        with patch("bot.SessionLocal", return_value=mock_db), \
             patch("bot.find_doublon", return_value=(None, None)), \
             patch("bot.get_all_parcelles", return_value=[]):
            await cmd_parcelle(mock_update, ctx)
        # Assert
        pending = ctx.user_data.get("parcelle_pending", {})
        assert pending.get("exposition") == "sud"
        assert pending.get("superficie_m2") == pytest.approx(12.5)

    @pytest.mark.asyncio
    async def test_us_parcelle_ca10_ajouter_mode_parcelle_confirm(
        self, mock_update
    ) -> None:
        """CA10 (edge) — /parcelle ajouter nord sud 12.5 → user_data['mode'] == 'parcelle_confirm'."""
        # Arrange
        ctx = MagicMock()
        ctx.args = ["ajouter", "nord", "sud", "12.5"]
        ctx.user_data = {}
        mock_db = MagicMock()
        mock_db.close = MagicMock()
        # Act
        with patch("bot.SessionLocal", return_value=mock_db), \
             patch("bot.find_doublon", return_value=(None, None)), \
             patch("bot.get_all_parcelles", return_value=[]):
            await cmd_parcelle(mock_update, ctx)
        # Assert
        assert ctx.user_data.get("mode") == "parcelle_confirm"
