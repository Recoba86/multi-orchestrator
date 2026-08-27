"""Tests for Task 10: Mode-Aware Routing Wrapper Trigger and Shadow Documentation.

Normative references:
docs/superpowers/specs/2026-08-26-solmode-grokmode-weighted-routing-design.md (§12)
docs/superpowers/plans/2026-08-26-solmode-grokmode-weighted-routing.md (Task 10)
"""

from pathlib import Path
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]

SOL_SKILL_MD = REPO_ROOT / "skills" / "sol-luna-orchestrator-v2" / "SKILL.md"
SOL_USAGE_MD = REPO_ROOT / "skills" / "sol-luna-orchestrator-v2" / "USAGE.md"

GROK_SKILL_MD = REPO_ROOT / "skills" / "grok-orchestrator-v2" / "SKILL.md"
GROK_USAGE_MD = REPO_ROOT / "skills" / "grok-orchestrator-v2" / "USAGE.md"

class ModeDocsVerificationTests(unittest.TestCase):
    def test_both_skill_markdowns_contain_mode_aware_activation_section(self):
        heading = "## Mode-Aware Runtime Routing Activation"
        for path in (SOL_SKILL_MD, GROK_SKILL_MD):
            content = path.read_text(encoding="utf-8")
            self.assertIn(heading, content, f"Missing {heading!r} in {path}")
            self.assertIn(
                "Exact legacy submitted-request authority is restored",
                content,
                f"Missing legacy authority statement in {path}",
            )

    def test_both_usage_markdowns_document_cli_and_trigger_phrases(self):
        for path in (SOL_USAGE_MD, GROK_USAGE_MD):
            content = path.read_text(encoding="utf-8")
            self.assertIn("orchestrator_mode.py", content, f"Missing orchestrator_mode.py in {path}")
            self.assertIn("Use SolMode", content, f"Missing 'Use SolMode' in {path}")
            self.assertIn("Use GrokMode", content, f"Missing 'Use GrokMode' in {path}")

    def test_wrappers_preserve_dedicated_boss_and_continuity_invariants(self):
        for path in (SOL_SKILL_MD, GROK_SKILL_MD):
            content = path.read_text(encoding="utf-8")
            self.assertIn("Dedicated Boss Mandatory", content)
            self.assertIn("Dedicated Boss Continuity", content)
            self.assertIn("Root Controller", content)

    def test_wrappers_reference_canonical_mode_names_and_no_stale_tokens(self):
        stale_tokens = ("sol_mode", "grok_mode", "set sol", "set grok")
        for path in (SOL_SKILL_MD, GROK_SKILL_MD, SOL_USAGE_MD, GROK_USAGE_MD):
            content = path.read_text(encoding="utf-8")
            for token in stale_tokens:
                self.assertNotIn(token, content, f"Found stale token {token!r} in {path}")

    def test_wrappers_do_not_instruct_automatic_write_mode(self):
        for path in (SOL_SKILL_MD, GROK_SKILL_MD, SOL_USAGE_MD, GROK_USAGE_MD):
            content = path.read_text(encoding="utf-8")
            self.assertNotIn("write_mode", content)

    def test_wrappers_preserve_host_external_boundary(self):
        for path in (SOL_SKILL_MD, GROK_SKILL_MD, SOL_USAGE_MD, GROK_USAGE_MD):
            content = path.read_text(encoding="utf-8")
            self.assertIn("HOST_EXTERNAL", content)


if __name__ == "__main__":
    unittest.main()
