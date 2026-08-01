"""登录鉴权：密码哈希（PBKDF2）+ 不透明会话 token。"""
from __future__ import annotations

import hashlib
import hmac
import secrets

PBKDF2_ITERATIONS = 600_000


def hash_password(password: str) -> str:
    """生成密码哈希，格式：pbkdf2_sha256$迭代次数$盐hex$哈希hex。"""
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """校验密码（常量时间比较，防时序攻击）。"""
    try:
        _algo, iterations, salt_hex, hash_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations),
        )
        return hmac.compare_digest(dk.hex(), hash_hex)
    except (ValueError, TypeError):
        return False


def generate_token() -> str:
    """生成不透明会话 token。"""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """token 入库前哈希，DB 不存明文 token。"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
