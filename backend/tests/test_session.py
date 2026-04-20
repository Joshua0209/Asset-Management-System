from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import get_db


class TestGetDb:
    def test_yields_session_and_closes_on_success(self) -> None:
        mock_session = MagicMock()
        with patch("app.db.session.SessionLocal", return_value=mock_session):
            gen = get_db()
            db = next(gen)
            assert db is mock_session
            with pytest.raises(StopIteration):
                next(gen)
        mock_session.close.assert_called_once()
        mock_session.rollback.assert_not_called()

    def test_rolls_back_and_closes_on_sqlalchemy_error(self) -> None:
        mock_session = MagicMock()
        with patch("app.db.session.SessionLocal", return_value=mock_session):
            gen = get_db()
            next(gen)
            with pytest.raises(SQLAlchemyError):
                gen.throw(SQLAlchemyError("connection lost"))
        mock_session.rollback.assert_called_once()
        mock_session.close.assert_called_once()
