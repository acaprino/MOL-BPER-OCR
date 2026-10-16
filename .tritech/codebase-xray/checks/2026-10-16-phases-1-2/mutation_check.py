"""Verify pipeline characterization tests against in-memory regressions.

Each subprocess imports the real dependencies, compiles one altered pipeline
module in memory, and runs the existing behavioral tests against that module.
The production source is never written or copied to another file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from types import ModuleType
from typing import Any


ROOT = Path(__file__).resolve().parents[4]
OUTPUT_DIR = Path(__file__).resolve().parent
PIPELINE_PATH = ROOT / "extraction" / "pipeline.py"
TEST_PATH = "tests/test_pipeline_postprocessing.py"
RESULT_MARKER = "MUTATION_RESULT="

MUTATIONS: dict[str, dict[str, Any]] = {
    "threshold_lowered": {
        "before": '< ANCHOR_CONF_MIN:',
        "after": '< (ANCHOR_CONF_MIN - 0.02):',
        "count": 2,
        "select": "test_an_anchor_below_threshold_is_returned_as_null",
        "behavior": "Reject anchors at confidence 0.94.",
    },
    "threshold_exclusive": {
        "before": '< ANCHOR_CONF_MIN:',
        "after": '<= ANCHOR_CONF_MIN:',
        "count": 2,
        "select": "test_an_anchor_at_threshold_takes_priority_over_the_main_value",
        "behavior": "Accept anchors at confidence 0.95.",
    },
    "ignore_early_stop": {
        "before": "if STOP_ON_ANCHOR_UNCERTAIN:",
        "after": "if False and STOP_ON_ANCHOR_UNCERTAIN:",
        "count": 1,
        "select": "test_uncertain_anchors_can_stop_before_the_main_pass",
        "behavior": "Stop after one anchor call when configured and both anchors are uncertain.",
    },
    "omit_anchor_overwrite": {
        "before": "        self._merge_anchors(result, anchors, field_sources)",
        "after": "        pass  # Simulate omitting the anchor merge.",
        "count": 1,
        "select": "test_an_anchor_at_threshold_takes_priority_over_the_main_value",
        "behavior": "Trusted anchors take priority over conflicting main values.",
    },
    "omit_main_tipo_normalization": {
        "before": "        self._postprocess_tipo(result)",
        "after": "        pass  # Simulate omitting main-pass tipo normalization.",
        "count": 1,
        "select": "test_tipo_is_normalized_from_each_header_read and CONTENT_MAIN",
        "behavior": "Normalize tipo from the main pass.",
    },
    "omit_retry_tipo_normalization": {
        "before": 'candidate["value"] = normalize_tipo(candidate.get("value"))',
        "after": 'candidate["value"] = candidate.get("value")',
        "count": 1,
        "select": "test_tipo_is_normalized_from_each_header_read and RETRY_HEADER",
        "behavior": "Normalize tipo from header retries.",
    },
    "disable_evidenze_coherence": {
        "before": 'if not is_nullish(t_evid_b.get("value")):',
        "after": 'if False and not is_nullish(t_evid_b.get("value")):',
        "count": 1,
        "select": "test_evidenze_is_repaired_from_its_tooltip",
        "behavior": "Repair null or numeric evidenze from the B tooltip.",
    },
    "disable_bmb_coherence": {
        "before": 'safe_set_field(flds, "tipo", value="BMB", confidence=t_tipo_bmb.get("confidence"))',
        "after": 'safe_set_field(flds, "tipo", confidence=t_tipo_bmb.get("confidence"))',
        "count": 1,
        "select": "test_missing_tipo_is_repaired_from_the_bmb_tooltip",
        "behavior": "Infer missing tipo BMB from its tooltip.",
    },
    "allow_off_calibration_table_replacement": {
        "before": "            if not calibrated:",
        "after": "            if False and not calibrated:",
        "count": 1,
        "select": "test_off_calibration_a_retry_cannot_replace_a_populated_subject_table",
        "behavior": "Off calibration, retries preserve a populated subject table.",
    },
}


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class _TestResults:
    """Capture pytest outcomes so a setup failure cannot count as a caught mutant."""

    def __init__(self) -> None:
        self.passed = 0
        self.skipped = 0
        self.failures: list[dict[str, str]] = []
        self.errors: list[dict[str, str]] = []

    def pytest_runtest_logreport(self, report: Any) -> None:
        if report.failed:
            detail = {"nodeid": report.nodeid, "failure": report.longreprtext}
            if report.when == "call":
                self.failures.append(detail)
            else:
                self.errors.append(detail)
        elif report.when == "call" and report.passed:
            self.passed += 1
        elif report.skipped:
            self.skipped += 1


def _run_child(mutation: str, expected_sha256: str) -> int:
    source_bytes = PIPELINE_PATH.read_bytes()
    if _digest(source_bytes) != expected_sha256:
        raise RuntimeError("Pipeline source changed during the verification run.")
    source = source_bytes.decode("utf-8")
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    if mutation != "baseline":
        spec = MUTATIONS[mutation]
        occurrences = source.count(spec["before"])
        if occurrences != spec["count"]:
            raise RuntimeError(f"Mutation {mutation}: expected {spec['count']} sites, found {occurrences}.")
        source = source.replace(spec["before"], spec["after"])

        # Import the real package first, then replace only its pipeline module.
        # Test imports and the shared VLM boundary fixture resolve to this module.
        import extraction

        mutant_module = ModuleType("extraction.pipeline")
        mutant_module.__file__ = str(PIPELINE_PATH)
        mutant_module.__package__ = "extraction"
        exec(compile(source, str(PIPELINE_PATH), "exec"), mutant_module.__dict__)
        sys.modules["extraction.pipeline"] = mutant_module
        extraction.pipeline = mutant_module

    import pytest

    results = _TestResults()
    args = [TEST_PATH, "-q", "-p", "no:cacheprovider"]
    if mutation != "baseline":
        args.extend(["-k", MUTATIONS[mutation]["select"]])
    exit_code = int(pytest.main(args, plugins=[results]))
    result = {
        "mutation": mutation,
        "exit_code": exit_code,
        "passed": results.passed,
        "skipped": results.skipped,
        "failed": len(results.failures),
        "errors": len(results.errors),
        "assertion_failures": sum("AssertionError" in item["failure"] for item in results.failures),
        "failed_tests": [item["nodeid"] for item in results.failures],
    }
    print(RESULT_MARKER + json.dumps(result), flush=True)
    return exit_code


def _launch(mutation: str, expected_sha256: str, run_number: int) -> dict[str, Any]:
    command = [sys.executable, str(Path(__file__).resolve()), "--child", mutation,
               "--expected-sha256", expected_sha256]
    child_env = dict(os.environ)
    for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        child_env[variable] = "1"
    completed = subprocess.run(command, cwd=ROOT, env=child_env, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=180)
    log = completed.stdout + completed.stderr
    log_path = OUTPUT_DIR / f"mutation-{mutation}-run-{run_number}.log"
    log_path.write_text(log, encoding="utf-8")
    result_lines = [line[len(RESULT_MARKER):] for line in completed.stdout.splitlines()
                    if line.startswith(RESULT_MARKER)]
    result = json.loads(result_lines[-1]) if result_lines else {"mutation": mutation}
    result["subprocess_exit_code"] = completed.returncode
    result["log"] = log_path.name
    if mutation == "baseline":
        verified = completed.returncode == 0 and result.get("passed", 0) > 0
    else:
        verified = (completed.returncode == 1 and result.get("errors") == 0
                    and result.get("failed", 0) > 0
                    and result.get("assertion_failures") == result.get("failed"))
    result["verified"] = verified
    print(f"{mutation}: {'verified' if verified else 'NOT VERIFIED'} "
          f"(exit {completed.returncode}, {result.get('failed', 0)} assertion failures)", flush=True)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--child", choices=["baseline", *MUTATIONS])
    parser.add_argument("--expected-sha256", default="")
    args = parser.parse_args()
    if args.child:
        return _run_child(args.child, args.expected_sha256)

    report_path = OUTPUT_DIR / "mutations.json"
    previous = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else None
    run_number = previous.get("run_number", 1) + 1 if previous else 1
    expected_sha256 = _digest(PIPELINE_PATH.read_bytes())
    baseline = _launch("baseline", expected_sha256, run_number)
    if not baseline["verified"]:
        raise RuntimeError("The unmodified characterization suite must pass before mutation checks.")
    results = [_launch(mutation, expected_sha256, run_number) for mutation in MUTATIONS]
    source_unchanged = _digest(PIPELINE_PATH.read_bytes()) == expected_sha256
    report = {
        "run_number": run_number,
        "pipeline_path": "extraction/pipeline.py",
        "pipeline_sha256": expected_sha256,
        "source_unchanged": source_unchanged,
        "test_path": TEST_PATH,
        "method": "Real source compiled with one targeted mutation per subprocess; no production writes.",
        "baseline": baseline,
        "mutations": [{**result, "behavior": MUTATIONS[result["mutation"]]["behavior"]}
                      for result in results],
        "verified": source_unchanged and all(result["verified"] for result in results),
    }
    if previous:
        report["previous_runs"] = [*previous.pop("previous_runs", []), previous]
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if report["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
