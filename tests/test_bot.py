import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database.db import Base
from database.models import Evenement
from bot import cmd_stats


class TestCmdStats:
    """Tests pour cmd_stats."""

    @patch('bot.send_voice_reply', new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_cmd_stats_with_perte(self, mock_voice, test_db):
        """Test /stats avec calcul stock réel (plantations - pertes)."""
        # Ajouter données
        test_db.add(Evenement(
            type_action="plantation", culture="tomate", variete="cerise",
            quantite=12, unite="plants", date=date(2026, 3, 15)
        ))
        test_db.add(Evenement(
            type_action="perte", culture="tomate", variete="cerise",
            quantite=2, unite="plants", date=date(2026, 3, 27), commentaire="gel nocturne"
        ))
        test_db.add(Evenement(
            type_action="plantation", culture="carotte",
            quantite=50, unite="graines", date=date(2026, 3, 10)
        ))
        test_db.commit()

        mock_update = MagicMock()
        mock_message = MagicMock()
        mock_update.message = mock_message
        mock_message.reply_text = AsyncMock()

        # Patch SessionLocal to return test_db
        with patch('bot.SessionLocal', return_value=test_db):
            await cmd_stats(mock_update, None)

        # Vérifier
        call_args = mock_message.reply_text.call_args[0][0]
        assert "🥬 *Cultures végétatives (récolte destructive) :*" in call_args
        assert "tomate : *10 plants* (planté 12, perdu 2)" in call_args
        assert "carotte : *50 graines*" in call_args

    @patch('bot.send_voice_reply', new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_cmd_stats_with_perte_and_recolte(self, mock_voice, test_db):
        """Test /stats avec calcul stock réel (plantations - pertes - récoltes)."""
        # Ajouter données : 25 plantés, 4 perdus, 2 récoltés → stock réel 19
        test_db.add(Evenement(
            type_action="plantation", culture="salade", 
            quantite=25, unite="plants", date=date(2026, 3, 10)
        ))
        test_db.add(Evenement(
            type_action="perte", culture="salade",
            quantite=4, unite="plants", date=date(2026, 3, 20), commentaire="gel"
        ))
        test_db.add(Evenement(
            type_action="recolte", culture="salade",
            quantite=2, unite="plants", date=date(2026, 3, 25)
        ))
        test_db.commit()

        mock_update = MagicMock()
        mock_message = MagicMock()
        mock_update.message = mock_message
        mock_message.reply_text = AsyncMock()

        # Patch SessionLocal to return test_db
        with patch('bot.SessionLocal', return_value=test_db):
            await cmd_stats(mock_update, None)

        # Vérifier
        call_args = mock_message.reply_text.call_args[0][0]
        assert "🥬 *Cultures végétatives (récolte destructive) :*" in call_args
        assert "salade : *19 plants* (planté 25, perdu 4, récolté 2)" in call_args

    @patch('bot.send_voice_reply', new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_cmd_stats_no_perte(self, mock_voice, test_db):
        """Test /stats sans pertes."""
        test_db.add(Evenement(
            type_action="plantation", culture="radis",
            quantite=20, unite="plants", date=date(2026, 3, 20)
        ))
        test_db.commit()

        mock_update = MagicMock()
        mock_message = MagicMock()
        mock_update.message = mock_message
        mock_message.reply_text = AsyncMock()

        # Patch SessionLocal to return test_db
        with patch('bot.SessionLocal', return_value=test_db):
            await cmd_stats(mock_update, None)

        call_args = mock_message.reply_text.call_args[0][0]
        assert "radis : *20 plants*" in call_args
        assert "perdu" not in call_args