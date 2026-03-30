import pytest
from unittest.mock import patch, MagicMock
from llm.groq_client import parse_commande, extract_intent, repondre_question


class TestParseCommande:
    """Tests pour parse_commande (parsing avec Groq)."""

    @patch('llm.groq_client._client')
    def test_parse_perte(self, mock_client):
        """Test parsing d'une phrase de perte."""
        # Mock de la réponse Groq
        mock_response = MagicMock()
        mock_response.choices[0].message.content = '''{
            "action": "perte",
            "culture": "tomate",
            "quantite": 3,
            "unite": "plants",
            "commentaire": "gel nocturne"
        }'''
        mock_client.chat.completions.create.return_value = mock_response

        result = parse_commande("J'ai perdu 3 plants de tomates à cause du gel")

        assert len(result) == 1
        event = result[0]
        assert event['action'] == 'perte'
        assert event['culture'] == 'tomate'
        assert event['quantite'] == 3
        assert event['unite'] == 'plants'
        assert event['commentaire'] == 'gel nocturne'

    @patch('llm.groq_client._client')
    def test_parse_multiple_events(self, mock_client):
        """Test parsing de phrases multiples."""
        mock_response = MagicMock()
        mock_response.choices[0].message.content = '''[
            {"action": "plantation", "culture": "oignon", "quantite": 15, "unite": "plants"},
            {"action": "plantation", "culture": "radis", "quantite": 10, "unite": "plants"}
        ]'''
        mock_client.chat.completions.create.return_value = mock_response

        result = parse_commande("J'ai planté 15 oignons et 10 radis")

        assert len(result) == 2
        assert result[0]['action'] == 'plantation'
        assert result[0]['culture'] == 'oignon'
        assert result[1]['culture'] == 'radis'


class TestExtractIntent:
    """Tests pour extract_intent."""

    @patch('llm.groq_client._client')
    def test_extract_intent_perte(self, mock_client):
        """Test extraction d'intent pour question sur pertes."""
        mock_response = MagicMock()
        mock_response.choices[0].message.content = '{"action": "perte", "culture": "tomate", "date_from": null}'
        mock_client.chat.completions.create.return_value = mock_response

        result = extract_intent("quand ai-je perdu des tomates ?")

        assert result['action'] == 'perte'
        assert result['culture'] == 'tomate'
        assert result['date_from'] is None


class TestRepondreQuestion:
    """Tests pour repondre_question."""

    @patch('llm.groq_client._client')
    def test_repondre_stock_reel(self, mock_client):
        """Test réponse sur stock réel."""
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "Il te reste 10 plants de tomates."
        mock_client.chat.completions.create.return_value = mock_response

        contexte = '''[
            {"action": "plantation", "culture": "tomate", "quantite": 12, "date": "2026-03-15"},
            {"action": "perte", "culture": "tomate", "quantite": 2, "date": "2026-03-27"}
        ]'''

        result = repondre_question("combien de tomates me reste-t-il ?", contexte)

        assert "10 plants" in result or "reste" in result