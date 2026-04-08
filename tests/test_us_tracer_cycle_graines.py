"""
tests/test_us_tracer_cycle_graines.py
--------------------------------------
[US Tracer le cycle graines]

CA1 : normalize_action("recolte graines") → "recolte_graines" (pas "recolte")
CA2 : Evenement recolte_graines avec culture, variété, quantité(g) peut être créé et sauvegardé
CA3 : Evenement semis avec origine_graines_id peut référencer une recolte_graines
CA4 : build_reduced_context inclut origine_graines_id dans les données sérialisées
CA5 : calcul_stock_cultures n'inclut PAS les recolte_graines dans le stock alimentaire
"""
from __future__ import annotations

import inspect
import json
import pytest
from unittest.mock import MagicMock, patch

from utils.actions import ACTION_MAP, normalize_action
from database.models import Evenement
from bot import _build_recap


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_telegram_update():
    """Simule un objet Update Telegram minimal."""
    update = MagicMock()
    update.effective_user.id = 123456
    update.effective_user.first_name = "Testeur"
    update.message.text = ""
    return update


@pytest.fixture
def mock_groq_response():
    """Simule une réponse Groq valide pour parse_commande."""
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps({
        "action": "recolte_graines",
        "culture": "tomate",
        "variete": "coeur de boeuf",
        "quantite": 15,
        "unite": "g",
        "parcelle": None,
        "date": None,
        "commentaire": None,
        "nb_graines_semees": None,
        "nb_plants_godets": None,
        "origine_graines_id": None,
    })
    mock_client.chat.completions.create.return_value.choices = [mock_choice]
    return mock_client


@pytest.fixture
def mock_whisper_transcription():
    """Simule une transcription Whisper pour un message vocal."""
    return "récolté graines tomates cœur de bœuf 15 grammes"


@pytest.fixture
def payload_recolte_graines() -> dict:
    """Payload parsé typique pour une récolte de graines (15 g, tomate cœur de bœuf)."""
    return {
        "action": "recolte_graines",
        "culture": "tomate",
        "variete": "coeur de boeuf",
        "quantite": 15,
        "unite": "g",
        "parcelle": None,
        "date": None,
        "commentaire": None,
        "duree_minutes": None,
        "rang": None,
        "traitement": None,
        "nb_graines_semees": None,
        "nb_plants_godets": None,
        "origine_graines_id": None,
    }


@pytest.fixture
def payload_semis_avec_origine() -> dict:
    """Payload parsé pour un semis référençant une recolte_graines (id=42)."""
    return {
        "action": "semis",
        "culture": "tomate",
        "variete": "coeur de boeuf",
        "quantite": None,
        "unite": "graines",
        "parcelle": None,
        "date": None,
        "commentaire": "graines de l'an dernier",
        "nb_graines_semees": None,
        "nb_plants_godets": None,
        "origine_graines_id": 42,
    }


# ──────────────────────────────────────────────────────────────────────────────
# CA1 — normalize_action("recolte graines") → "recolte_graines" (pas "recolte")
# ──────────────────────────────────────────────────────────────────────────────

class TestCA1NormalizeActionRecolteGraines:

    def test_us_graines_ca1_normalize_action_happy_path(self) -> None:
        """CA1 — Happy path : 'recolte graines' normalisé → 'recolte_graines'."""
        assert normalize_action("recolte graines") == "recolte_graines"

    def test_us_graines_ca1_normalize_action_not_recolte(self) -> None:
        """CA1 — 'recolte graines' ne doit pas retourner 'recolte'."""
        result = normalize_action("recolte graines")
        assert result != "recolte"

    def test_us_graines_ca1_recolte_graines_in_action_map(self) -> None:
        """CA1 — La clé 'recolte_graines' est bien dans ACTION_MAP."""
        assert "recolte_graines" in ACTION_MAP

    def test_us_graines_ca1_action_map_ordre_priorite(self) -> None:
        """CA1 — 'recolte_graines' précède 'recolte' dans ACTION_MAP (priorité dict)."""
        keys = list(ACTION_MAP.keys())
        assert keys.index("recolte_graines") < keys.index("recolte")

    def test_us_graines_ca1_synonyme_recolter_graines(self) -> None:
        """CA1 — 'recolter graines' → 'recolte_graines' (infinitif vocal)."""
        assert normalize_action("recolter graines") == "recolte_graines"

    def test_us_graines_ca1_synonyme_graines_recoltees(self) -> None:
        """CA1 — 'graines recoltees' → 'recolte_graines' (participe passé)."""
        assert normalize_action("graines recoltees") == "recolte_graines"

    def test_us_graines_ca1_synonyme_recolte_semences(self) -> None:
        """CA1 — 'recolte semences' → 'recolte_graines' (synonyme semences)."""
        assert normalize_action("recolte semences") == "recolte_graines"

    def test_us_graines_ca1_synonyme_semences_recoltees(self) -> None:
        """CA1 — 'semences recoltees' → 'recolte_graines' (vocal variante)."""
        assert normalize_action("semences recoltees") == "recolte_graines"

    def test_us_graines_ca1_synonyme_ramasse_graines(self) -> None:
        """CA1 — 'ramasse graines' → 'recolte_graines' (langage naturel)."""
        assert normalize_action("ramasse graines") == "recolte_graines"

    def test_us_graines_ca1_synonyme_cueilli_graines(self) -> None:
        """CA1 — 'cueilli graines' → 'recolte_graines'."""
        assert normalize_action("cueilli graines") == "recolte_graines"

    def test_us_graines_ca1_canonical_direct(self) -> None:
        """CA1 — La chaîne canonique 'recolte_graines' est renvoyée telle quelle."""
        assert normalize_action("recolte_graines") == "recolte_graines"

    def test_us_graines_ca1_recolte_simple_reste_recolte(self) -> None:
        """CA1 — Edge case : 'recolte' seul → 'recolte' (pas de confusion inverse)."""
        assert normalize_action("recolte") == "recolte"

    def test_us_graines_ca1_action_none_retourne_none(self) -> None:
        """CA1 — Edge case : None en entrée → None en sortie."""
        assert normalize_action(None) is None

    def test_us_graines_ca1_action_vide_retourne_none(self) -> None:
        """CA1 — Edge case : chaîne vide → None."""
        assert normalize_action("") is None

    def test_us_graines_ca1_action_map_a_plusieurs_synonymes(self) -> None:
        """CA1 — recolte_graines possède au moins 3 synonymes pour couvrir vocal et texte."""
        assert len(ACTION_MAP["recolte_graines"]) >= 3


# ──────────────────────────────────────────────────────────────────────────────
# CA2 — Evenement recolte_graines créé et sauvegardé (culture, variété, qté en g)
# ──────────────────────────────────────────────────────────────────────────────

class TestCA2EvenementRecolteGraines:

    def test_us_graines_ca2_instantiation_happy_path(self) -> None:
        """CA2 — Happy path : Evenement instancié avec type_action='recolte_graines'."""
        ev = Evenement(
            type_action="recolte_graines",
            culture="tomate",
            variete="coeur de boeuf",
            quantite=15.0,
            unite="g",
        )
        assert ev.type_action == "recolte_graines"
        assert ev.culture == "tomate"
        assert ev.variete == "coeur de boeuf"
        assert ev.quantite == 15.0
        assert ev.unite == "g"

    def test_us_graines_ca2_persiste_en_db(self, test_db) -> None:
        """CA2 — L'événement recolte_graines est bien persisté en base SQLite."""
        ev = Evenement(
            type_action="recolte_graines",
            culture="tomate",
            variete="coeur de boeuf",
            quantite=15.0,
            unite="g",
        )
        test_db.add(ev)
        test_db.commit()
        test_db.refresh(ev)

        assert ev.id is not None
        found = test_db.query(Evenement).filter(
            Evenement.type_action == "recolte_graines"
        ).first()
        assert found is not None
        assert found.culture == "tomate"
        assert found.quantite == 15.0
        assert found.unite == "g"

    def test_us_graines_ca2_colonne_origine_graines_id_existe(self) -> None:
        """CA2 — La colonne origine_graines_id est déclarée sur Evenement."""
        colonnes = {c.key for c in Evenement.__table__.columns}
        assert "origine_graines_id" in colonnes

    def test_us_graines_ca2_colonne_origine_graines_id_nullable(self) -> None:
        """CA2 — origine_graines_id est nullable (champ optionnel)."""
        assert Evenement.__table__.c["origine_graines_id"].nullable is True

    def test_us_graines_ca2_date_optionnelle(self) -> None:
        """CA2 — Edge case : date optionnelle → None par défaut."""
        ev = Evenement(
            type_action="recolte_graines",
            culture="carotte",
            quantite=5.0,
            unite="g",
        )
        assert ev.date is None

    def test_us_graines_ca2_variete_optionnelle(self) -> None:
        """CA2 — Edge case : variété optionnelle → None accepté."""
        ev = Evenement(
            type_action="recolte_graines",
            culture="haricot",
            quantite=20.0,
            unite="g",
            variete=None,
        )
        assert ev.variete is None

    def test_us_graines_ca2_quantite_zero(self) -> None:
        """CA2 — Edge case : quantité 0 g est une valeur limite acceptée."""
        ev = Evenement(
            type_action="recolte_graines",
            culture="tomate",
            quantite=0.0,
            unite="g",
        )
        assert ev.quantite == 0.0

    def test_us_graines_ca2_quantite_grande(self) -> None:
        """CA2 — Edge case : grande quantité (ex: 500 g) est acceptée."""
        ev = Evenement(
            type_action="recolte_graines",
            culture="tournesol",
            quantite=500.0,
            unite="g",
        )
        assert ev.quantite == 500.0

    def test_us_graines_ca2_parse_prompt_contient_recolte_graines(self) -> None:
        """CA2 — PARSE_PROMPT contient l'action 'recolte_graines' dans le schéma."""
        from llm.groq_client import PARSE_PROMPT
        assert "recolte_graines" in PARSE_PROMPT

    def test_us_graines_ca2_parse_prompt_exemple_tomate_coeur_de_boeuf(self) -> None:
        """CA2 — PARSE_PROMPT contient l'exemple tomate cœur de bœuf (gherkin)."""
        from llm.groq_client import PARSE_PROMPT
        prompt_lower = PARSE_PROMPT.lower()
        assert "coeur de boeuf" in prompt_lower or "cœur de bœuf" in prompt_lower

    def test_us_graines_ca2_parse_prompt_exemple_15g(self) -> None:
        """CA2 — PARSE_PROMPT contient l'exemple avec 15 g de graines."""
        from llm.groq_client import PARSE_PROMPT
        assert "15" in PARSE_PROMPT

    def test_us_graines_ca2_build_recap_mentionne_recolte_graines(
        self, payload_recolte_graines: dict
    ) -> None:
        """CA2 — _build_recap pour recolte_graines mentionne 'recolte_graines' ou 'graines'."""
        recap = _build_recap(payload_recolte_graines, event_id=7)
        assert "recolte_graines" in recap.lower() or "graines" in recap.lower()

    def test_us_graines_ca2_build_recap_affiche_culture(
        self, payload_recolte_graines: dict
    ) -> None:
        """CA2 — _build_recap pour recolte_graines affiche la culture."""
        recap = _build_recap(payload_recolte_graines, event_id=7)
        assert "tomate" in recap.lower()


# ──────────────────────────────────────────────────────────────────────────────
# CA3 — Evenement semis avec origine_graines_id référençant une recolte_graines
# ──────────────────────────────────────────────────────────────────────────────

class TestCA3OrigineGrainesId:

    def test_us_graines_ca3_semis_avec_origine_happy_path(self, test_db) -> None:
        """CA3 — Happy path : semis référençant une recolte_graines persistée en base."""
        source = Evenement(
            type_action="recolte_graines",
            culture="tomate",
            variete="coeur de boeuf",
            quantite=15.0,
            unite="g",
        )
        test_db.add(source)
        test_db.commit()
        test_db.refresh(source)

        semis = Evenement(
            type_action="semis",
            culture="tomate",
            variete="coeur de boeuf",
            origine_graines_id=source.id,
        )
        test_db.add(semis)
        test_db.commit()
        test_db.refresh(semis)

        assert semis.origine_graines_id == source.id

    def test_us_graines_ca3_semis_peut_retrouver_source_par_id(self, test_db) -> None:
        """CA3 — Depuis un semis, on peut retrouver la recolte_graines source via l'id."""
        source = Evenement(
            type_action="recolte_graines",
            culture="poivron",
            variete="rouge",
            quantite=8.0,
            unite="g",
        )
        test_db.add(source)
        test_db.commit()
        test_db.refresh(source)

        semis = Evenement(
            type_action="semis",
            culture="poivron",
            origine_graines_id=source.id,
        )
        test_db.add(semis)
        test_db.commit()
        test_db.refresh(semis)

        source_retrouve = test_db.query(Evenement).filter(
            Evenement.id == semis.origine_graines_id
        ).first()
        assert source_retrouve is not None
        assert source_retrouve.type_action == "recolte_graines"
        assert source_retrouve.culture == "poivron"

    def test_us_graines_ca3_semis_sans_origine_none(self) -> None:
        """CA3 — Edge case : semis sans lien → origine_graines_id None par défaut."""
        ev = Evenement(type_action="semis", culture="courgette")
        assert ev.origine_graines_id is None

    def test_us_graines_ca3_recolte_graines_origine_none(
        self, payload_recolte_graines: dict
    ) -> None:
        """CA3 — Une recolte_graines elle-même n'a pas d'origine_graines_id."""
        ev = Evenement(
            type_action=payload_recolte_graines["action"],
            culture=payload_recolte_graines["culture"],
            origine_graines_id=payload_recolte_graines["origine_graines_id"],
        )
        assert ev.origine_graines_id is None

    def test_us_graines_ca3_payload_semis_origine_mappee(
        self, payload_semis_avec_origine: dict
    ) -> None:
        """CA3 — Le payload parsé avec origine_graines_id=42 instancie correctement."""
        ev = Evenement(
            type_action=payload_semis_avec_origine["action"],
            culture=payload_semis_avec_origine["culture"],
            origine_graines_id=payload_semis_avec_origine["origine_graines_id"],
        )
        assert ev.origine_graines_id == 42

    def test_us_graines_ca3_parse_prompt_contient_origine_graines_id(self) -> None:
        """CA3 — PARSE_PROMPT définit le champ origine_graines_id dans le schéma JSON."""
        from llm.groq_client import PARSE_PROMPT
        assert "origine_graines_id" in PARSE_PROMPT

    def test_us_graines_ca3_parse_prompt_exemple_id_42(self) -> None:
        """CA3 — PARSE_PROMPT inclut un exemple de semis avec origine_graines_id=42."""
        from llm.groq_client import PARSE_PROMPT
        assert "42" in PARSE_PROMPT

    def test_us_graines_ca3_fk_ondelete_set_null(self) -> None:
        """CA3 — FK origine_graines_id a bien ondelete='SET NULL' (intégrité référentielle)."""
        col = Evenement.__table__.c["origine_graines_id"]
        fks = list(col.foreign_keys)
        assert len(fks) == 1
        assert fks[0].ondelete.upper() == "SET NULL"

    def test_us_graines_ca3_origine_graines_id_est_integer(self) -> None:
        """CA3 — La colonne origine_graines_id est de type Integer (FK compatible)."""
        from sqlalchemy import Integer as SAInteger
        col = Evenement.__table__.c["origine_graines_id"]
        assert isinstance(col.type, SAInteger)


# ──────────────────────────────────────────────────────────────────────────────
# CA4 — build_reduced_context inclut origine_graines_id dans les données
# ──────────────────────────────────────────────────────────────────────────────

class TestCA4BuildReducedContext:

    def test_us_graines_ca4_origine_graines_id_dans_contexte(self, test_db) -> None:
        """CA4 — Happy path : build_reduced_context sérialise origine_graines_id."""
        from utils.ia_orchestrator import build_reduced_context

        source = Evenement(
            type_action="recolte_graines",
            culture="tomate",
            variete="coeur de boeuf",
            quantite=15.0,
            unite="g",
        )
        test_db.add(source)
        test_db.commit()
        test_db.refresh(source)

        semis = Evenement(
            type_action="semis",
            culture="tomate",
            variete="coeur de boeuf",
            origine_graines_id=source.id,
        )
        test_db.add(semis)
        test_db.commit()
        test_db.refresh(semis)

        contexte = build_reduced_context([source, semis])
        assert "origine_graines_id" in contexte
        assert str(source.id) in contexte

    def test_us_graines_ca4_recolte_graines_dans_contexte_json(self, test_db) -> None:
        """CA4 — Le contexte JSON contient les événements recolte_graines."""
        from utils.ia_orchestrator import build_reduced_context

        ev = Evenement(
            type_action="recolte_graines",
            culture="poivron",
            variete="rouge",
            quantite=8.0,
            unite="g",
        )
        test_db.add(ev)
        test_db.commit()
        test_db.refresh(ev)

        contexte = build_reduced_context([ev])
        assert "recolte_graines" in contexte
        assert "poivron" in contexte

    def test_us_graines_ca4_contexte_vide_si_pas_evenements(self) -> None:
        """CA4 — Edge case : aucun événement → contexte retourne '[]'."""
        from utils.ia_orchestrator import build_reduced_context

        contexte = build_reduced_context([])
        assert contexte == "[]"

    def test_us_graines_ca4_contexte_sans_recolte_graines(self, test_db) -> None:
        """CA4 — Edge case : pas de recolte_graines en base → contexte sans généalogie."""
        from utils.ia_orchestrator import build_reduced_context

        ev = Evenement(type_action="arrosage", culture="courgette")
        test_db.add(ev)
        test_db.commit()
        test_db.refresh(ev)

        contexte = build_reduced_context([ev])
        assert "recolte_graines" not in contexte

    def test_us_graines_ca4_contexte_est_json_valide(self, test_db) -> None:
        """CA4 — build_reduced_context retourne du JSON valide parseable."""
        from utils.ia_orchestrator import build_reduced_context

        ev = Evenement(
            type_action="recolte_graines",
            culture="tomate",
            quantite=10.0,
            unite="g",
        )
        test_db.add(ev)
        test_db.commit()
        test_db.refresh(ev)

        contexte = build_reduced_context([ev])
        parsed = json.loads(contexte)
        assert isinstance(parsed, list)
        assert len(parsed) == 1
        assert "origine_graines_id" in parsed[0]

    def test_us_graines_ca4_groq_erreur_propagee(self) -> None:
        """CA4 — Erreur réseau Groq lors d'une question généalogie → exception propagée."""
        from llm.groq_client import repondre_question

        contexte = '[{"id":1,"action":"recolte_graines","culture":"tomate"}]'
        with patch("llm.groq_client._client") as mock_client:
            mock_client.chat.completions.create.side_effect = RuntimeError("Groq unavailable")
            with pytest.raises(RuntimeError, match="Groq unavailable"):
                repondre_question("D'où viennent mes graines ?", contexte)

    def test_us_graines_ca4_groq_appele_avec_contexte_genealogie(self) -> None:
        """CA4 — repondre_question est appelée avec le contexte incluant origine_graines_id."""
        from llm.groq_client import repondre_question

        contexte = json.dumps([
            {
                "action": "recolte_graines",
                "culture": "tomate",
                "variete": "coeur de boeuf",
                "quantite": 15,
                "unite": "g",
                "origine_graines_id": None,
            },
            {
                "action": "semis",
                "culture": "tomate",
                "variete": "coeur de boeuf",
                "origine_graines_id": 1,
            },
        ])
        question = "D'où viennent les graines de cœur de bœuf ?"

        with patch("llm.groq_client._client") as mock_client:
            mock_choice = MagicMock()
            mock_choice.message.content = (
                "Vos graines de cœur de bœuf proviennent de la récolte #1."
            )
            mock_client.chat.completions.create.return_value.choices = [mock_choice]

            reponse = repondre_question(question, contexte)

        assert mock_client.chat.completions.create.called
        assert isinstance(reponse, str)
        assert len(reponse) > 0

    def test_us_graines_ca4_contexte_tronque_a_50_elements(self) -> None:
        """CA4 — build_reduced_context tronque à 50 éléments max (limite token LLM)."""
        from utils.ia_orchestrator import build_reduced_context

        events = [
            Evenement(
                type_action="recolte_graines",
                culture=f"culture_{i}",
                quantite=float(i),
                unite="g",
            )
            for i in range(60)
        ]

        contexte = build_reduced_context(events)
        parsed = json.loads(contexte)
        assert len(parsed) <= 50


# ──────────────────────────────────────────────────────────────────────────────
# CA5 — calcul_stock_cultures n'inclut PAS les recolte_graines dans le stock
# ──────────────────────────────────────────────────────────────────────────────

class TestCA5RecolteGrainesExclueStockAlimentaire:

    def test_us_graines_ca5_recolte_graines_exclue_du_stock(self, test_db) -> None:
        """CA5 — Happy path : recolte_graines ne modifie pas le stock de récolte alimentaire."""
        from utils.stock import calcul_stock_cultures

        test_db.add(Evenement(
            type_action="plantation",
            culture="tomate",
            quantite=10.0,
            unite="plants",
            rang=1,
        ))
        test_db.add(Evenement(
            type_action="recolte_graines",
            culture="tomate",
            variete="coeur de boeuf",
            quantite=15.0,
            unite="g",
        ))
        test_db.commit()

        stock = calcul_stock_cultures(test_db)
        assert "tomate" in stock
        assert stock["tomate"].nb_recoltes == 0
        assert stock["tomate"].recoltes_total == 0.0

    def test_us_graines_ca5_recolte_alimentaire_comptabilisee(self, test_db) -> None:
        """CA5 — Contrôle : une 'recolte' alimentaire est bien comptabilisée (pas exclue)."""
        from utils.stock import calcul_stock_cultures

        test_db.add(Evenement(
            type_action="plantation",
            culture="courgette",
            quantite=3.0,
            unite="plants",
            rang=1,
        ))
        test_db.add(Evenement(
            type_action="recolte",
            culture="courgette",
            quantite=2.0,
            unite="kg",
        ))
        test_db.commit()

        stock = calcul_stock_cultures(test_db)
        assert "courgette" in stock
        assert stock["courgette"].recoltes_total == 2.0
        assert stock["courgette"].nb_recoltes == 1

    def test_us_graines_ca5_recolte_graines_et_recolte_meme_culture(self, test_db) -> None:
        """CA5 — recolte_graines n'est pas additionnée à la recolte alimentaire pour la même culture."""
        from utils.stock import calcul_stock_cultures

        test_db.add(Evenement(
            type_action="plantation",
            culture="tomate",
            quantite=5.0,
            unite="plants",
            rang=1,
        ))
        test_db.add(Evenement(
            type_action="recolte",
            culture="tomate",
            quantite=3.0,
            unite="kg",
        ))
        test_db.add(Evenement(
            type_action="recolte_graines",
            culture="tomate",
            quantite=10.0,
            unite="g",
        ))
        test_db.commit()

        stock = calcul_stock_cultures(test_db)
        assert stock["tomate"].recoltes_total == 3.0

    def test_us_graines_ca5_plusieurs_recolte_graines_stock_intact(self, test_db) -> None:
        """CA5 — Plusieurs recolte_graines ne modifient jamais le stock de plants."""
        from utils.stock import calcul_stock_cultures

        test_db.add(Evenement(
            type_action="plantation",
            culture="poivron",
            quantite=4.0,
            unite="plants",
            rang=1,
        ))
        for _ in range(3):
            test_db.add(Evenement(
                type_action="recolte_graines",
                culture="poivron",
                quantite=5.0,
                unite="g",
            ))
        test_db.commit()

        stock = calcul_stock_cultures(test_db)
        assert "poivron" in stock
        assert stock["poivron"].plants_plantes == 4.0
        assert stock["poivron"].recoltes_total == 0.0

    def test_us_graines_ca5_filtre_recolte_dans_source_code(self) -> None:
        """CA5 — Le code source de calcul_stock_cultures filtre exactement sur 'recolte'."""
        from utils import stock as stock_module

        source = inspect.getsource(stock_module.calcul_stock_cultures)
        assert '"recolte"' in source or "'recolte'" in source
        assert 'type_action == "recolte_graines"' not in source
        assert "type_action == 'recolte_graines'" not in source

    def test_us_graines_ca5_aucune_plantation_retourne_dict_vide(self, test_db) -> None:
        """CA5 — Edge case : aucune plantation en base → dict vide retourné."""
        from utils.stock import calcul_stock_cultures

        test_db.add(Evenement(
            type_action="recolte_graines",
            culture="tomate",
            quantite=15.0,
            unite="g",
        ))
        test_db.commit()

        stock = calcul_stock_cultures(test_db)
        assert stock == {}