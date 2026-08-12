"""The anti-fabrication guard.

Throughline's entire claim is that every figure it displays was computed from a
live public source. That claim is worth nothing as a promise; it has to be
enforced, or it decays the first time somebody pastes a number into a template
to make a screenshot look better.

Two properties are checked:

1. No judge-facing template renders a hardcoded statistic. Numbers reach the
   page through template variables or they do not reach it at all.
2. No divergence figure is hardcoded in the engine.

**This guard fails, it does not skip.** A conditionally-skipped test is a false
green: the run is honest and the assertion simply never executes, under a green
check, for the life of the repo. If the file set cannot be resolved, that is a
failure, not a pass.

The file set is resolved with `git ls-files --cached --others --exclude-standard`
so that **untracked files are included**. A guard scoped to tracked files alone
has a blind spot exactly the size of "the file I am about to add": it is
invisible locally, becomes visible the moment it is committed, and fails in CI
on a change that passed every local run.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# Figures that are configuration or presentation, not measurements: thresholds
# the engine is defined by, CSS, and HTTP status codes.
ALLOWED_LITERALS = {
    "0",
    "1",
    "2",
    "3",
    "4",
    "5",
    "10",
    "100",
    "200",
    "404",
    "500",
    "503",
}


def repo_files(suffixes: tuple[str, ...]) -> list[Path]:
    """Every file git knows about *plus* untracked, gitignored excluded."""
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.fail(
            "Could not resolve the file set via git; refusing to report a pass. "
            f"stderr: {result.stderr.strip()}"
        )
    files = [ROOT / line for line in result.stdout.splitlines() if line.strip()]
    return [f for f in files if f.suffix in suffixes and f.is_file()]


class TestGuardIsNotVacuous:
    """The guard must be capable of failing, or it proves nothing.

    Without this, a bug that made `repo_files` return an empty list would turn
    every assertion below into a silent pass, and the suite would go green
    precisely when it had stopped checking anything.
    """

    def test_it_actually_sees_files(self):
        assert repo_files((".html",)), "resolved zero templates, guard would be vacuous"
        assert repo_files((".py",)), "resolved zero python files, guard would be vacuous"

    def test_it_sees_untracked_files(self, tmp_path):
        """A file that is not yet committed must still be in scope."""
        scratch = ROOT / "_guard_scope_probe.html"
        try:
            scratch.write_text("<p>probe</p>")
            assert scratch in repo_files((".html",)), (
                "untracked file was not in scope; the guard has a blind spot "
                "the size of every file about to be added"
            )
        finally:
            scratch.unlink(missing_ok=True)

    def test_it_detects_a_planted_violation(self):
        """Mutation check: a known-bad string must be caught by the pattern."""
        planted = '<div class="v">51.9%</div>'
        assert STAT_PATTERN.search(planted), "guard pattern cannot catch a planted statistic"


# A rendered statistic: a number with a decimal point or thousands separator, or
# a percentage, sitting in text rather than arriving via {{ }}.
STAT_PATTERN = re.compile(r">\s*\d[\d,]*\.?\d*\s*%?\s*<")


class TestTemplatesRenderNoHardcodedStatistics:
    def test_no_statistic_is_baked_into_a_template(self):
        offenders: list[str] = []
        for path in repo_files((".html",)):
            for lineno, line in enumerate(path.read_text().splitlines(), start=1):
                if "{{" in line or "{%" in line:
                    continue  # a computed value, which is the whole point
                for match in STAT_PATTERN.finditer(line):
                    literal = match.group(0).strip("><% \t")
                    if literal in ALLOWED_LITERALS or not literal:
                        continue
                    offenders.append(f"{path.relative_to(ROOT)}:{lineno}: {literal!r}")

        assert not offenders, (
            "Hardcoded statistics found in judge-facing templates. Every figure "
            "must render from a computed value:\n  " + "\n  ".join(offenders)
        )


class TestEngineDoesNotCarryFabricatedFigures:
    def test_no_divergence_totals_are_hardcoded(self):
        """Guards against a measured figure being frozen into the code.

        A number pasted into the engine stops tracking reality the moment the
        city republishes, and if it ever reaches an assertion the suite will
        then defend it: correcting the code fails CI and reads as a regression.
        """
        banned = re.compile(r"(divergence_rate|divergences_total|entities_resolved)\s*=\s*[\d.]+")
        offenders = [
            f"{path.relative_to(ROOT)}:{lineno}"
            for path in repo_files((".py",))
            if "tests/" not in str(path.relative_to(ROOT))
            for lineno, line in enumerate(path.read_text().splitlines(), start=1)
            if banned.search(line)
        ]
        assert not offenders, "Measured figures assigned as constants: " + ", ".join(offenders)


class TestModelsCannotProduceNumbers:
    def test_adjudication_prompt_forbids_inventing_facts(self):
        """The panel judges conflicts; it never counts or scores."""
        source = (ROOT / "src/throughline/core/adjudicate.py").read_text()
        assert "NOT producing any count" in source
        assert "must NOT invent any fact" in source

    def test_adjudication_is_deletable(self):
        """The API-deletion test, enforced.

        The deterministic engine must not *import* the model layer. If it ever
        does, the verdict has quietly become dependent on a vendor API and the
        product has become a wrapper around somebody else's model.

        Checks import statements specifically, not the word: prose in a
        docstring explaining that models are kept out of the verdict is exactly
        the documentation we want, and a substring match would ban it.
        """
        import_pattern = re.compile(
            r"^\s*(?:from\s+[\w.]*adjudicate|import\s+[\w.]*adjudicate|"
            r"from\s+[\w.]+\s+import\s+.*\badjudicate\b)",
            re.MULTILINE,
        )
        for module in ("diverge.py", "resolve.py", "normalize.py", "models.py", "pipeline.py"):
            source = (ROOT / "src/throughline/core" / module).read_text()
            assert not import_pattern.search(source), (
                f"core/{module} imports the model layer; the deterministic verdict "
                "must stand on its own with every model deleted"
            )

    def test_deletion_check_is_not_vacuous(self):
        """The pattern must actually catch a real import line."""
        import_pattern = re.compile(
            r"^\s*(?:from\s+[\w.]*adjudicate|import\s+[\w.]*adjudicate|"
            r"from\s+[\w.]+\s+import\s+.*\badjudicate\b)",
            re.MULTILINE,
        )
        assert import_pattern.search("from .adjudicate import adjudicate\n")
        assert import_pattern.search("from throughline.core import adjudicate\n")
        # ...and must not fire on prose that merely mentions it.
        assert not import_pattern.search("# Models adjudicate the ambiguous tail.\n")
