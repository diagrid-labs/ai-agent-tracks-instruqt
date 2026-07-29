"""Framework-agnostic core of the Supply Chain Auditor.

This package contains all the audit logic that is independent of the agent
framework: parsing the Dependabot bump, resolving the upstream source repo,
fetching release notes and the source diff, the deterministic red-flag
heuristics, the untrusted-content guardrail, the prompt, and the verdict
reconcile + report rendering.
"""
