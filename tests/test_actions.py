import pytest
from utils.actions import normalize_action, ACTION_MAP


class TestNormalizeAction:
    """Tests pour la fonction normalize_action."""

    def test_normalize_perte_variants(self):
        """Test que les variantes de 'perte' sont normalisées correctement."""
        variants = [
            "j'ai perdu 3 plants",
            "perdu 2 tomates",
            "mort de froid",
            "arraché par le vent",
            "crevé par la sécheresse"
        ]
        for variant in variants:
            result = normalize_action(variant)
            assert result == "perte", f"Échec pour '{variant}': {result}"

    def test_normalize_other_actions(self):
        """Test que les autres actions fonctionnent toujours."""
        test_cases = [
            ("j'ai récolté 5 kg de tomates", "recolte"),
            ("semé des carottes", "semis"),
            ("planté 10 choux", "plantation"),
            ("arrosé pendant 20 min", "arrosage"),
            ("paillé le sol", "paillage"),
            ("traité avec purin d'ortie", "traitement"),
            ("désherbé les mauvaises herbes", "desherbage"),
            ("taillé les branches", "taille"),
            ("tuteuré les tomates", "tuteurage"),
            ("fertilisé avec compost", "amendement"),
            ("observé des limaces", "observation"),
        ]
        for phrase, expected in test_cases:
            result = normalize_action(phrase)
            assert result == expected, f"Échec pour '{phrase}': {result} != {expected}"

    def test_normalize_unknown(self):
        """Test que les actions inconnues retournent la chaîne nettoyée."""
        result = normalize_action("quelque chose d'inconnu")
        assert result == "quelque chose d'inconnu"  # nettoyé

    def test_normalize_none(self):
        """Test avec None."""
        assert normalize_action(None) is None


class TestActionMap:
    """Tests pour ACTION_MAP."""

    def test_perte_in_action_map(self):
        """Test que 'perte' est dans ACTION_MAP."""
        assert "perte" in ACTION_MAP
        assert "perdu" in ACTION_MAP["perte"]
        assert "mort" in ACTION_MAP["perte"]
        assert "arrache" in ACTION_MAP["perte"]
        assert "creve" in ACTION_MAP["perte"]

    def test_action_map_structure(self):
        """Test que ACTION_MAP a la bonne structure."""
        for action, variants in ACTION_MAP.items():
            assert isinstance(variants, list)
            assert len(variants) > 0
            assert all(isinstance(v, str) for v in variants)