"""
tests/test_us_plan_occupation_parcelles.py
-------------------------------------------
Tests US_Plan_occupation_parcelles (issue GitHub #18)

Couvre :
- CA11 : normalize_parcelle_name (casse, accents, tirets, espaces)
- CA12 : levenshtein_distance (cas nominaux)
- CA10/CA12 : find_doublon (exact, proche, aucun)
- CA1-CA7 : calcul_occupation_parcelles (cultures actives, sans parcelle, âge J+, alerte)
- CA3 : seuils alerte végétatif ≥ 45j, reproducteur ≥ 90j
- cmd_plan sans arg (mock)
- cmd_plan avec parcelle inconnue
- cmd_parcelle ajouter : création, doublon exact, variante proche
"""
from __future__ import annotations

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from utils.parcelles import (
    normalize_parcelle_name,
    levenshtein_distance,
    find_doublon,
    create_parcelle,
    get_all_parcelles,
    calcul_occupation_parcelles,
)
from database.models import Evenement, Parcelle, CultureConfig
from bot import _alerte_recolte, SEUIL_ALERTE


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def db_with_parcelles(test_db):
    """BD de test avec quelques parcelles pré-insérées."""
    db = test_db
    db.add(Parcelle(nom="Nord", nom_normalise="nord", ordre=1, actif=True))
    db.add(Parcelle(nom="Sud", nom_normalise="sud", ordre=2, actif=True))
    db.add(Parcelle(nom="Est", nom_normalise="est", ordre=3, actif=True))
    db.commit()
    return db


@pytest.fixture
def db_with_cultures(test_db):
    """BD avec plantations actives pour tester calcul_occupation_parcelles."""
    db = test_db

    # CultureConfig
    db.add(CultureConfig(nom="tomate", type_organe_recolte="reproducteur"))
    db.add(CultureConfig(nom="salade", type_organe_recolte="végétatif"))
    db.add(CultureConfig(nom="basilic", type_organe_recolte="végétatif"))
    db.commit()

    today = datetime.now()
    # Tomate dans parcelle NORD plantée il y a 27 jours
    db.add(Evenement(
        type_action="plantation",
        culture="tomate",
        variete="Cœur de Bœuf",
        quantite=3.0,
        rang=1,
        unite="plants",
        parcelle="NORD",
        date=today - timedelta(days=27),
    ))
    # Salade dans parcelle NORD plantée il y a 50 jours (> seuil 45j végétatif)
    db.add(Evenement(
        type_action="plantation",
        culture="salade",
        variete="Batavia",
        quantite=8.0,
        rang=1,
        unite="plants",
        parcelle="NORD",
        date=today - timedelta(days=50),
    ))
    # Basilic sans parcelle plantée il y a 8 jours
    db.add(Evenement(
        type_action="plantation",
        culture="basilic",
        variete=None,
        quantite=20.0,
        rang=1,
        unite="plants",
        parcelle=None,
        date=today - timedelta(days=8),
    ))
    db.commit()
    return db


# ──────────────────────────────────────────────────────────────────────────────
# CA11 — normalize_parcelle_name
# ──────────────────────────────────────────────────────────────────────────────

class TestNormalizeParcelleName:
    def test_lowercase(self) -> None:
        """CA11 — Mise en minuscules."""
        assert normalize_parcelle_name("NORD") == "nord"

    def test_strip_spaces(self) -> None:
        """CA11 — Strip des espaces en début/fin."""
        assert normalize_parcelle_name("  nord  ") == "nord"

    def test_remove_accents(self) -> None:
        """CA11 — Suppression des accents."""
        assert normalize_parcelle_name("côté") == "cote"

    def test_remove_hyphens(self) -> None:
        """CA11 — Suppression des tirets."""
        assert normalize_parcelle_name("nord-est") == "nordest"

    def test_remove_internal_spaces(self) -> None:
        """CA11 — Suppression des espaces internes."""
        assert normalize_parcelle_name("côté est") == "cotéest".replace("é", "e")

    def test_mixed(self) -> None:
        """CA11 — Combinaison : casse + accents + tirets."""
        assert normalize_parcelle_name("  Côté-Est  ") == "coteest"

    def test_simple_word(self) -> None:
        """CA11 — Mot simple sans transformation."""
        assert normalize_parcelle_name("serre") == "serre"


# ──────────────────────────────────────────────────────────────────────────────
# CA12 — levenshtein_distance
# ──────────────────────────────────────────────────────────────────────────────

class TestLevenshteinDistance:
    def test_identical_strings(self) -> None:
        """Distance entre deux chaînes identiques = 0."""
        assert levenshtein_distance("nord", "nord") == 0

    def test_empty_strings(self) -> None:
        """Distance entre deux chaînes vides = 0."""
        assert levenshtein_distance("", "") == 0

    def test_one_empty(self) -> None:
        """Distance d'une chaîne vide à 'abc' = len(abc)."""
        assert levenshtein_distance("", "abc") == 3
        assert levenshtein_distance("abc", "") == 3

    def test_single_substitution(self) -> None:
        """1 substitution → distance = 1."""
        assert levenshtein_distance("nord", "nard") == 1

    def test_single_insertion(self) -> None:
        """1 insertion → distance = 1."""
        assert levenshtein_distance("nor", "nord") == 1

    def test_single_deletion(self) -> None:
        """1 suppression → distance = 1."""
        assert levenshtein_distance("nords", "nord") == 1

    def test_distance_2(self) -> None:
        """Distance de 2 → seuil de variante proche (CA12)."""
        assert levenshtein_distance("nrd", "nord") == 1
        assert levenshtein_distance("sud", "sude") == 1
        # 'nor' → 'est' = 3 (au-delà du seuil)
        assert levenshtein_distance("nor", "est") == 3

    def test_completely_different(self) -> None:
        """Chaînes complètement différentes → grande distance."""
        assert levenshtein_distance("abc", "xyz") == 3


# ──────────────────────────────────────────────────────────────────────────────
# CA10, CA12 — find_doublon
# ──────────────────────────────────────────────────────────────────────────────

class TestFindDoublon:
    def test_exact_match(self, db_with_parcelles) -> None:
        """CA10 — Doublon exact trouvé."""
        exact, proche = find_doublon(db_with_parcelles, "nord")
        assert exact is not None
        assert exact.nom_normalise == "nord"
        assert proche is None

    def test_no_match(self, db_with_parcelles) -> None:
        """Aucun doublon → (None, None)."""
        exact, proche = find_doublon(db_with_parcelles, "zzzparcelle")
        assert exact is None
        assert proche is None

    def test_proche_match(self, db_with_parcelles) -> None:
        """CA12 — Variante proche (Levenshtein ≤ 2) détectée."""
        # "nrd" est à distance 1 de "nord"
        exact, proche = find_doublon(db_with_parcelles, "nrd")
        assert exact is None
        assert proche is not None
        assert proche.nom_normalise == "nord"

    def test_exact_takes_priority(self, db_with_parcelles) -> None:
        """L'exact match prend priorité, proche non retourné si exact trouvé."""
        exact, proche = find_doublon(db_with_parcelles, "sud")
        assert exact is not None
        assert exact.nom_normalise == "sud"
        assert proche is None


# ──────────────────────────────────────────────────────────────────────────────
# CA1-CA7 — calcul_occupation_parcelles
# ──────────────────────────────────────────────────────────────────────────────

class TestCalculOccupationParcelles:
    def test_cultures_actives_groupees(self, db_with_cultures) -> None:
        """CA1 — Les cultures avec stock > 0 sont incluses."""
        result = calcul_occupation_parcelles(db_with_cultures)
        # NORD doit avoir salade et tomate
        nord = result.get("NORD", [])
        cultures_nord = {c["culture"] for c in nord}
        assert "tomate" in cultures_nord
        assert "salade" in cultures_nord

    def test_cultures_sans_parcelle(self, db_with_cultures) -> None:
        """CA7 — Cultures sans parcelle groupées sous clé None."""
        result = calcul_occupation_parcelles(db_with_cultures)
        sans_parcelle = result.get(None, [])
        assert len(sans_parcelle) > 0
        cultures = {c["culture"] for c in sans_parcelle}
        assert "basilic" in cultures

    def test_age_jours_calcule(self, db_with_cultures) -> None:
        """CA2 — L'âge J+ est calculé depuis la date de plantation."""
        result = calcul_occupation_parcelles(db_with_cultures)
        nord = result.get("NORD", [])
        tomate = next((c for c in nord if c["culture"] == "tomate"), None)
        assert tomate is not None
        assert 26 <= tomate["age_jours"] <= 28  # tolérance ±1j

    def test_age_jours_salade(self, db_with_cultures) -> None:
        """CA2 — Âge de la salade (50 jours)."""
        result = calcul_occupation_parcelles(db_with_cultures)
        nord = result.get("NORD", [])
        salade = next((c for c in nord if c["culture"] == "salade"), None)
        assert salade is not None
        assert 49 <= salade["age_jours"] <= 51

    def test_empty_when_no_plantations(self, test_db) -> None:
        """Retourne dict vide si aucune plantation."""
        result = calcul_occupation_parcelles(test_db)
        assert result == {}

    def test_nb_plants(self, db_with_cultures) -> None:
        """CA1 — Le nb_plants est correctement calculé."""
        result = calcul_occupation_parcelles(db_with_cultures)
        nord = result.get("NORD", [])
        tomate = next((c for c in nord if c["culture"] == "tomate"), None)
        assert tomate is not None
        assert tomate["nb_plants"] == 3.0


# ──────────────────────────────────────────────────────────────────────────────
# CA3 — Seuils alerte
# ──────────────────────────────────────────────────────────────────────────────

class TestAlerteRecolte:
    def test_vegetatif_sous_seuil(self) -> None:
        """CA3 — Végétatif < 45j → pas d'alerte."""
        assert _alerte_recolte("végétatif", 44) is False

    def test_vegetatif_au_seuil(self) -> None:
        """CA3 — Végétatif = 45j → alerte."""
        assert _alerte_recolte("végétatif", 45) is True

    def test_vegetatif_depasse_seuil(self) -> None:
        """CA3 — Végétatif > 45j → alerte."""
        assert _alerte_recolte("végétatif", 50) is True

    def test_reproducteur_sous_seuil(self) -> None:
        """CA3 — Reproducteur < 90j → pas d'alerte."""
        assert _alerte_recolte("reproducteur", 89) is False

    def test_reproducteur_au_seuil(self) -> None:
        """CA3 — Reproducteur = 90j → alerte."""
        assert _alerte_recolte("reproducteur", 90) is True

    def test_sans_type_organe(self) -> None:
        """CA3 — Type organe None → pas d'alerte."""
        assert _alerte_recolte(None, 200) is False

    def test_seuils_values(self) -> None:
        """CA3 — Vérifier les valeurs de SEUIL_ALERTE."""
        assert SEUIL_ALERTE["végétatif"] == 45
        assert SEUIL_ALERTE["reproducteur"] == 90

    def test_alerte_salade_50j(self, db_with_cultures) -> None:
        """CA3 — Salade plantée à J+50 déclenche alerte (végétatif ≥ 45j)."""
        result = calcul_occupation_parcelles(db_with_cultures)
        nord = result.get("NORD", [])
        salade = next((c for c in nord if c["culture"] == "salade"), None)
        assert salade is not None
        assert _alerte_recolte(salade["type_organe"], salade["age_jours"]) is True

    def test_pas_alerte_tomate_27j(self, db_with_cultures) -> None:
        """CA3 — Tomate plantée à J+27 ne déclenche pas d'alerte (reproducteur < 90j)."""
        result = calcul_occupation_parcelles(db_with_cultures)
        nord = result.get("NORD", [])
        tomate = next((c for c in nord if c["culture"] == "tomate"), None)
        assert tomate is not None
        assert _alerte_recolte(tomate["type_organe"], tomate["age_jours"]) is False


# ──────────────────────────────────────────────────────────────────────────────
# cmd_plan — mocks Telegram
# ──────────────────────────────────────────────────────────────────────────────

def _make_update_ctx(args=None):
    """Construit un (update, ctx) mockés pour les tests de commandes."""
    update = MagicMock()
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    ctx = MagicMock()
    ctx.args = args or []
    ctx.user_data = {}
    return update, ctx


class TestCmdPlan:
    @pytest.mark.asyncio
    async def test_cmd_plan_global_no_cultures(self) -> None:
        """cmd_plan sans arg et sans cultures → aucune erreur, message envoyé."""
        update, ctx = _make_update_ctx(args=[])
        with (
            patch("bot.SessionLocal") as mock_sl,
            patch("bot.calcul_occupation_parcelles", return_value={}),
            patch("bot.get_all_parcelles", return_value=[]),
            patch("bot.send_voice_reply", new_callable=AsyncMock),
        ):
            mock_db = MagicMock()
            mock_sl.return_value = mock_db

            from bot import cmd_plan
            await cmd_plan(update, ctx)

        update.message.reply_text.assert_called_once()
        texte_envoye = update.message.reply_text.call_args[0][0]
        assert "Plan d'occupation" in texte_envoye

    @pytest.mark.asyncio
    async def test_cmd_plan_parcelle_inconnue(self) -> None:
        """CA5 — cmd_plan avec parcelle inconnue → message 'Aucune culture active'."""
        update, ctx = _make_update_ctx(args=["zzz"])
        with (
            patch("bot.SessionLocal") as mock_sl,
            patch("bot.calcul_occupation_parcelles", return_value={}),
            patch("bot.get_all_parcelles", return_value=[]),
            patch("bot.send_voice_reply", new_callable=AsyncMock),
        ):
            mock_db = MagicMock()
            mock_sl.return_value = mock_db

            from bot import cmd_plan
            await cmd_plan(update, ctx)

        texte_envoye = update.message.reply_text.call_args[0][0]
        assert "Aucune culture active" in texte_envoye

    @pytest.mark.asyncio
    async def test_cmd_plan_parcelle_avec_cultures(self) -> None:
        """CA5 — cmd_plan avec parcelle connue affiche les cultures."""
        update, ctx = _make_update_ctx(args=["nord"])
        cultures = [{
            "culture": "tomate",
            "variete": "Cœur de Bœuf",
            "nb_plants": 3.0,
            "unite": "plants",
            "type_organe": "reproducteur",
            "date_plantation": datetime.now() - timedelta(days=27),
            "age_jours": 27,
        }]
        with (
            patch("bot.SessionLocal") as mock_sl,
            patch("bot.calcul_occupation_parcelles", return_value={"NORD": cultures}),
            patch("bot.get_all_parcelles", return_value=[]),
            patch("bot.send_voice_reply", new_callable=AsyncMock),
        ):
            mock_db = MagicMock()
            mock_sl.return_value = mock_db

            from bot import cmd_plan
            await cmd_plan(update, ctx)

        texte_envoye = update.message.reply_text.call_args[0][0]
        assert "NORD" in texte_envoye
        assert "tomate" in texte_envoye
        assert "J+27" in texte_envoye

    @pytest.mark.asyncio
    async def test_cmd_plan_hint_pied_message(self) -> None:
        """CA6 — Le hint est présent en pied de message vue globale."""
        update, ctx = _make_update_ctx(args=[])
        with (
            patch("bot.SessionLocal") as mock_sl,
            patch("bot.calcul_occupation_parcelles", return_value={}),
            patch("bot.get_all_parcelles", return_value=[]),
            patch("bot.send_voice_reply", new_callable=AsyncMock),
        ):
            mock_db = MagicMock()
            mock_sl.return_value = mock_db

            from bot import cmd_plan
            await cmd_plan(update, ctx)

        texte_envoye = update.message.reply_text.call_args[0][0]
        assert "/plan [nom parcelle]" in texte_envoye


# ──────────────────────────────────────────────────────────────────────────────
# cmd_parcelle — mocks Telegram
# ──────────────────────────────────────────────────────────────────────────────

class TestCmdParcelle:
    @pytest.mark.asyncio
    async def test_parcelle_ajouter_sans_nom(self) -> None:
        """CA13 — /parcelle ajouter sans nom → message d'erreur."""
        update, ctx = _make_update_ctx(args=["ajouter"])
        with patch("bot.SessionLocal") as mock_sl:
            mock_db = MagicMock()
            mock_sl.return_value = mock_db

            from bot import cmd_parcelle
            await cmd_parcelle(update, ctx)

        texte = update.message.reply_text.call_args[0][0]
        assert "Précisez" in texte

    @pytest.mark.asyncio
    async def test_parcelle_doublon_exact(self) -> None:
        """CA10 — Doublon exact → refus avec message ❌."""
        update, ctx = _make_update_ctx(args=["ajouter", "nord"])
        parcelle_existante = Parcelle(nom="Nord", nom_normalise="nord", ordre=1, actif=True)

        with (
            patch("bot.SessionLocal") as mock_sl,
            patch("bot.normalize_parcelle_name", return_value="nord"),
            patch("bot.find_doublon", return_value=(parcelle_existante, None)),
        ):
            mock_db = MagicMock()
            mock_sl.return_value = mock_db

            from bot import cmd_parcelle
            await cmd_parcelle(update, ctx)

        texte = update.message.reply_text.call_args[0][0]
        assert "❌" in texte
        assert "NORD" in texte.upper()

    @pytest.mark.asyncio
    async def test_parcelle_variante_proche(self) -> None:
        """CA12 — Variante proche → demande confirmation."""
        update, ctx = _make_update_ctx(args=["ajouter", "nrd"])
        parcelle_proche = Parcelle(nom="Nord", nom_normalise="nord", ordre=1, actif=True)

        with (
            patch("bot.SessionLocal") as mock_sl,
            patch("bot.normalize_parcelle_name", return_value="nrd"),
            patch("bot.find_doublon", return_value=(None, parcelle_proche)),
        ):
            mock_db = MagicMock()
            mock_sl.return_value = mock_db

            from bot import cmd_parcelle
            await cmd_parcelle(update, ctx)

        texte = update.message.reply_text.call_args[0][0]
        assert "⚠️" in texte
        assert "similaire" in texte.lower()
        assert ctx.user_data.get('mode') == 'parcelle_confirm'

    @pytest.mark.asyncio
    async def test_parcelle_ajouter_nouveau(self) -> None:
        """CA13 — Nouvelle parcelle sans doublon → affiche récap + demande confirmation."""
        update, ctx = _make_update_ctx(args=["ajouter", "ouest"])

        with (
            patch("bot.SessionLocal") as mock_sl,
            patch("bot.normalize_parcelle_name", return_value="ouest"),
            patch("bot.find_doublon", return_value=(None, None)),
            patch("bot.get_all_parcelles", return_value=[]),
        ):
            mock_db = MagicMock()
            mock_sl.return_value = mock_db

            from bot import cmd_parcelle
            await cmd_parcelle(update, ctx)

        texte = update.message.reply_text.call_args[0][0]
        assert "OUEST" in texte.upper()
        assert ctx.user_data.get('mode') == 'parcelle_confirm'
        assert ctx.user_data.get('parcelle_pending', {}).get('nom') == 'ouest'

    @pytest.mark.asyncio
    async def test_parcelle_usage_sans_args(self) -> None:
        """Aucun argument → message d'usage affiché."""
        update, ctx = _make_update_ctx(args=[])
        from bot import cmd_parcelle
        await cmd_parcelle(update, ctx)
        texte = update.message.reply_text.call_args[0][0]
        assert "Usage" in texte
