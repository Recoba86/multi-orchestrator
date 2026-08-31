"""Granular model-family independence: Sol and Luna are distinct families."""

from pathlib import Path
import sys
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from core.model_discovery import derive_model_family


class CognitiveIndependenceTests(unittest.TestCase):
    def test_sol_and_luna_are_distinct_families(self):
        self.assertEqual(derive_model_family("gpt-5.6-sol"), "GPT_5_6_SOL")
        self.assertEqual(derive_model_family("gpt-5.6-luna"), "GPT_5_6_LUNA")
        self.assertNotEqual(derive_model_family("gpt-5.6-sol"), derive_model_family("gpt-5.6-luna"))

    def test_same_grok_family_across_routes(self):
        self.assertEqual(
            derive_model_family("nine-router/gcli/grok-4.6-high"),
            derive_model_family("nine-router/cu/cursor-grok-4.6-high"),
        )
        self.assertEqual(derive_model_family("nine-router/gcli/grok-4.6-high"), "GROK_4_6")

    def test_gemini_medium_and_high_share_family(self):
        self.assertEqual(
            derive_model_family("nine-router/ag/gemini-3.7-flash-high"),
            derive_model_family("nine-router/ag/gemini-3.7-flash-medium"),
        )

    def test_terra_is_distinct_gpt_lineage(self):
        self.assertEqual(derive_model_family("gpt-5.6-terra"), "GPT_5_6_TERRA")
        self.assertNotEqual(derive_model_family("gpt-5.6-terra"), derive_model_family("gpt-5.6-sol"))


if __name__ == "__main__":
    unittest.main()
