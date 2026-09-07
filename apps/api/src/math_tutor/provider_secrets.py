"""Purpose-separated authenticated encryption for private saved provider keys.

No credential is written to environment variables, exports, configuration JSON,
or diagnostic strings. Rotation/loss of SESSION_SECRET requires re-entering keys.
"""

import base64
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from pydantic import SecretStr

from math_tutor import settings


def cipher() -> AESGCM:
    key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"shepard-provider-credentials-v1",
        info=b"provider-key-encryption",
    ).derive(settings.session_secret().encode())
    return AESGCM(key)


def encrypt_key(connection_id: str, secret: SecretStr) -> str:
    nonce = os.urandom(12)
    encrypted = cipher().encrypt(
        nonce, secret.get_secret_value().encode(), ("provider-v1:" + connection_id).encode()
    )
    return base64.b64encode(nonce + encrypted).decode("ascii")


def decrypt_key(connection_id: str, encrypted: str) -> SecretStr | None:
    try:
        value = base64.b64decode(encrypted, validate=True)
        clear = cipher().decrypt(value[:12], value[12:], ("provider-v1:" + connection_id).encode())
        return SecretStr(clear.decode())
    except InvalidTag, ValueError, UnicodeError:
        # Keep Settings available after session-secret rotation so an adult can
        # replace the credential. Actual inference fails closed in the transport.
        return None
