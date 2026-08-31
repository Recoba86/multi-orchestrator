"""Tests for Auto Team mode-aware routing documentation."""

from pathlib import Path
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]

AUTOTEAM_SKILL_MD = REPO_ROOT / "skills" / "autoteam" / "SKILL.md"
AUTOTEAM_USAGE_MD = REPO_ROOT / "skills" / "autoteam" / "USAGE.md"


class ModeDocsVerificationTests(unittest.TestCase):
    def test_skill_markdown_contains_mode_independent_activation_section(self):
        content = AUTOTEAM_SKILL_MD.read_text(encoding="utf-8")
        self.assertIn("## Runtime Routing Activation", content)
        self.assertIn("SolMode and GrokMode use the same operator-selected Auto Team chains", content)
        self.assertIn("Exact legacy submitted-request authority is restored", content)
        self.assertIn("$autoteam", content)
    def test_skill_requires_explicit_native_host_binding(self):
        content = AUTOTEAM_SKILL_MD.read_text(encoding="utf-8")
        self.assertIn("spawn_agent({", content)
        self.assertIn("model: <validated requested_model>", content)
        self.assertIn("reasoning_effort: <validated requested_effort>", content)
        self.assertIn("HOST_MODEL_BINDING_ERROR", content)
        self.assertIn("parent/default model", content)
        self.assertIn("effective_model", content)
        self.assertIn("UNPROVEN", content)
        self.assertIn("^[a-z0-9_]+$", content)
        self.assertIn("autoteam_scout_01_mission_1787106000", content)
        self.assertIn("HOST_AGENT_NAME_INVALID", content)
        self.assertIn("session_meta.base_instructions.provenance", content)
        self.assertIn("turn_context.model", content)
        self.assertNotIn("task_name: <child task name>", content)

    def test_usage_markdown_documents_cli_and_trigger_phrases(self):
        content = AUTOTEAM_USAGE_MD.read_text(encoding="utf-8")
        self.assertIn("orchestrator-routing", content)
        self.assertIn("Use SolMode", content)
        self.assertIn("Use GrokMode", content)
        self.assertIn("$autoteam", content)

    def test_wrapper_preserves_dedicated_boss_and_continuity_invariants(self):
        content = AUTOTEAM_SKILL_MD.read_text(encoding="utf-8")
        self.assertIn("Dedicated Boss Mandatory", content)
        self.assertIn("Dedicated Boss Continuity", content)
        self.assertIn("Root Controller", content)

    def test_wrapper_references_canonical_mode_names_and_no_stale_tokens(self):
        stale_tokens = ("sol_mode", "grok_mode", "set sol", "set grok")
        for path in (AUTOTEAM_SKILL_MD, AUTOTEAM_USAGE_MD):
            content = path.read_text(encoding="utf-8")
            for token in stale_tokens:
                self.assertNotIn(token, content, f"Found stale token {token!r} in {path}")
        self.assertIn("does not replace the canonical Auto Team model chains", AUTOTEAM_USAGE_MD.read_text(encoding="utf-8"))
        self.assertNotIn("zero GPT Plus throughput", AUTOTEAM_USAGE_MD.read_text(encoding="utf-8"))

    def test_wrapper_does_not_instruct_automatic_write_mode(self):
        for path in (AUTOTEAM_SKILL_MD, AUTOTEAM_USAGE_MD):
            content = path.read_text(encoding="utf-8")
            self.assertNotIn("write_mode", content)

    def test_wrapper_preserves_host_external_boundary(self):
        content = AUTOTEAM_SKILL_MD.read_text(encoding="utf-8")
        self.assertIn("HOST_EXTERNAL", content)


if __name__ == "__main__":
    unittest.main()
