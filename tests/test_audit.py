from pathlib import Path

from titanbox.audit import AuditLog


def test_audit_chain_detects_tamper(tmp_path: Path):
    path = tmp_path / "audit.jsonl"
    audit = AuditLog(path, "audit-test-key")
    audit.append(action="deploy", actor_id=123, result="success", project="bot1")
    audit.append(action="rollback", actor_id=123, result="success", project="bot1")
    assert audit.verify() is True
    text = path.read_text()
    path.write_text(text.replace('"result":"success"', '"result":"tampered"', 1))
    assert audit.verify() is False
