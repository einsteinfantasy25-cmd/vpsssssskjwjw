import time

import pytest

from titanbox.security import FailureCircuit, SecretRedactor, TokenBucket, totp_code, verify_totp


def test_secret_redactor_masks_exact_and_telegram_tokens(monkeypatch):
    monkeypatch.setenv("SOME_API_TOKEN", "super-secret-value-12345")
    redactor = SecretRedactor()
    text = redactor.redact(
        "secret=super-secret-value-12345 tg=123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"  # secret-scan: allow-test-fixture
    )
    assert "super-secret-value-12345" not in text
    assert "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi" not in text  # secret-scan: allow-test-fixture
    assert "<redacted>" in text


def test_totp_matches_rfc6238_sha1_vector():
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    assert totp_code(secret, unix_time=59, digits=8) == "94287082"


def test_totp_verification_rejects_replay():
    secret = "JBSWY3DPEHPK3PXP"
    now = 1_700_000_000.0
    code = totp_code(secret, unix_time=now)
    counter = verify_totp(secret, code, unix_time=now)
    assert counter is not None
    assert verify_totp(secret, code, unix_time=now, last_counter=counter) is None


@pytest.mark.asyncio
async def test_token_bucket_burst_limit():
    bucket = TokenBucket(rate_per_minute=60, burst=2)
    assert await bucket.allow()
    assert await bucket.allow()
    assert not await bucket.allow()


def test_failure_circuit_opens_and_recovers(monkeypatch):
    circuit = FailureCircuit(threshold=2, window_seconds=60, cooldown_seconds=0.05)
    circuit.record_failure()
    assert not circuit.is_open()
    circuit.record_failure()
    assert circuit.is_open()
    time.sleep(0.07)
    assert not circuit.is_open()
