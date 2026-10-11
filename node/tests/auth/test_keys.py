"""Master key file, HKDF (RFC 5869), scrypt strings, tokens and TOTP (RFC 4226 and 6238)."""

import datetime as dt
import hashlib
import hmac
import os
from pathlib import Path

import pytest

from mia.core import keys
from mia.settings import get_settings


def test_generate_refuses_overwrite_and_sets_mode(tmp_path: Path) -> None:
    path = tmp_path / "k" / "master.key"
    keys.generate(path)
    assert len(path.read_bytes()) == 32 and oct(path.stat().st_mode & 0o777) == "0o400"
    with pytest.raises(keys.MasterKeyError, match="exists"):
        keys.generate(path)


def test_master_key_refuses_missing_or_open_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "other.key"  # conftest already made tmp_path/master.key
    monkeypatch.setenv("MIA_MASTER_KEY_FILE", str(path))
    get_settings.cache_clear()
    keys.reset_cache()
    with pytest.raises(keys.MasterKeyError, match="not found"):
        keys.master_key()
    keys.generate(path)
    os.chmod(path, 0o644)
    with pytest.raises(keys.MasterKeyError, match="chmod 400"):
        keys.master_key()
    os.chmod(path, 0o400)
    assert keys.master_key() == path.read_bytes()


def test_without_key_file_node_secret_is_the_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MIA_MASTER_KEY_FILE")
    monkeypatch.setenv("MIA_NODE_SECRET", "old-secret")
    get_settings.cache_clear()
    keys.reset_cache()
    assert keys.master_key() == hashlib.sha256(b"old-secret").digest()
    # Link codes created before the key file existed keep working: same HMAC as before.
    expected = hmac.new(b"old-secret", b"123456", hashlib.sha256).hexdigest()
    assert keys.code_hmac("123456") == expected
    monkeypatch.setenv("MIA_NODE_SECRET", "")
    get_settings.cache_clear()
    keys.reset_cache()
    with pytest.raises(keys.MasterKeyError, match="mia keys init"):
        keys.master_key()


def test_hkdf_rfc_5869_case_1() -> None:
    okm = keys.hkdf(bytes([0x0B] * 22), bytes(range(0xF0, 0xFA)), 42, bytes(range(13)))
    assert okm.hex() == (
        "3cb25f25faacd57a90434f64d0362f2a2d2d0a90cf1a5a4c5db02d56ecc4c5bf34007208d5b887185865"
    )


def test_subkeys_differ_by_label() -> None:
    assert keys.subkey("mia/totp") != keys.subkey("mia/auth-codes")
    assert len(keys.subkey("mia/totp")) == 32


def test_scrypt_string_round_trip_and_params() -> None:
    stored = keys.hash_secret("correct horse")
    assert stored.startswith(f"scrypt${keys.SCRYPT_N}$8$1$")
    assert keys.verify_secret("correct horse", stored)
    assert not keys.verify_secret("wrong", stored)
    assert not keys.verify_secret("x", "garbage")
    assert keys.verify_secret("x", keys.dummy_hash()) is False


def test_tokens_and_codes() -> None:
    tok = keys.new_token()
    assert len(tok) == 43 and "=" not in tok and len(keys.token_hash(tok)) == 64
    assert keys.numeric_code().isdigit() and len(keys.numeric_code()) == 6


def test_hotp_rfc_4226_vectors() -> None:
    key = b"12345678901234567890"
    assert [keys.hotp(key, c) for c in (0, 1, 2)] == ["755224", "287082", "359152"]


def test_totp_step_and_seed() -> None:
    assert keys.totp_step(dt.datetime(1970, 1, 1, 0, 0, 59, tzinfo=dt.UTC)) == 1
    seed = keys.totp_seed("CRED", "nonce")
    assert len(seed) == 20 and seed != keys.totp_seed("CRED", "other")
    uri = keys.totp_uri(seed, "owner@example.fi")
    assert uri.startswith("otpauth://totp/Mia:owner%40example.fi?secret=") and "issuer=Mia" in uri
