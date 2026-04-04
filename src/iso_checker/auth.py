from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

PBKDF2_ITERATIONS = 240_000


def hash_password(password: str, *, iterations: int = PBKDF2_ITERATIONS) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algo, iter_raw, salt_hex, digest_hex = stored_hash.split("$", 3)
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    iterations = int(iter_raw)
    salt = bytes.fromhex(salt_hex)
    expected = bytes.fromhex(digest_hex)
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def _urlsafe_b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _urlsafe_unb64(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def issue_session_cookie(payload: dict[str, Any], secret: str, *, ttl_seconds: int = 8 * 3600) -> str:
    body = dict(payload)
    body["exp"] = int(time.time()) + ttl_seconds
    body_json = json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")
    token = _urlsafe_b64(body_json)
    sig = hmac.new(secret.encode("utf-8"), token.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{token}.{sig}"


def parse_session_cookie(cookie_value: str, secret: str) -> dict[str, Any] | None:
    try:
        token, sig = cookie_value.split(".", 1)
    except ValueError:
        return None
    expected = hmac.new(secret.encode("utf-8"), token.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        payload = json.loads(_urlsafe_unb64(token).decode("utf-8"))
    except Exception:
        return None
    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    return payload
