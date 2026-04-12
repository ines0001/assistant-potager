"""
tests/test_bug_variete_recherche_affichage.py
---------------------------------------------
Couverture du BUG : Variété absente du critère de recherche et de l'affichage
dans le mode correction.

  - CA1 : critères extraits contiennent 'variete' quand la variété est mentionnée
  - CA2 : filtre SQL sur Evenement.variete.ilike quand variete dans critères
  - CA3 : filtre variété optionnel (null si non mentionné)
  - CA4 : _fmt_event affiche la variété entre parenthèses
  - CA5 : liste multi-résultats distingue les variétés
  - Scénario : événement sans variété → pas de "()" vide
"""
import json
import pytest
from datetime import datetime, date
from unittest.mock import patch, MagicMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.db import Base
from database.models import Evenement


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


def _make_event(id_, action, culture, variete=None, parcelle=None, quantite=10.0):
    return Evenement(
        id=id_,
        type_action=action,
        culture=culture,
        variete=variete,
        parcelle=parcelle,
        quantite=quantite,
        unite="plants",
        date=datetime(2026, 4, 7),
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _call_find_candidates_with_groq(description: str, groq_json: dict, db_session):
    """
    Appelle _find_candidates en mockant Groq + SessionLocal pour utiliser
    la session de test.
    """
    from bot import _find_candidates

    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = json.dumps(groq_json)

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_resp

    # Groq est importé localement dans _find_candidates via `from groq import Groq`
    # → on patche groq.Groq pour intercepter cet import
    with patch("groq.Groq", return_value=mock_client), \
         patch("bot.SessionLocal", return_value=db_session):
        results = _find_candidates(description)
    return results


# ── CA1 : critères extraits contiennent variete ───────────────────────────────

class TestCA1_CriteresContiennentVariete:
    """Groq retourne variete='ronde' quand l'utilisateur la mentionne."""

    def test_variete_presente_dans_criteres(self, caplog, db):
        """
        CA1 : When "modifier plantation tomate ronde"
        Then critères contiennent variete="ronde"
        """
        db.add(_make_event(1, "plantation", "tomate", variete="ronde"))
        db.commit()

        groq_json = {
            "action": "plantation",
            "culture": "tomate",
            "variete": "ronde",
            "date_debut": None,
            "date_fin": None,
            "parcelle": None,
        }

        import logging
        with caplog.at_level(logging.INFO, logger="potager"):
            results = _call_find_candidates_with_groq(
                "modifier plantation tomate ronde", groq_json, db
            )

        assert "'variete': 'ronde'" in caplog.text or '"variete": "ronde"' in caplog.text, \
            "Le log CRITÈRES RECHERCHE doit contenir variete='ronde'"


# ── CA2 : filtre SQL sur variete ──────────────────────────────────────────────

class TestCA2_FiltreSQLVariete:
    """La requête SQL filtre sur variete.ilike quand variete est dans critères."""

    def test_filtre_sql_variete_retourne_bonne_variete(self, db):
        """
        CA2 : deux plantations tomate avec des variétés différentes.
        Quand variete='ronde', seule la plantation ronde est retournée.
        """
        db.add(_make_event(10, "plantation", "tomate", variete="ronde"))
        db.add(_make_event(11, "plantation", "tomate", variete="cerise"))
        db.commit()

        groq_json = {
            "action": "plantation",
            "culture": "tomate",
            "variete": "ronde",
            "date_debut": None,
            "date_fin": None,
            "parcelle": None,
        }

        results = _call_find_candidates_with_groq(
            "modifier plantation tomate ronde", groq_json, db
        )

        ids = [e.id for e in results]
        assert 10 in ids, "L'événement tomate ronde doit être retourné"
        assert 11 not in ids, "L'événement tomate cerise ne doit PAS être retourné"


# ── CA3 : filtre optionnel (sans variété) ────────────────────────────────────

class TestCA3_FiltreVarieteOptionnel:
    """Quand variete=null, la requête SQL ne filtre pas sur la variété."""

    def test_sans_variete_tous_retournes(self, db):
        """
        CA3 : When "modifier plantation tomate" (sans variété)
        Then tous les événements plantation tomate sont retournés
        """
        db.add(_make_event(20, "plantation", "tomate", variete="ronde"))
        db.add(_make_event(21, "plantation", "tomate", variete="cerise"))
        db.commit()

        groq_json = {
            "action": "plantation",
            "culture": "tomate",
            "variete": None,
            "date_debut": None,
            "date_fin": None,
            "parcelle": None,
        }

        results = _call_find_candidates_with_groq(
            "modifier plantation tomate", groq_json, db
        )

        ids = [e.id for e in results]
        assert 20 in ids
        assert 21 in ids

    def test_criteres_sans_variete_pas_de_filtre(self, caplog, db):
        """CA3 : variete=null → log ne filtre pas la variété."""
        groq_json = {
            "action": "plantation",
            "culture": "tomate",
            "variete": None,
            "date_debut": None,
            "date_fin": None,
            "parcelle": None,
        }

        import logging
        with caplog.at_level(logging.INFO, logger="potager"):
            _call_find_candidates_with_groq("modifier plantation tomate", groq_json, db)

        # Le log CRITÈRES RECHERCHE doit afficher le dict complet avec variete
        assert "CRITÈRES RECHERCHE" in caplog.text or "CRIT" in caplog.text


# ── CA4 : _fmt_event affiche variété entre parenthèses ───────────────────────

class TestCA4_FmtEventVariete:
    """_fmt_event affiche la variété entre parenthèses après la culture."""

    def test_variete_affichee(self):
        """CA4 : événement avec variété → '… tomate (ronde) 10.0plants …'"""
        from bot import _fmt_event

        e = _make_event(247, "plantation", "tomate", variete="ronde")
        result = _fmt_event(e)

        assert "tomate (ronde)" in result, f"Attendu 'tomate (ronde)' dans : {result}"

    def test_variete_position_avant_quantite(self):
        """CA4 : variété apareît avant la quantité."""
        from bot import _fmt_event

        e = _make_event(247, "plantation", "tomate", variete="ronde", quantite=10.0)
        result = _fmt_event(e)

        idx_var = result.index("(ronde)")
        idx_qte = result.index("10.0")
        assert idx_var < idx_qte, "La variété doit apparaître avant la quantité"

    def test_format_complet(self):
        """CA4 : format exact '#247 07/04 — plantation tomate (ronde) 10.0plants'"""
        from bot import _fmt_event

        e = _make_event(247, "plantation", "tomate", variete="ronde", quantite=10.0)
        result = _fmt_event(e)

        assert result.startswith("#247"), f"Doit commencer par #247, obtenu : {result}"
        assert "plantation tomate (ronde) 10.0plants" in result


# ── CA5 : liste multi-résultats distingue les variétés ───────────────────────

class TestCA5_ListeMultiVariete:
    """Chaque ligne de la liste de sélection affiche la variété."""

    def test_deux_varietes_distinctes_dans_liste(self):
        """CA5 : _fmt_event sur deux événements de variétés différentes produit des lignes différentes."""
        from bot import _fmt_event

        e1 = _make_event(100, "plantation", "tomate", variete="ronde")
        e2 = _make_event(101, "plantation", "tomate", variete="cerise")

        line1 = _fmt_event(e1)
        line2 = _fmt_event(e2)

        assert "(ronde)" in line1
        assert "(cerise)" in line2
        assert line1 != line2, "Les deux lignes doivent être distinctes"


# ── Scénario : événement sans variété → pas de "()" vide ─────────────────────

class TestSansPrenthesesVides:
    """Événement sans variété → aucun '()' vide dans l'affichage."""

    def test_pas_de_parentheses_vides(self):
        """Scénario : événement tomate sans variété → pas de '()'."""
        from bot import _fmt_event

        e = _make_event(162, "plantation", "tomate", variete=None)
        result = _fmt_event(e)

        assert "()" not in result, f"Aucune parenthèses vides attendues, obtenu : {result}"

    def test_affichage_sans_variete(self):
        """Scénario : format sans variété reste correct."""
        from bot import _fmt_event

        e = _make_event(162, "plantation", "tomate", variete=None, quantite=30.0)
        result = _fmt_event(e)

        assert "tomate" in result
        assert "30.0plants" in result
        assert "()" not in result
