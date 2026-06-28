"""Generate a VAPID keypair for Web Push (locked-screen timer alerts).

Run once, then store the two values in SSM:
    python scripts/gen_vapid.py
    aws ssm put-parameter --name /vires/vapid_public_key  --type String       --value "<public>"
    aws ssm put-parameter --name /vires/vapid_private_key --type SecureString  --value "<private>"

The public key is the browser's applicationServerKey (non-secret); the private key
signs pushes — keep it secret.
"""

from __future__ import annotations

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def main() -> None:
    priv = ec.generate_private_key(ec.SECP256R1())
    private_raw = _b64url(priv.private_numbers().private_value.to_bytes(32, "big"))
    public_point = priv.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    print("VIRES_VAPID_PUBLIC_KEY  (applicationServerKey, non-secret):")
    print(_b64url(public_point))
    print()
    print("VIRES_VAPID_PRIVATE_KEY (SECRET — store as SecureString):")
    print(private_raw)


if __name__ == "__main__":
    main()
