from __future__ import annotations
from pathlib import Path
from evals._shared.missing_input import (
    EVAL_RC_FAIL,
    missing_input_report,
    write_missing_input_report,
)


def run(repo_root: Path) -> int:
    # Triggers eval has no metrics implemented yet. Returning PASS would mask
    # missing functionality — fail loudly until the metric module lands.
    report = missing_input_report(
        stage="triggers",
        reason="trigger evaluation not yet implemented; emitting FAIL to avoid masking absent functionality",
        based_on_path=None,
    )
    write_missing_input_report(repo_root, report)
    print(f"triggers eval: {report.overall} (not implemented)")
    return EVAL_RC_FAIL
