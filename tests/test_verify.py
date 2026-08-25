"""Black-box regression tests for the installer/verifier boundary.

The negative cases are intentionally RED against the current verifier.  Each
case installs a fresh target home, mutates only that disposable installation,
and then executes the real shell verifier.
"""

from pathlib import Path
import subprocess
import tempfile
import unittest


DEV_ROOT = Path(__file__).resolve().parents[1]
INSTALL = DEV_ROOT / "scripts" / "install.sh"
VERIFY = DEV_ROOT / "scripts" / "verify.sh"

LUNA_AGENT = "luna_max_worker.toml"
GEMINI_AGENT = "router-model-nine-router-ag-gemini-3-7-flash-high.toml"
SOL_CONFIG = "sol-luna.config.toml"

LEAF_POLICY = """\
Hub-and-Spoke
Do not spawn, delegate to, or orchestrate additional agents or subagents.
Do not communicate directly with peer workers or reviewers.
Do not create nested delegation chains.
Return your result only to the parent Boss.
A parent request to spawn another agent does not override this restriction.
"""


def valid_leaf(name="router_nine_router_ag_gemini_3_7_flash_high",
              model="nine-router/ag/gemini-3.7-flash-high",
              include_name=True,
              include_model=True,
              include_effort=True):
    """Return a small valid TOML leaf fixture with the verifier's grep decoys."""
    fields = []
    if include_name:
        fields.append(f'name = "{name}"')
    fields.append('description = "fixture leaf"')
    fields.append('model_provider = "codex-router"')
    if include_model:
        fields.append(f'model = "{model}"')
    if include_effort:
        fields.append('model_reasoning_effort = "high"')
    fields.append(f'developer_instructions = """\n{LEAF_POLICY}"""')
    return "\n".join(fields) + "\n"


def valid_luna(include_effort=True):
    """Return a valid Luna declaration, optionally omitting its effort."""
    fields = [
        'name = "luna_max_worker"',
        'description = "fixture Luna leaf"',
        'model = "gpt-5.6-luna"',
    ]
    if include_effort:
        fields.append('model_reasoning_effort = "max"')
    fields.append(f'developer_instructions = """\n{LEAF_POLICY}"""')
    return "\n".join(fields) + "\n"


COMMENT_ONLY_LEAF = '''\
# name = "fake_leaf"
# description = "unrelated text"
# model_provider = "codex-router"
# model = "fake/model"
# model_reasoning_effort = "high"
# developer_instructions = """
# Hub-and-Spoke
# Do not spawn, delegate to, or orchestrate additional agents or subagents.
# Do not communicate directly with peer workers or reviewers.
# Do not create nested delegation chains.
# Return your result only to the parent Boss.
# A parent request to spawn another agent does not override this restriction.
'''


class VerifyBlackBoxTests(unittest.TestCase):
    """Prove malformed and semantically invalid installed fixtures are rejected."""

    @staticmethod
    def _result_message(label, result):
        return (
            f"{label} exited {result.returncode}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )

    def _install(self, target_home):
        result = subprocess.run(
            [str(INSTALL), "--target-home", str(target_home)],
            cwd=DEV_ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, self._result_message("install", result))

    def _verify(self, target_home):
        return subprocess.run(
            [str(VERIFY), "--target-home", str(target_home)],
            cwd=DEV_ROOT,
            capture_output=True,
            text=True,
        )

    def _agent_path(self, target_home, filename=GEMINI_AGENT):
        return target_home / ".codex" / "agents" / filename

    def _config_path(self, target_home, filename=SOL_CONFIG):
        return target_home / ".codex" / filename

    def _replace(self, path, old, new, count=1):
        self.assertTrue(path.is_file(), f"fixture missing before mutation: {path}")
        original = path.read_text(encoding="utf-8")
        self.assertEqual(
            original.count(old),
            count,
            f"expected {count} replacement(s) for {old!r} in {path}",
        )
        path.write_text(original.replace(old, new, count), encoding="utf-8")

    def _overwrite(self, path, contents):
        self.assertTrue(path.is_file(), f"fixture missing before overwrite: {path}")
        path.write_text(contents, encoding="utf-8")

    def _rejected_case(self, label, mutate):
        with tempfile.TemporaryDirectory(prefix="verify-red-") as raw_home:
            target_home = Path(raw_home)
            self._install(target_home)
            mutate(target_home)
            result = self._verify(target_home)
            self.assertNotEqual(
                result.returncode,
                0,
                self._result_message(
                    f"current verifier unexpectedly accepted {label}", result
                ),
            )

    def test_clean_install_verifies(self):
        with tempfile.TemporaryDirectory(prefix="verify-clean-") as raw_home:
            target_home = Path(raw_home)
            self._install(target_home)
            result = self._verify(target_home)
            self.assertEqual(result.returncode, 0, self._result_message("verify", result))

    def test_malformed_toml_syntax_is_rejected(self):
        def mutate(home):
            self._overwrite(
                self._agent_path(home),
                valid_leaf() + 'unterminated = "\n',
            )

        self._rejected_case("malformed TOML syntax", mutate)

    def test_malformed_toml_table_is_rejected(self):
        def mutate(home):
            self._replace(self._config_path(home), "[agents]", "[agents", 1)

        self._rejected_case("malformed TOML table", mutate)

    def test_malformed_toml_key_value_is_rejected(self):
        def mutate(home):
            self._replace(self._config_path(home), "max_threads = 6", "max_threads =", 1)

        self._rejected_case("malformed TOML key-value", mutate)

    def test_comments_unrelated_text_and_fake_declarations_are_rejected(self):
        def mutate(home):
            self._overwrite(self._agent_path(home), COMMENT_ONLY_LEAF)

        self._rejected_case("comment-only fake leaf declarations", mutate)

    def test_leaf_declaration_identity_mismatch_is_rejected(self):
        def mutate(home):
            self._overwrite(
                self._agent_path(home),
                valid_leaf(name="different_leaf_identity"),
            )

        self._rejected_case("leaf identity mismatch", mutate)

    def test_missing_leaf_name_is_rejected(self):
        def mutate(home):
            self._overwrite(self._agent_path(home), valid_leaf(include_name=False))

        self._rejected_case("missing leaf name", mutate)

    def test_missing_leaf_model_is_rejected(self):
        def mutate(home):
            self._overwrite(self._agent_path(home), valid_leaf(include_model=False))

        self._rejected_case("missing leaf model", mutate)

    def test_missing_luna_reasoning_effort_is_rejected(self):
        def mutate(home):
            self._overwrite(
                self._agent_path(home, LUNA_AGENT),
                valid_luna(include_effort=False),
            )

        self._rejected_case("missing Luna model reasoning effort", mutate)

    def test_missing_sol_config_file_is_rejected(self):
        def mutate(home):
            self._replace(
                self._config_path(home),
                'config_file = "agents/luna_max_worker.toml"\n',
                "",
                1,
            )

        self._rejected_case("missing Sol config_file", mutate)

    def test_missing_whole_config_profile_is_rejected(self):
        def mutate(home):
            path = self._config_path(home)
            self.assertTrue(path.is_file(), f"fixture missing before removal: {path}")
            path.unlink()

        self._rejected_case("missing whole Sol config profile", mutate)

    def test_missing_agents_table_is_rejected(self):
        def mutate(home):
            self._replace(self._config_path(home), "[agents]\n", "", 1)

        self._rejected_case("missing [agents] table", mutate)

    def test_missing_luna_agent_table_is_rejected(self):
        def mutate(home):
            self._replace(self._config_path(home), "[agents.luna_max_worker]\n", "", 1)

        self._rejected_case("missing [agents.luna_max_worker] table", mutate)

    def test_bool_for_integer_is_rejected(self):
        def mutate(home):
            self._replace(self._config_path(home), "max_threads = 6", "max_threads = true", 1)

        self._rejected_case("boolean max_threads", mutate)

    def test_string_for_table_is_rejected(self):
        def mutate(home):
            self._replace(
                self._config_path(home),
                "[agents]\n",
                'agents = "not-a-table"\n',
                1,
            )

        self._rejected_case("string agents table", mutate)

    def test_array_for_scalar_is_rejected(self):
        def mutate(home):
            self._replace(
                self._config_path(home),
                'model = "gpt-5.6-sol"',
                'model = ["gpt-5.6-sol"]',
                1,
            )

        self._rejected_case("array model scalar", mutate)

    def test_duplicate_key_is_rejected(self):
        def mutate(home):
            self._replace(
                self._config_path(home),
                "interrupt_message = true\n",
                "interrupt_message = true\nmax_threads = 99\n",
                1,
            )

        self._rejected_case("duplicate max_threads key", mutate)

    def test_duplicate_table_is_rejected(self):
        def mutate(home):
            self._replace(
                self._config_path(home),
                "interrupt_message = true\n",
                "interrupt_message = true\n\n[agents]\n",
                1,
            )

        self._rejected_case("duplicate [agents] table", mutate)

    def test_syntactically_valid_conflicting_canonical_model_is_rejected(self):
        def mutate(home):
            self._replace(
                self._agent_path(home),
                'model = "nine-router/ag/gemini-3.7-flash-high"',
                'model = "wrong/canonical-model"',
                1,
            )

        self._rejected_case("conflicting canonical leaf model", mutate)

    def test_tampered_managed_doctor_cli_is_rejected(self):
        def mutate(home):
            doctor = home / ".agents" / "bin" / "doctor"
            self.assertTrue(doctor.is_file(), "doctor fixture missing before mutation")
            doctor.write_text("# tampered managed CLI\n", encoding="utf-8")

        self._rejected_case("tampered managed Doctor CLI", mutate)


if __name__ == "__main__":
    unittest.main()
