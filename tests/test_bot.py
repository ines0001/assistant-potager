import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database.db import Base
from database.models import Evenement
from bot import cmd_stats


class TestCmdStats:
    """Tests pour cmd_stats."""

    @patch('database.db.SessionLocal')
    @patch('bot.send_voice_reply', new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_cmd_stats_with_perte(self, mock_voice, mock_session):
        """Test /stats avec calcul stock réel (plantations - pertes)."""
        # Créer DB de test
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = SessionLocal()

        # Ajouter données
        db.add(Evenement(
            type_action="plantation", culture="tomate", variete="cerise",
            quantite=12, unite="plants", date="2026-03-15"
        ))
        db.add(Evenement(
            type_action="perte", culture="tomate", variete="cerise",
            quantite=2, unite="plants", date="2026-03-27", commentaire="gel nocturne"
        ))
        db.add(Evenement(
            type_action="plantation", culture="carotte",
            quantite=50, unite="graines", date="2026-03-10"
        ))
        db.commit()

        mock_session.side_effect = lambda: db

        mock_update = MagicMock()
        mock_message = MagicMock()
        mock_update.message = mock_message
        mock_message.reply_text = AsyncMock()

        await cmd_stats(mock_update, None)

        # Vérifier
        call_args = mock_message.reply_text.call_args[0][0]
        assert "🌱 *Stock plants actuel :*" in call_args
        assert "tomate : *10 plants* (planté 12, perdu 2)" in call_args
        assert "carotte : *50 graines*" in call_args

        db.close()

    @patch('database.db.SessionLocal')
    @patch('bot.send_voice_reply', new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_cmd_stats_no_perte(self, mock_voice, mock_session):
        """Test /stats sans pertes."""
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = SessionLocal()
        db.add(Evenement(
            type_action="plantation", culture="radis",
            quantite=20, unite="plants", date="2026-03-20"
        ))
        db.commit()

        mock_session.side_effect = lambda: db

        mock_update = MagicMock()
        mock_message = MagicMock()
        mock_update.message = mock_message
        mock_message.reply_text = AsyncMock()

        await cmd_stats(mock_update, None)

        call_args = mock_message.reply_text.call_args[0][0]
        assert "radis : *20 plants*" in call_args
        assert "perdu" not in call_args

        db.close()