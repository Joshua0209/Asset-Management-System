from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import get_settings
from app.core.security import (
    InvalidTokenError,
    TokenPayload,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.models.user import UserRole


class TestPasswordHashing:
    def test_hash_password_returns_bcrypt_string(self) -> None:
        hashed = hash_password("correct horse battery staple")
        assert hashed.startswith(("$2a$", "$2b$", "$2y$"))
        assert hashed != "correct horse battery staple"

    def test_hash_password_is_salted_and_nondeterministic(self) -> None:
        first = hash_password("same password")
        second = hash_password("same password")
        assert first != second

    def test_verify_password_accepts_correct(self) -> None:
        hashed = hash_password("Password123")
        assert verify_password("Password123", hashed) is True

    def test_verify_password_rejects_wrong(self) -> None:
        hashed = hash_password("Password123")
        assert verify_password("Password124", hashed) is False

    def test_verify_password_rejects_empty(self) -> None:
        hashed = hash_password("Password123")
        assert verify_password("", hashed) is False

    def test_verify_password_tolerates_malformed_hash(self) -> None:
        # A malformed hash must return False, not raise — keeps routes simple.
        assert verify_password("anything", "not-a-bcrypt-hash") is False


class TestAccessToken:
    def test_create_and_decode_round_trip(self) -> None:
        token, expires_at = create_access_token(
            subject="user-uuid-123",
            role=UserRole.HOLDER,
        )
        assert isinstance(token, str) and token.count(".") == 2  # header.payload.sig
        payload = decode_access_token(token)
        assert isinstance(payload, TokenPayload)
        assert payload.sub == "user-uuid-123"
        assert payload.role == UserRole.HOLDER
        # expires_at must be UTC-aware and in the future
        assert expires_at.tzinfo is not None
        assert expires_at > datetime.now(UTC)

    def test_expires_at_reflects_configured_minutes(self) -> None:
        before = datetime.now(UTC)
        _, expires_at = create_access_token(
            subject="user-uuid",
            role=UserRole.MANAGER,
            expires_minutes=30,
        )
        delta = expires_at - before
        # Allow some slack for clock drift during test execution
        assert timedelta(minutes=29) < delta <= timedelta(minutes=30, seconds=5)

    def test_decode_rejects_expired_token(self) -> None:
        token, _ = create_access_token(
            subject="user-uuid",
            role=UserRole.HOLDER,
            expires_minutes=-1,  # already expired
        )
        with pytest.raises(InvalidTokenError):
            decode_access_token(token)

    def test_decode_rejects_tampered_signature(self) -> None:
        token, _ = create_access_token(subject="user-uuid", role=UserRole.HOLDER)
        tampered = token[:-4] + ("AAAA" if token[-4:] != "AAAA" else "BBBB")
        with pytest.raises(InvalidTokenError):
            decode_access_token(tampered)

    def test_decode_rejects_garbage(self) -> None:
        with pytest.raises(InvalidTokenError):
            decode_access_token("not.a.jwt")

    def test_decode_rejects_token_with_wrong_secret(self, monkeypatch: pytest.MonkeyPatch) -> None:
        token, _ = create_access_token(subject="user-uuid", role=UserRole.HOLDER)
        # After token is minted, rotate the secret — the token must no longer verify.
        from app.core import config as config_module

        config_module.get_settings.cache_clear()
        monkeypatch.setenv("JWT_SECRET", "a-totally-different-secret-value")
        try:
            with pytest.raises(InvalidTokenError):
                decode_access_token(token)
        finally:
            config_module.get_settings.cache_clear()

    def test_token_carries_role_claim(self) -> None:
        token, _ = create_access_token(subject="u", role=UserRole.MANAGER)
        assert decode_access_token(token).role == UserRole.MANAGER


class TestDecodeAccessTokenMalformedClaims:
    """Cover the second try/except in ``decode_access_token`` (the
    ``(KeyError, ValueError)`` handler at app/core/security.py:91-92).

    These tokens are *cryptographically valid* — same secret, same algorithm,
    not expired — but the claim payload itself is malformed. This is the path
    a forged or version-skewed token takes when the signature happens to line
    up but the contract has drifted.
    """

    def _sign(self, claims: dict[str, object]) -> str:
        """Sign a JWT with the project's secret/algorithm so the signature
        verifies; the body lets us mutate claim shape independently."""
        settings = get_settings()
        return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    @staticmethod
    def _future_exp_ts() -> int:
        return int((datetime.now(UTC) + timedelta(minutes=5)).timestamp())

    def test_missing_sub_claim_raises_invalid_token(self) -> None:
        token = self._sign({"role": "holder", "exp": self._future_exp_ts()})
        with pytest.raises(InvalidTokenError, match="Malformed token claims"):
            decode_access_token(token)

    def test_missing_role_claim_raises_invalid_token(self) -> None:
        token = self._sign({"sub": "user-uuid", "exp": self._future_exp_ts()})
        with pytest.raises(InvalidTokenError, match="Malformed token claims"):
            decode_access_token(token)

    def test_unknown_role_value_raises_invalid_token(self) -> None:
        # Role "admin" isn't in UserRole — would otherwise become a privilege
        # escalation if we accepted it.
        token = self._sign(
            {"sub": "user-uuid", "role": "admin", "exp": self._future_exp_ts()}
        )
        with pytest.raises(InvalidTokenError, match="Malformed token claims"):
            decode_access_token(token)
