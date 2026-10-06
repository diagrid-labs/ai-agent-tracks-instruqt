"""One-shot entry point: audit a Dependabot PR and post the report comment.

Runs once (e.g. in CI): read the PR context + Dependabot metadata from the
environment, run the durable audit workflow once per bumped dependency, post (or
dry-run) a single combined PR comment, and exit. It is **advisory** — it exits 0
even on FAIL so it never blocks a merge by itself (wire a required check on
`recommendation == block` if you want a gate).
"""

from __future__ import annotations

import logging
import os
import sys

from auditor_core import orchestration
from auditor_core.models import DependencyBump, PRContext
from dotenv import load_dotenv
from runtime import resume_or_invoke

logger = logging.getLogger("supply_chain_auditor")


def run_audit(
    pr: PRContext, bumps: list[DependencyBump], runner
) -> tuple[str, list[dict]]:
    """Run the durable audit workflow once per bump; return (combined report, verdicts)."""
    sections: list[str] = []
    verdicts: list[dict] = []
    for bump in bumps:
        thread_id = f"audit-{pr.repo}-{pr.number}-{bump.package}".replace("/", "-")
        result = resume_or_invoke(
            runner,
            {"pr": pr.model_dump(), "bump": bump.model_dump()},
            workflow_id=thread_id,
        )
        report_md = result.get("report_md", "") if isinstance(result, dict) else ""
        if not report_md:
            # A blank/partial workflow result must fail loudly, not post an empty
            # comment that reads as a silent pass. main() turns this into an
            # explicit "manual review required" notice.
            raise RuntimeError(f"workflow returned no report for {bump.package}")
        sections.append(report_md)
        if result.get("verdict"):
            verdicts.append(result["verdict"])
    return orchestration.combine_reports(sections), verdicts


def main() -> int:
    load_dotenv()
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))

    pr = orchestration.ensure_pr_details(PRContext.from_env())
    bumps = orchestration.parse_bumps(pr)
    if not bumps:
        logger.info(
            "No dependency bump detected (no DEP_* metadata and no parseable bump "
            "in the PR title %r); nothing to audit.",
            pr.title,
        )
        return 0
    logger.info(
        "Auditing %d dependency bump(s) in %s#%s", len(bumps), pr.repo, pr.number
    )

    from agent import build_runner  # lazy: needs a Dapr sidecar

    runner = build_runner()
    runner.start()
    try:
        body, _verdicts = run_audit(pr, bumps, runner)
    except Exception as exc:  # fail safe: never leave a bump silently unaudited
        logger.error("Audit pipeline failed: %s", exc, exc_info=True)
        orchestration.post_report(pr.repo, pr.number, orchestration.error_report(exc))
        return 1
    finally:
        runner.shutdown()

    status = orchestration.post_report(pr.repo, pr.number, body)
    logger.info("Post result: %s", status)
    print(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
