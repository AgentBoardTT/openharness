"""Tests for the audit module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.audit.logger import AuditEventType, AuditLogger
from harness.audit.scanner import PIIScanner, ScanResult
from harness.audit.retention import RetentionPolicy
from harness.audit.export import export_audit_log, export_all_audit_logs


# ---------------------------------------------------------------------------
# AuditLogger tests
# ---------------------------------------------------------------------------


class TestAuditLogger:
    def test_creates_log_file(self, tmp_path: Path) -> None:
        logger = AuditLogger("test-session", audit_dir=tmp_path)
        logger.log_session_start("anthropic", "claude-sonnet-4-6")
        assert logger.log_path is not None
        assert logger.log_path.exists()

    def test_disabled_logger_noop(self, tmp_path: Path) -> None:
        logger = AuditLogger("test-session", enabled=False, audit_dir=tmp_path)
        result = logger.log_session_start("anthropic", "claude-sonnet-4-6")
        assert result is None
        assert logger.event_count == 0

    def test_chain_integrity(self, tmp_path: Path) -> None:
        logger = AuditLogger("test-session", audit_dir=tmp_path)
        logger.log_session_start("anthropic", "claude-sonnet-4-6")
        logger.log_tool_call("Bash", {"command": "ls"})
        logger.log_tool_result("Bash", is_error=False, content_length=100)
        logger.log_session_end(turns=1, total_tokens=500)

        assert logger.event_count == 4

        # Verify hash chain
        events = []
        with open(logger.log_path) as f:  # type: ignore[arg-type]
            for line in f:
                events.append(json.loads(line))

        assert len(events) == 4
        for i in range(1, len(events)):
            # Each event's prev_hash should match the previous event's hash
            assert events[i]["prev_hash"] == events[i - 1]["hash"]

    def test_log_tool_call_with_args(self, tmp_path: Path) -> None:
        logger = AuditLogger("test-session", audit_dir=tmp_path, log_tool_args=True)
        logger.log_tool_call("Bash", {"command": "echo hello"})

        with open(logger.log_path) as f:  # type: ignore[arg-type]
            event = json.loads(f.readline())
        assert event["data"]["args"]["command"] == "echo hello"

    def test_log_tool_call_without_args(self, tmp_path: Path) -> None:
        logger = AuditLogger("test-session", audit_dir=tmp_path, log_tool_args=False)
        logger.log_tool_call("Bash", {"command": "echo hello"})

        with open(logger.log_path) as f:  # type: ignore[arg-type]
            event = json.loads(f.readline())
        assert "args" not in event["data"]

    def test_log_permission_decision(self, tmp_path: Path) -> None:
        logger = AuditLogger("test-session", audit_dir=tmp_path)
        logger.log_permission_decision("Bash", "allow", "bypass")

        with open(logger.log_path) as f:  # type: ignore[arg-type]
            event = json.loads(f.readline())
        assert event["event_type"] == "permission_decision"
        assert event["data"]["tool"] == "Bash"
        assert event["data"]["decision"] == "allow"

    def test_log_provider_call(self, tmp_path: Path) -> None:
        logger = AuditLogger("test-session", audit_dir=tmp_path)
        logger.log_provider_call(
            "anthropic", "claude-sonnet-4-6",
            input_tokens=100, output_tokens=50, cost=0.001,
        )

        with open(logger.log_path) as f:  # type: ignore[arg-type]
            event = json.loads(f.readline())
        assert event["event_type"] == "provider_call"
        assert event["data"]["input_tokens"] == 100

    def test_log_pii_detected(self, tmp_path: Path) -> None:
        logger = AuditLogger("test-session", audit_dir=tmp_path)
        logger.log_pii_detected("email", "tool_result")

        with open(logger.log_path) as f:  # type: ignore[arg-type]
            event = json.loads(f.readline())
        assert event["event_type"] == "pii_detected"

    def test_verify_chain_valid(self, tmp_path: Path) -> None:
        logger = AuditLogger("verify-test", audit_dir=tmp_path)
        logger.log_session_start("anthropic", "claude-sonnet-4-6")
        logger.log_tool_call("Bash", {"command": "ls"})
        logger.log_session_end(turns=1)
        logger.close()

        valid, errors = AuditLogger.verify_chain(logger.log_path)  # type: ignore[arg-type]
        assert valid, f"Chain should be valid but got errors: {errors}"

    def test_verify_chain_tampered(self, tmp_path: Path) -> None:
        logger = AuditLogger("tamper-test", audit_dir=tmp_path)
        logger.log_session_start("anthropic", "claude-sonnet-4-6")
        logger.log_tool_call("Bash", {"command": "ls"})
        logger.close()

        # Tamper with the file — modify one event
        lines = logger.log_path.read_text().strip().split("\n")  # type: ignore[union-attr]
        event = json.loads(lines[0])
        event["data"]["provider"] = "tampered"
        lines[0] = json.dumps(event, separators=(",", ":"))
        logger.log_path.write_text("\n".join(lines) + "\n")  # type: ignore[union-attr]

        valid, errors = AuditLogger.verify_chain(logger.log_path)  # type: ignore[arg-type]
        assert not valid
        assert len(errors) > 0

    def test_context_manager(self, tmp_path: Path) -> None:
        with AuditLogger("ctx-test", audit_dir=tmp_path) as logger:
            logger.log_session_start("anthropic", "claude-sonnet-4-6")
        # After exiting context, file should be written
        log_path = tmp_path / "audit-ctx-test.jsonl"
        assert log_path.exists()
        content = log_path.read_text().strip()
        assert len(content) > 0

    def test_close_idempotent(self, tmp_path: Path) -> None:
        logger = AuditLogger("close-test", audit_dir=tmp_path)
        logger.log_session_start("anthropic", "claude-sonnet-4-6")
        logger.close()
        logger.close()  # Should not raise


# ---------------------------------------------------------------------------
# PIIScanner tests
# ---------------------------------------------------------------------------


class TestPIIScanner:
    def test_detects_email(self) -> None:
        scanner = PIIScanner()
        results = scanner.scan("Contact user@example.com for help")
        names = [r.pattern_name for r in results]
        assert "email" in names

    def test_detects_phone(self) -> None:
        scanner = PIIScanner()
        results = scanner.scan("Call 555-123-4567 for support")
        names = [r.pattern_name for r in results]
        assert "phone_us" in names

    def test_detects_ssn(self) -> None:
        scanner = PIIScanner()
        results = scanner.scan("SSN: 123-45-6789")
        names = [r.pattern_name for r in results]
        assert "ssn" in names

    def test_detects_aws_key(self) -> None:
        scanner = PIIScanner()
        results = scanner.scan("AKIAIOSFODNN7EXAMPLE")
        names = [r.pattern_name for r in results]
        assert "aws_access_key" in names

    def test_detects_github_token(self) -> None:
        scanner = PIIScanner()
        results = scanner.scan("token: ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij")
        names = [r.pattern_name for r in results]
        assert "github_token" in names

    def test_detects_jwt(self) -> None:
        scanner = PIIScanner()
        jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiYWRtaW4iOnRydWV9.TJVA95OrM7E2cBab30RMHrHDcEfxjoYZgeFONFh7HgQ"
        results = scanner.scan(jwt)
        names = [r.pattern_name for r in results]
        assert "jwt" in names

    def test_detects_slack_token(self) -> None:
        scanner = PIIScanner()
        results = scanner.scan("SLACK_TOKEN=xoxb-123456789-abcdefghij")
        names = [r.pattern_name for r in results]
        assert "slack_token" in names

    def test_detects_private_key(self) -> None:
        scanner = PIIScanner()
        results = scanner.scan("-----BEGIN RSA PRIVATE KEY-----")
        names = [r.pattern_name for r in results]
        assert "private_key_header" in names

    def test_detects_generic_api_key(self) -> None:
        scanner = PIIScanner()
        results = scanner.scan("api_key=sk_test_AbCdEfGhIjKlMnOpQrStUv")
        names = [r.pattern_name for r in results]
        assert "generic_api_key" in names

    def test_no_false_positive_on_normal_text(self) -> None:
        scanner = PIIScanner()
        results = scanner.scan("This is a normal sentence about programming.")
        assert len(results) == 0

    def test_has_findings(self) -> None:
        scanner = PIIScanner()
        assert scanner.has_findings("user@example.com")
        assert not scanner.has_findings("just normal text")

    def test_custom_pattern(self) -> None:
        scanner = PIIScanner(custom_patterns={"custom_id": r"CUST-\d{6}"})
        results = scanner.scan("Customer CUST-123456 filed a complaint")
        names = [r.pattern_name for r in results]
        assert "custom_id" in names

    def test_scan_dict(self) -> None:
        scanner = PIIScanner()
        data = {"name": "John", "email": "john@example.com", "count": 42}
        results = scanner.scan_dict(data)
        names = [r.pattern_name for r in results]
        assert "email" in names

    def test_disabled_patterns(self) -> None:
        scanner = PIIScanner(disabled_patterns={"email"})
        results = scanner.scan("user@example.com")
        names = [r.pattern_name for r in results]
        assert "email" not in names

    def test_scan_dict_nested(self) -> None:
        scanner = PIIScanner()
        data = {
            "user": {
                "contact": {"email": "nested@example.com"},
                "name": "Alice",
            },
            "tags": ["safe", "AKIAIOSFODNN7EXAMPLE"],
        }
        results = scanner.scan_dict(data)
        names = [r.pattern_name for r in results]
        assert "email" in names
        assert "aws_access_key" in names

    def test_scan_dict_depth_limit(self) -> None:
        """Deeply nested dicts should not cause recursion issues."""
        scanner = PIIScanner()
        deep: dict = {"v": "safe"}
        current = deep
        for _ in range(20):
            current["child"] = {"v": "safe"}
            current = current["child"]
        current["v"] = "user@example.com"
        # Beyond depth 10, scanning stops — the email may or may not be found
        # but it should NOT raise
        scanner.scan_dict(deep)


# ---------------------------------------------------------------------------
# RetentionPolicy tests
# ---------------------------------------------------------------------------


class TestRetentionPolicy:
    def test_age_based_cleanup(self, tmp_path: Path) -> None:
        import os
        import time

        # Create some old files
        for i in range(3):
            f = tmp_path / f"audit-old-{i}.jsonl"
            f.write_text("{}\n")
            # Set mtime to 200 days ago
            old_time = time.time() - (200 * 86400)
            os.utime(f, (old_time, old_time))

        # Create a recent file
        recent = tmp_path / "audit-recent.jsonl"
        recent.write_text("{}\n")

        policy = RetentionPolicy(tmp_path, max_age_days=90)
        removed = policy.enforce_retention()

        assert removed == 3
        assert recent.exists()

    def test_size_based_cleanup(self, tmp_path: Path) -> None:
        # Create files totaling > 1MB
        for i in range(10):
            f = tmp_path / f"audit-size-{i}.jsonl"
            f.write_text("x" * 200_000)  # 200KB each = 2MB total

        policy = RetentionPolicy(tmp_path, max_size_mb=1)
        removed = policy.enforce_retention()

        assert removed > 0
        remaining = list(tmp_path.glob("audit-*.jsonl"))
        total_size = sum(f.stat().st_size for f in remaining)
        assert total_size <= 1 * 1024 * 1024

    def test_empty_dir(self, tmp_path: Path) -> None:
        policy = RetentionPolicy(tmp_path / "nonexistent", max_age_days=90)
        removed = policy.enforce_retention()
        assert removed == 0

    def test_archive_mode(self, tmp_path: Path) -> None:
        import os
        import time

        f = tmp_path / "audit-archive-test.jsonl"
        f.write_text('{"event": "test"}\n')
        old_time = time.time() - (200 * 86400)
        os.utime(f, (old_time, old_time))

        policy = RetentionPolicy(tmp_path, max_age_days=90, archive=True)
        removed = policy.enforce_retention()

        assert removed == 1
        assert not f.exists()
        gz = tmp_path / "audit-archive-test.jsonl.gz"
        assert gz.exists()


# ---------------------------------------------------------------------------
# Export tests
# ---------------------------------------------------------------------------


class TestExport:
    def test_export_json(self, tmp_path: Path) -> None:
        logger = AuditLogger("export-test", audit_dir=tmp_path)
        logger.log_session_start("anthropic", "claude-sonnet-4-6")
        logger.log_session_end()

        result = export_audit_log("export-test", fmt="json", audit_dir=tmp_path)
        events = json.loads(result)
        assert len(events) == 2

    def test_export_csv(self, tmp_path: Path) -> None:
        logger = AuditLogger("export-test", audit_dir=tmp_path)
        logger.log_session_start("anthropic", "claude-sonnet-4-6")

        result = export_audit_log("export-test", fmt="csv", audit_dir=tmp_path)
        assert "event_id" in result
        assert "session_start" in result

    def test_export_missing_session(self, tmp_path: Path) -> None:
        result = export_audit_log("nonexistent", audit_dir=tmp_path)
        assert result == ""

    def test_export_all(self, tmp_path: Path) -> None:
        for sid in ("s1", "s2"):
            logger = AuditLogger(sid, audit_dir=tmp_path)
            logger.log_session_start("anthropic", "claude-sonnet-4-6")

        result = export_all_audit_logs(fmt="json", audit_dir=tmp_path)
        events = json.loads(result)
        assert len(events) == 2
