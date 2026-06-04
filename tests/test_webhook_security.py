import hashlib
import hmac

from agent_control.webhook_server import verify_hmac


def test_verify_hmac_valid() -> None:
    secret = "test-secret"
    body = b'{"repository":{"full_name":"ai-sdlc-lab/demo-app"}}'
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert verify_hmac(secret, body, sig)


def test_verify_hmac_invalid() -> None:
    assert not verify_hmac("secret", b"body", "sha256=deadbeef")
