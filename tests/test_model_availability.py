#!/usr/bin/env python3
"""Focused tests for read-only model availability and provider health foundation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
from pathlib import Path
import sys
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from core.model_availability import (  # noqa: E402
    ErrorCategory,
    Freshness,
    ModelAvailabilityRecord,
    ModelStatus,
    PROBE_FAILED,
    PROBE_UNSUPPORTED,
    PROVENANCE_OFFLINE,
    PROVENANCE_PROBE,
    PROVENANCE_UNSUPPORTED,
    ProviderHealthRecord,
    ProviderStatus,
    observe_model_offline,
    observe_provider_offline,
    probe_model_availability,
    probe_provider_health,
    sanitize_identifier,
    validate_timeout,
)


class ModelAvailabilityTests(unittest.TestCase):
    def test_enums_and_constants_exact_values(self):
        self.assertEqual(ModelStatus.AVAILABLE.value, "AVAILABLE")
        self.assertEqual(ModelStatus.UNAVAILABLE.value, "UNAVAILABLE")
        self.assertEqual(ModelStatus.UNKNOWN.value, "UNKNOWN")

        self.assertEqual(ProviderStatus.HEALTHY.value, "HEALTHY")
        self.assertEqual(ProviderStatus.UNAVAILABLE.value, "UNAVAILABLE")
        self.assertEqual(ProviderStatus.UNKNOWN.value, "UNKNOWN")

        self.assertEqual(Freshness.FRESH.value, "FRESH")
        self.assertEqual(Freshness.STALE.value, "STALE")
        self.assertEqual(Freshness.UNKNOWN.value, "UNKNOWN")

        self.assertEqual(
            {e.value for e in ErrorCategory},
            {
                "AUTH",
                "RATE_LIMIT",
                "QUOTA",
                "SERVER",
                "TIMEOUT",
                "NOT_FOUND",
                "MALFORMED_RESPONSE",
                "PROBE_UNSUPPORTED",
                "UNKNOWN",
            },
        )
        self.assertEqual(PROBE_UNSUPPORTED, "PROBE_UNSUPPORTED")
        self.assertEqual(PROBE_FAILED, "PROBE_FAILED")

    def test_offline_observation_is_always_unknown_with_no_timestamp_or_latency(self):
        m_rec = observe_model_offline("openai/gpt-4")
        self.assertEqual(m_rec.model_id, "openai/gpt-4")
        self.assertEqual(m_rec.provider_id, "UNKNOWN")
        self.assertEqual(m_rec.status, ModelStatus.UNKNOWN)
        self.assertEqual(m_rec.provenance, PROVENANCE_OFFLINE)
        self.assertEqual(m_rec.freshness, Freshness.UNKNOWN)
        self.assertIsNone(m_rec.checked_at)
        self.assertIsNone(m_rec.latency_ms)
        self.assertIsNone(m_rec.error_category)

        p_rec = observe_provider_offline("openai")
        self.assertEqual(p_rec.provider_id, "openai")
        self.assertEqual(p_rec.status, ProviderStatus.UNKNOWN)
        self.assertEqual(p_rec.provenance, PROVENANCE_OFFLINE)
        self.assertEqual(p_rec.freshness, Freshness.UNKNOWN)
        self.assertIsNone(p_rec.checked_at)
        self.assertIsNone(p_rec.latency_ms)
        self.assertIsNone(p_rec.error_category)

    def test_probe_without_adapter_returns_unknown_and_probe_unsupported(self):
        m_rec = probe_model_availability("test/model", "test-provider")
        self.assertEqual(m_rec.model_id, "test/model")
        self.assertEqual(m_rec.provider_id, "test-provider")
        self.assertEqual(m_rec.status, ModelStatus.UNKNOWN)
        self.assertEqual(m_rec.provenance, PROVENANCE_UNSUPPORTED)
        self.assertEqual(m_rec.freshness, Freshness.UNKNOWN)
        self.assertEqual(m_rec.error_category, ErrorCategory.PROBE_UNSUPPORTED)
        self.assertIsNone(m_rec.checked_at)
        self.assertIsNone(m_rec.latency_ms)

        p_rec = probe_provider_health("test-provider")
        self.assertEqual(p_rec.provider_id, "test-provider")
        self.assertEqual(p_rec.status, ProviderStatus.UNKNOWN)
        self.assertEqual(p_rec.provenance, PROVENANCE_UNSUPPORTED)
        self.assertEqual(p_rec.freshness, Freshness.UNKNOWN)
        self.assertEqual(p_rec.error_category, ErrorCategory.PROBE_UNSUPPORTED)
        self.assertIsNone(p_rec.checked_at)
        self.assertIsNone(p_rec.latency_ms)

    def test_test_adapter_seam_receives_only_minimal_pure_parameters(self):
        received = []

        def fake_model_adapter(model_id, provider_id, timeout, payload):
            received.append((model_id, provider_id, timeout, payload))
            return ModelAvailabilityRecord(
                model_id=model_id,
                provider_id=provider_id,
                status=ModelStatus.AVAILABLE,
                provenance=PROVENANCE_PROBE,
                freshness=Freshness.FRESH,
                checked_at=datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc),
                latency_ms=42.5,
            )

        res = probe_model_availability(
            "my-model", "my-provider", timeout_seconds=10.0, adapter=fake_model_adapter
        )
        self.assertEqual(len(received), 1)
        self.assertEqual(
            received[0], ("my-model", "my-provider", 10.0, "EMPTY_PROBE_PAYLOAD")
        )
        self.assertEqual(res.status, ModelStatus.AVAILABLE)
        self.assertEqual(res.freshness, Freshness.FRESH)
        self.assertEqual(res.latency_ms, 42.5)
        self.assertEqual(
            res.checked_at, datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)
        )

    def test_provider_probe_adapter_seam(self):
        received = []

        def fake_provider_adapter(provider_id, timeout, payload):
            received.append((provider_id, timeout, payload))
            return ProviderHealthRecord(
                provider_id=provider_id,
                status=ProviderStatus.HEALTHY,
                provenance=PROVENANCE_PROBE,
                freshness=Freshness.FRESH,
                checked_at=datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc),
                latency_ms=15.0,
            )

        res = probe_provider_health(
            "my-provider", timeout_seconds=3.0, adapter=fake_provider_adapter
        )
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0], ("my-provider", 3.0, "EMPTY_PROBE_PAYLOAD"))
        self.assertEqual(res.status, ProviderStatus.HEALTHY)
        self.assertEqual(res.freshness, Freshness.FRESH)
        self.assertEqual(res.latency_ms, 15.0)

    def test_timeout_validation(self):
        self.assertEqual(validate_timeout(5), 5.0)
        self.assertEqual(validate_timeout(0.5), 0.5)
        self.assertEqual(validate_timeout(300), 300.0)

        for invalid in (0, -1, -0.1, 300.1, 1000, float("nan"), float("inf"), float("-inf")):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    validate_timeout(invalid)

        for invalid_type in (None, "5", [5], True, False):
            with self.subTest(invalid_type=invalid_type):
                with self.assertRaises(TypeError):
                    validate_timeout(invalid_type)

    def test_safe_string_validation_on_records(self):
        # Empty string and whitespace-only string
        for empty_or_ws in ("", "   ", "	", " "):
            with self.subTest(empty_or_ws=empty_or_ws):
                with self.assertRaises(ValueError):
                    ModelAvailabilityRecord(
                        model_id=empty_or_ws,
                        provider_id="p",
                        status=ModelStatus.UNKNOWN,
                        provenance=PROVENANCE_OFFLINE,
                    )
        # Non-empty surrounding whitespace is preserved on model_id
        rec_ws = ModelAvailabilityRecord(
            model_id=" provider/model ",
            provider_id="p",
            status=ModelStatus.UNKNOWN,
            provenance=PROVENANCE_OFFLINE,
        )
        self.assertEqual(rec_ws.model_id, " provider/model ")
        # Leading/trailing whitespace on provider_id/provenance
        with self.assertRaises(ValueError):
            ProviderHealthRecord(
                provider_id=" provider ",
                status=ProviderStatus.UNKNOWN,
                provenance=PROVENANCE_OFFLINE,
            )
        with self.assertRaises(ValueError):
            ModelAvailabilityRecord(
                model_id="model",
                provider_id=" provider ",
                status=ModelStatus.UNKNOWN,
                provenance=PROVENANCE_OFFLINE,
            )
        with self.assertRaises(ValueError):
            ModelAvailabilityRecord(
                model_id="model",
                provider_id="p",
                status=ModelStatus.UNKNOWN,
                provenance=" provenance ",
            )
        # Control / escape characters / ANSI
        for bad in ("model\nname", "model\x00name", "model\x1b[31mname", "model\rname"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    ModelAvailabilityRecord(
                        model_id=bad,
                        provider_id="p",
                        status=ModelStatus.UNKNOWN,
                        provenance=PROVENANCE_OFFLINE,
                    )
                with self.assertRaises(ValueError):
                    ProviderHealthRecord(
                        provider_id=bad,
                        status=ProviderStatus.UNKNOWN,
                        provenance=PROVENANCE_OFFLINE,
                    )

        # Non-string types
        for non_str in (123, None, True):
            with self.subTest(non_str=non_str):
                with self.assertRaises(TypeError):
                    ModelAvailabilityRecord(
                        model_id=non_str,
                        provider_id="p",
                        status=ModelStatus.UNKNOWN,
                        provenance=PROVENANCE_OFFLINE,
                    )

    def test_detail_field_validation(self):
        # Empty string is allowed
        rec = ModelAvailabilityRecord(
            model_id="m",
            provider_id="p",
            status=ModelStatus.UNKNOWN,
            provenance=PROVENANCE_OFFLINE,
            detail="",
        )
        self.assertEqual(rec.detail, "")

        # Detail with control / newline / ESC / NUL rejected
        for bad_detail in ("error\nline2", "error\x00null", "error\x1b[0m", "error\rreturn"):
            with self.subTest(bad_detail=bad_detail):
                with self.assertRaises(ValueError):
                    ModelAvailabilityRecord(
                        model_id="m",
                        provider_id="p",
                        status=ModelStatus.UNKNOWN,
                        provenance=PROVENANCE_OFFLINE,
                        detail=bad_detail,
                    )
                with self.assertRaises(ValueError):
                    ProviderHealthRecord(
                        provider_id="p",
                        status=ProviderStatus.UNKNOWN,
                        provenance=PROVENANCE_OFFLINE,
                        detail=bad_detail,
                    )

        # Over-length detail rejected
        with self.assertRaises(ValueError):
            ModelAvailabilityRecord(
                model_id="m",
                provider_id="p",
                status=ModelStatus.UNKNOWN,
                provenance=PROVENANCE_OFFLINE,
                detail="a" * 2049,
            )

    def test_freshness_validation_and_rejection(self):
        # Non-enum freshness rejected
        with self.assertRaises(TypeError):
            ModelAvailabilityRecord(
                model_id="m",
                provider_id="p",
                status=ModelStatus.UNKNOWN,
                provenance=PROVENANCE_OFFLINE,
                freshness="FRESH",  # not Enum
            )
        with self.assertRaises(TypeError):
            ProviderHealthRecord(
                provider_id="p",
                status=ProviderStatus.UNKNOWN,
                provenance=PROVENANCE_OFFLINE,
                freshness="FRESH",  # not Enum
            )

    def test_latency_ms_validation_types_and_values(self):
        # bool rejected
        with self.assertRaises(TypeError):
            ModelAvailabilityRecord(
                model_id="m",
                provider_id="p",
                status=ModelStatus.UNKNOWN,
                provenance="custom-probe",
                latency_ms=True,
            )
        # NaN and Inf rejected
        for bad_lat in (float("nan"), float("inf"), float("-inf"), -1.0):
            with self.subTest(bad_lat=bad_lat):
                with self.assertRaises(ValueError):
                    ModelAvailabilityRecord(
                        model_id="m",
                        provider_id="p",
                        status=ModelStatus.UNKNOWN,
                        provenance="custom-probe",
                        latency_ms=bad_lat,
                    )

    def test_active_probe_available_healthy_invariants(self):
        # AVAILABLE requires FRESH, checked_at (tz-aware), latency_ms (non-negative)
        with self.assertRaises(ValueError):
            ModelAvailabilityRecord(
                model_id="m",
                provider_id="p",
                status=ModelStatus.AVAILABLE,
                provenance=PROVENANCE_PROBE,
                freshness=Freshness.STALE,  # not FRESH
                checked_at=datetime.now(timezone.utc),
                latency_ms=10.0,
            )
        with self.assertRaises(ValueError):
            ModelAvailabilityRecord(
                model_id="m",
                provider_id="p",
                status=ModelStatus.AVAILABLE,
                provenance=PROVENANCE_PROBE,
                freshness=Freshness.FRESH,
                checked_at=None,  # missing checked_at
                latency_ms=10.0,
            )
        with self.assertRaises(ValueError):
            ModelAvailabilityRecord(
                model_id="m",
                provider_id="p",
                status=ModelStatus.AVAILABLE,
                provenance=PROVENANCE_PROBE,
                freshness=Freshness.FRESH,
                checked_at=datetime.now(timezone.utc),
                latency_ms=None,  # missing latency_ms
            )

        # HEALTHY requires FRESH, checked_at (tz-aware), latency_ms (non-negative)
        with self.assertRaises(ValueError):
            ProviderHealthRecord(
                provider_id="p",
                status=ProviderStatus.HEALTHY,
                provenance=PROVENANCE_PROBE,
                freshness=Freshness.UNKNOWN,  # not FRESH
                checked_at=datetime.now(timezone.utc),
                latency_ms=10.0,
            )

    def test_offline_and_probe_unsupported_invariants(self):
        # Offline provenance must not have checked_at or latency_ms, must be UNKNOWN status & freshness
        with self.assertRaises(ValueError):
            ModelAvailabilityRecord(
                model_id="m",
                provider_id="p",
                status=ModelStatus.AVAILABLE,
                provenance=PROVENANCE_OFFLINE,
                freshness=Freshness.FRESH,
                checked_at=datetime.now(timezone.utc),
                latency_ms=10.0,
            )
        with self.assertRaises(ValueError):
            ModelAvailabilityRecord(
                model_id="m",
                provider_id="p",
                status=ModelStatus.UNKNOWN,
                provenance=PROVENANCE_OFFLINE,
                freshness=Freshness.FRESH,  # must be UNKNOWN
            )
        with self.assertRaises(ValueError):
            ModelAvailabilityRecord(
                model_id="m",
                provider_id="p",
                status=ModelStatus.UNKNOWN,
                provenance=PROVENANCE_UNSUPPORTED,
                freshness=Freshness.UNKNOWN,
                latency_ms=5.0,  # must not have latency_ms
            )

    def test_adapter_result_invariants_checked_by_probe_functions(self):
        # Adapter returning wrong object type
        def bad_type_adapter(m, p, t, payload):
            return "not a record"

        with self.assertRaises(TypeError):
            probe_model_availability("m", "p", adapter=bad_type_adapter)

        # Adapter returning mismatched model_id or provider_id
        def mismatched_model_adapter(m, p, t, payload):
            return ModelAvailabilityRecord(
                model_id="other-model",
                provider_id=p,
                status=ModelStatus.UNKNOWN,
                provenance=PROVENANCE_PROBE,
            )

        with self.assertRaises(ValueError):
            probe_model_availability("m", "p", adapter=mismatched_model_adapter)

        def mismatched_provider_adapter(p, t, payload):
            return ProviderHealthRecord(
                provider_id="other-provider",
                status=ProviderStatus.UNKNOWN,
                provenance=PROVENANCE_PROBE,
            )

        with self.assertRaises(ValueError):
            probe_provider_health("p", adapter=mismatched_provider_adapter)

    def test_checked_at_converts_aware_timestamps_to_utc(self):
        # Positive offset (+05:30)
        tz_pos = timezone(timedelta(hours=5, minutes=30))
        dt_pos = datetime(2026, 8, 25, 17, 30, tzinfo=tz_pos)
        rec_pos = ModelAvailabilityRecord(
            model_id="test/model",
            provider_id="test-provider",
            status=ModelStatus.AVAILABLE,
            provenance=PROVENANCE_PROBE,
            freshness=Freshness.FRESH,
            checked_at=dt_pos,
            latency_ms=10.0,
        )
        self.assertEqual(rec_pos.checked_at, datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc))
        self.assertEqual(rec_pos.checked_at.tzinfo, timezone.utc)

        # Negative offset (-08:00)
        tz_neg = timezone(timedelta(hours=-8))
        dt_neg = datetime(2026, 8, 25, 4, 0, tzinfo=tz_neg)
        rec_neg = ProviderHealthRecord(
            provider_id="test-provider",
            status=ProviderStatus.HEALTHY,
            provenance=PROVENANCE_PROBE,
            freshness=Freshness.FRESH,
            checked_at=dt_neg,
            latency_ms=10.0,
        )
        self.assertEqual(rec_neg.checked_at, datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc))
        self.assertEqual(rec_neg.checked_at.tzinfo, timezone.utc)

        # Naive timestamp remains rejected
        with self.assertRaises(ValueError):
            ModelAvailabilityRecord(
                model_id="test/model",
                provider_id="test-provider",
                status=ModelStatus.AVAILABLE,
                provenance=PROVENANCE_PROBE,
                freshness=Freshness.FRESH,
                checked_at=datetime(2026, 8, 25, 12, 0),
                latency_ms=10.0,
            )
        with self.assertRaises(ValueError):
            ProviderHealthRecord(
                provider_id="test-provider",
                status=ProviderStatus.HEALTHY,
                provenance=PROVENANCE_PROBE,
                freshness=Freshness.FRESH,
                checked_at=datetime(2026, 8, 25, 12, 0),
                latency_ms=10.0,
            )

    def test_sanitization(self):
        self.assertEqual(sanitize_identifier("openai/gpt-4"), "openai/gpt-4")
        self.assertEqual(sanitize_identifier("model\nwith\nnewlines"), "model?with?newlines")
        self.assertEqual(sanitize_identifier("model\r\x00control"), "model??control")
        self.assertEqual(sanitize_identifier("path\\with\\backslash"), "path\\\\with\\\\backslash")
        self.assertEqual(sanitize_identifier(123), "")

        # Deterministic bounding at <=384 characters with stable truncation marker
        long_str = "a" * 600
        sanitized_long = sanitize_identifier(long_str)
        self.assertEqual(len(sanitized_long), 384)
        self.assertTrue(sanitized_long.endswith("..."))
        self.assertEqual(sanitized_long, "a" * 381 + "...")

        # Escaped backslashes expand first, then truncate to <=384 with marker
        slash_str = chr(92) * 300
        sanitized_slash = sanitize_identifier(slash_str)
        self.assertEqual(len(sanitized_slash), 384)
        self.assertTrue(sanitized_slash.endswith("..."))
        self.assertEqual(sanitized_slash, (chr(92) * 381) + "...")


if __name__ == "__main__":
    unittest.main()
