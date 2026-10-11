"""Key material and the crypto primitives of authentication (ADR 011). No database here.

Guarantees: the master key is read from a root-only file (mode 0400) or, without one, derived
from MIA_NODE_SECRET; subkeys come from HKDF-SHA256 with fixed labels, so no TOTP seed is ever
stored; passwords, PINs and client secrets are scrypt strings that carry their parameters;
tokens are 32 random bytes; TOTP follows RFC 6238 on HOTP (RFC 4226).
"""

import base64
import hashlib
import hmac
import os
import secrets
import struct
import urllib.parse
from datetime import datetime
from pathlib import Path

from mia.settings import get_settings

KEY_BYTES = 32
SCRYPT_N = 2**17  # OWASP; tests lower it through monkeypatch
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_MAXMEM = 256 * 1024 * 1024
TOTP_STEP = 30
TOTP_DIGITS = 6
_cache: dict[Path, bytes] = {}
_dummy: str | None = None


class MasterKeyError(RuntimeError):
    """The master key file is missing, unreadable or too open, and there is no fallback."""


def generate(path: Path) -> None:
    """Write a new 32-byte key with mode 0400. Refuses to overwrite an existing file."""
    if path.exists():
        raise MasterKeyError(f"{path} exists; refusing to overwrite a master key")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
    with os.fdopen(fd, "wb") as f:
        f.write(secrets.token_bytes(KEY_BYTES))


def master_key() -> bytes:
    """The node's master key. Without MIA_MASTER_KEY_FILE, SHA-256 of MIA_NODE_SECRET."""
    settings = get_settings()
    path = settings.MIA_MASTER_KEY_FILE
    if path is None:
        if not settings.MIA_NODE_SECRET:
            raise MasterKeyError("set MIA_MASTER_KEY_FILE (run `mia keys init`) or MIA_NODE_SECRET")
        return hashlib.sha256(settings.MIA_NODE_SECRET.encode()).digest()
    if path not in _cache:
        try:
            mode = path.stat().st_mode
        except FileNotFoundError as exc:
            raise MasterKeyError(f"master key file not found: {path}") from exc
        if not path.is_file():
            raise MasterKeyError(f"{path} is not a file (a missing bind mount becomes a folder)")
        if mode & 0o077:
            raise MasterKeyError(f"{path} is readable by group or others; chmod 400 it")
        data = path.read_bytes()
        if len(data) < KEY_BYTES:
            raise MasterKeyError(f"{path} holds fewer than {KEY_BYTES} bytes")
        _cache[path] = data
    return _cache[path]


def reset_cache() -> None:
    """Forget the cached key file and the dummy hash (tests, key rotation)."""
    global _dummy
    _cache.clear()
    _dummy = None


def hkdf(ikm: bytes, info: bytes, length: int = 32, salt: bytes = b"") -> bytes:
    """HKDF-SHA256 (RFC 5869): extract, then expand to `length` bytes."""
    prk = hmac.new(salt or bytes(32), ikm, hashlib.sha256).digest()
    out, block, counter = b"", b"", 1
    while len(out) < length:
        block = hmac.new(prk, block + info + bytes([counter]), hashlib.sha256).digest()
        out += block
        counter += 1
    return out[:length]


def subkey(label: str) -> bytes:
    """A 32-byte key for one purpose: mia/link-codes, mia/auth-codes, mia/totp."""
    return hkdf(master_key(), label.encode())


def code_hmac(code: str) -> str:
    """HMAC of a one-time code. Keyed by MIA_NODE_SECRET itself when there is no key file, so
    link codes created before the key file keep working; by the auth-codes subkey otherwise."""
    settings = get_settings()
    key = (
        subkey("mia/auth-codes")
        if settings.MIA_MASTER_KEY_FILE is not None
        else settings.MIA_NODE_SECRET.encode()
    )
    if not key:
        raise MasterKeyError("set MIA_MASTER_KEY_FILE (run `mia keys init`) or MIA_NODE_SECRET")
    return hmac.new(key, code.encode(), hashlib.sha256).hexdigest()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def hash_secret(secret: str) -> str:
    """scrypt string `scrypt$N$r$p$salt$hash` (parameters travel with the hash)."""
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        secret.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, maxmem=SCRYPT_MAXMEM
    )
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def verify_secret(secret: str, stored: str) -> bool:
    """Constant-time check of a secret against a scrypt string. False for a malformed string."""
    try:
        _, n, r, p, salt, digest = stored.split("$")
        expected = hashlib.scrypt(
            secret.encode(), salt=_unb64(salt), n=int(n), r=int(r), p=int(p), maxmem=SCRYPT_MAXMEM
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(expected, _unb64(digest))


def dummy_hash() -> str:
    """A hash to verify against when the login is unknown, so timing does not reveal it."""
    global _dummy
    if _dummy is None:
        _dummy = hash_secret(secrets.token_hex(8))
    return _dummy


def new_token() -> str:
    """32 random bytes, base64url without padding (43 characters)."""
    return _b64(secrets.token_bytes(32))


def token_hash(token: str) -> str:
    """SHA-256 hex of a token, the only form stored."""
    return hashlib.sha256(token.encode()).hexdigest()


def numeric_code(digits: int = 6) -> str:
    """A zero-padded random numeric code."""
    return f"{secrets.randbelow(10**digits):0{digits}d}"


def hotp(key: bytes, counter: int, digits: int = TOTP_DIGITS) -> str:
    """HOTP (RFC 4226) with HMAC-SHA1 and dynamic truncation."""
    mac = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    code = struct.unpack(">I", mac[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{code % 10**digits:0{digits}d}"


def totp_step(now: datetime) -> int:
    """The 30-second step a time falls in (RFC 6238)."""
    return int(now.timestamp()) // TOTP_STEP


def totp_seed(credential_id: str, nonce: str) -> bytes:
    """The 20-byte TOTP seed of a credential, derived, never stored."""
    return hkdf(subkey("mia/totp"), f"{credential_id}:{nonce}".encode(), 20)


def totp_uri(seed: bytes, label: str) -> str:
    """otpauth URI for authenticator apps."""
    secret = base64.b32encode(seed).decode().rstrip("=")
    return (
        f"otpauth://totp/Mia:{urllib.parse.quote(label, safe='')}?secret={secret}"
        f"&issuer=Mia&algorithm=SHA1&digits={TOTP_DIGITS}&period={TOTP_STEP}"
    )
