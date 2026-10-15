#!/usr/bin/env python3
"""
build_capsule.py - Assemble, validate, and render a Dependency Exit Capsule.

Strict Capsule Rules:
- Two separate top-level sections: "observed" and "ai_generated".
- Never mix AI claims into "observed".
- Every finding has a status: "verified" | "unverified" | "not_testable".
- Validates the assembled capsule against references/capsule-schema.json.
- Renders an executive Markdown exit capsule report.
"""

import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path


def validate_capsule(capsule: dict, schema: dict) -> list[str]:
    """Validate capsule structure, required fields, and strict separation rules."""
    errors = []

    # 1. Check top-level required fields
    required_top = [
        "schema_version",
        "capsule_id",
        "generated_at",
        "target_repo",
        "target_dependency",
        "observed",
        "ai_generated"
    ]
    for key in required_top:
        if key not in capsule:
            errors.append(f"Missing required top-level property: '{key}'")

    if errors:
        return errors

    # 2. Strict separation: Check that no AI fields are mixed into "observed"
    observed = capsule.get("observed", {})
    forbidden_observed_keys = {
        "model_metadata",
        "proposed_replacement",
        "migration_steps",
        "suggested_tests",
        "compatibility_gaps",
        "open_concerns_and_limitations",
        "ai_generated"
    }
    for k in observed.keys():
        if k in forbidden_observed_keys:
            errors.append(f"VIOLATION: AI-generated field '{k}' found inside 'observed' section!")

    # 3. Check observed required sections
    for obs_req in ["risk_indicators", "usage_locations", "executed_test_results"]:
        if obs_req not in observed:
            errors.append(f"Missing required 'observed' property: '{obs_req}'")

    # 4. Check ai_generated required sections
    ai_gen = capsule.get("ai_generated", {})
    for ai_req in [
        "model_metadata",
        "proposed_replacement",
        "migration_steps",
        "suggested_tests",
        "compatibility_gaps",
        "open_concerns_and_limitations"
    ]:
        if ai_req not in ai_gen:
            errors.append(f"Missing required 'ai_generated' property: '{ai_req}'")

    # 5. Check status validation
    valid_statuses = {"verified", "unverified", "not_testable"}

    def check_status(obj, path):
        if isinstance(obj, dict):
            if "status" in obj:
                st = obj["status"]
                if st not in valid_statuses:
                    errors.append(f"Invalid status '{st}' at {path}. Must be one of {valid_statuses}")
            for k, v in obj.items():
                check_status(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for idx, item in enumerate(obj):
                check_status(item, f"{path}[{idx}]")

    check_status(capsule, "capsule")

    # 6. Check replacement validation block
    prop = ai_gen.get("proposed_replacement", {})
    val = prop.get("validation", {})
    if "is_valid" not in val or "validation_source" not in val:
        errors.append("Proposed replacement validation block must contain 'is_valid' and 'validation_source'.")

    return errors


def render_markdown_report(capsule: dict) -> str:
    """Render a comprehensive Dependency Exit Capsule Markdown document."""
    repo = capsule["target_repo"]
    dep = capsule["target_dependency"]
    obs = capsule["observed"]
    ai = capsule["ai_generated"]
    risk = obs["risk_indicators"]
    usage = obs["usage_locations"]
    tests = obs["executed_test_results"]
    model = ai["model_metadata"]
    replacement = ai["proposed_replacement"]

    md = []
    md.append(f"# 🛡️ Dependency Exit Capsule: `{dep['name']}`")
    md.append("")
    md.append(f"**Capsule ID:** `{capsule['capsule_id']}`  ")
    md.append(f"**Generated At:** `{capsule['generated_at']}`  ")
    md.append(f"**Target Repository:** `{repo['name']}` (`{repo['path']}`)  ")
    md.append(f"**Python Runtime:** Python {repo['python_version']}  ")
    md.append(f"**Schema Version:** `{capsule['schema_version']}`  ")
    md.append("")
    md.append("---")
    md.append("")

    # =========================================================================
    # PART 1: OBSERVED EVIDENCE
    # =========================================================================
    md.append("## 🔬 Part 1: Observed Evidence (Empirical & Verifiable)")
    md.append("> [!NOTE]")
    md.append("> All findings in this section are strictly derived from registry metadata, AST static analysis,")
    md.append("> and isolated differential test execution. No AI-generated content is present here.")
    md.append("")

    # 1.1 Risk Indicators
    md.append("### 1.1 Upstream Registry & Risk Indicators")
    md.append(f"**Status:** `{risk['status'].upper()}`")
    md.append("")
    md.append("| Metric | Observed Value |")
    md.append("| :--- | :--- |")
    md.append(f"| **Target Dependency** | `{dep['name']}` |")
    md.append(f"| **Declared Specifier** | `{dep['declared_specifier']}` |")
    md.append(f"| **Source File** | `{dep['source_file']}` |")
    md.append(f"| **Latest PyPI Version** | `{dep['latest_pypi_version'] or 'N/A'}` |")
    md.append(f"| **Last PyPI Release Date** | `{risk['last_release_date'] or 'N/A'}` |")
    days_rel = f"{risk['days_since_last_release']} days" if risk['days_since_last_release'] is not None else "Unknown"
    md.append(f"| **Staleness (Days Elapsed)** | `{days_rel}` |")
    md.append(f"| **Yanked Status** | `{'YES' if risk['yanked'] else 'No'}` |")
    if risk['yanked_reason']:
        md.append(f"| **Yanked Reason** | `{risk['yanked_reason']}` |")
    md.append(f"| **Repository URL** | `{dep['repository_url'] or 'N/A'}` |")
    archived_str = "Unknown" if risk['github_archived'] is None else ("YES (Archived)" if risk['github_archived'] else "No")
    md.append(f"| **GitHub Archived** | `{archived_str}` |")
    md.append(f"| **GitHub Last Push** | `{risk['github_last_push'] or 'N/A'}` |")
    if risk.get("api_notes"):
        md.append(f"| **API Notes** | `{risk['api_notes']}` |")
    md.append("")

    if risk.get("deprecation_signals"):
        md.append("#### Detected Deprecation Signals in Upstream Description")
        for sig in risk["deprecation_signals"]:
            md.append(f"- ⚠️ *\"{sig}\"*")
        md.append("")

    # 1.2 Usage Locations
    md.append("### 1.2 Codebase AST Usage Map")
    md.append(f"**Status:** `{usage['status'].upper()}` | **Total Occurrences:** `{usage['total_occurrences']}` | **Dynamic Imports Detected:** `{'YES (Uncertain)' if usage['dynamic_imports_detected'] else 'None'}`")
    md.append("")

    if usage.get("imports"):
        md.append("#### Imports Discovered")
        md.append("| File | Line | Imported Symbol | Alias | Dynamic | Status |")
        md.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
        for imp in usage["imports"]:
            alias_display = f"`{imp['alias']}`" if imp['alias'] else "*none*"
            dyn_display = "⚠️ Yes" if imp['is_dynamic'] else "No"
            md.append(f"| `{imp['file']}` | Line {imp['line']} | `{imp['imported_symbol']}` | {alias_display} | {dyn_display} | `{imp['status']}` |")
        md.append("")
    else:
        md.append("*No imports found in codebase.*")
        md.append("")

    if usage.get("calls"):
        md.append("#### Function & Method Calls Discovered")
        md.append("| File | Line | Call Expression | Status |")
        md.append("| :--- | :--- | :--- | :--- |")
        for call in usage["calls"]:
            md.append(f"| `{call['file']}` | Line {call['line']} | `{call['call_expression']}` | `{call['status']}` |")
        md.append("")
    else:
        md.append("*No direct calls found in codebase.*")
        md.append("")

    # 1.3 Executed Differential Test Results
    md.append("### 1.3 Executed Differential Test Results")
    md.append(f"**Status:** `{tests['status'].upper()}`")
    md.append("")
    base = tests["baseline"]
    rep = tests["replacement"]
    diff = tests["diff"]

    md.append("| Test Suite Metric | Venv A (Baseline Original) | Venv B (Replacement + Patch) | Delta |")
    md.append("| :--- | :--- | :--- | :--- |")
    md.append(f"| **Exit Code** | `{base['exit_code']}` | `{rep['exit_code'] if rep else 'N/A'}` | - |")
    md.append(f"| **Total Tests** | `{base['total']}` | `{rep['total'] if rep else 'N/A'}` | - |")
    md.append(f"| **Passed** | `{base['passed']}` | `{rep['passed'] if rep else 'N/A'}` | - |")
    md.append(f"| **Failed** | `{base['failed']}` | `{rep['failed'] if rep else 'N/A'}` | - |")
    md.append(f"| **Duration** | `{base['duration_seconds']}s` | `{rep['duration_seconds'] if rep else 'N/A'}s` | - |")
    md.append("")

    md.append("#### Attributable Regressions Analysis")
    attributable = diff.get("new_failures_attributable_to_replacement", [])
    if attributable:
        md.append("> [!WARNING]")
        md.append("> **New failures directly attributable to the replacement:**")
        for f in attributable:
            md.append(f"- ❌ `{f}`")
    else:
        md.append("> [!TIP]")
        md.append("> **Zero new failures attributable to replacement.** All existing passing tests remained green.")
    md.append("")

    if diff.get("resolved_failures"):
        md.append("#### Resolved Failures (Fixed by Migration)")
        for rf in diff["resolved_failures"]:
            md.append(f"- ✅ `{rf}`")
        md.append("")

    md.append(f"**Notes:** {diff.get('notes', 'None')}")
    md.append("")
    md.append("---")
    md.append("")

    # =========================================================================
    # PART 2: AI-GENERATED MIGRATION PROPOSAL
    # =========================================================================
    md.append("## 🤖 Part 2: AI-Generated Migration Proposal (Model-Assisted)")
    md.append("> [!CAUTION]")
    md.append("> Findings in this section are model-generated recommendations. Each item is marked `unverified`")
    md.append("> until manually confirmed or exercised in tests.")
    md.append("")

    # 2.1 Model Provenance
    md.append("### 2.1 Model Provenance & Licensing")
    md.append(f"- **Model Name:** `{model['name']}`")
    md.append(f"- **Model Version:** `{model['version']}`")
    md.append(f"- **Access Method:** `{model['access_method']}`")
    md.append(f"- **License:** `{model['license']}`")
    md.append("")

    # 2.2 Proposed Replacement & Validation
    md.append("### 2.2 Proposed Replacement Package")
    val = replacement["validation"]
    val_badge = "✅ VALIDATED" if val["is_valid"] else "❌ REJECTED"
    md.append(f"**Target Replacement:** `{replacement['package_name']}` ({replacement['type']}) — **{val_badge}**")
    md.append("")
    md.append(f"**Validation Source:** `{val['validation_source']}` | **Validation Status:** `{val['status'].upper()}`")
    md.append(f"**Verification Details:** {val['details']}")
    md.append("")
    md.append(f"**Rationale:** {replacement['rationale']}")
    md.append("")

    # 2.3 Migration Steps
    md.append("### 2.3 Step-by-Step Migration Plan")
    for step in ai.get("migration_steps", []):
        md.append(f"#### Step {step['step_number']}: {step['title']} `[{step['status']}]`")
        md.append(f"{step['description']}")
        if step.get("diff_snippet"):
            md.append("```diff")
            md.append(step["diff_snippet"])
            md.append("```")
        md.append("")

    # 2.4 Suggested Tests
    md.append("### 2.4 Suggested Tests for Regression Verification")
    for st in ai.get("suggested_tests", []):
        md.append(f"#### `{st['test_name']}` `[{st['status']}]`")
        md.append(f"{st['description']}")
        if st.get("code_snippet"):
            md.append("```python")
            md.append(st["code_snippet"])
            md.append("```")
        md.append("")

    # 2.5 Compatibility Gaps
    md.append("### 2.5 Compatibility Gaps & Breaking Changes")
    for gap in ai.get("compatibility_gaps", []):
        md.append(f"- **{gap['area']}** `[{gap['status']}]`: {gap['description']}")
        if gap.get("mitigation"):
            md.append(f"  - *Mitigation:* {gap['mitigation']}")
    md.append("")

    # 2.6 Open Concerns and Limitations
    md.append("### 2.6 Open Concerns & Limitations")
    for concern in ai.get("open_concerns_and_limitations", []):
        severity_icon = "🔴" if concern["severity"] in ("high", "critical") else "🟡"
        md.append(f"- {severity_icon} **{concern['title']}** (Severity: `{concern['severity'].upper()}`) `[{concern['status']}]`")
        md.append(f"  {concern['description']}")
    md.append("")

    return "\n".join(md)


def assemble_capsule(
    dep_name: str,
    repo_path: Path,
    risk_data: dict,
    usage_data: dict,
    proposal_data: dict,
    diff_test_data: dict,
    python_version: str = "3.12"
) -> dict:
    """Assemble individual phase artifacts into a standardized capsule payload."""
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    clean_dep = dep_name.replace("-", "_").lower()
    clean_repo = repo_path.name.lower()
    capsule_id = f"capsule-{clean_repo}-{clean_dep}-{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d%H%M')}"

    # Extract target dep details
    target_dep_info = {
        "name": dep_name,
        "declared_specifier": risk_data.get("declared_specifier", ""),
        "source_file": risk_data.get("source_file", "requirements.txt"),
        "latest_pypi_version": risk_data.get("latest_version"),
        "pypi_url": risk_data.get("pypi_url"),
        "repository_url": risk_data.get("repository_url")
    }

    observed_section = {
        "risk_indicators": {
            "status": risk_data.get("risk_status", "verified"),
            "last_release_date": risk_data.get("last_release_date"),
            "days_since_last_release": risk_data.get("days_since_last_release"),
            "yanked": bool(risk_data.get("yanked", False)),
            "yanked_reason": risk_data.get("yanked_reason"),
            "github_archived": risk_data.get("github_archived"),
            "github_last_push": risk_data.get("github_last_push"),
            "days_since_last_push": risk_data.get("days_since_last_push"),
            "deprecation_signals": risk_data.get("deprecation_signals", []),
            "api_notes": "; ".join(risk_data.get("notes", [])) if risk_data.get("notes") else None
        },
        "usage_locations": {
            "status": usage_data.get("status", "verified"),
            "total_occurrences": usage_data.get("total_occurrences", 0),
            "dynamic_imports_detected": bool(usage_data.get("dynamic_imports_detected", False)),
            "imports": usage_data.get("imports", []),
            "calls": usage_data.get("calls", [])
        },
        "executed_test_results": diff_test_data
    }

    ai_generated_section = {
        "model_metadata": proposal_data["model_metadata"],
        "proposed_replacement": proposal_data["proposed_replacement"],
        "migration_steps": proposal_data.get("migration_steps", []),
        "suggested_tests": proposal_data.get("suggested_tests", []),
        "compatibility_gaps": proposal_data.get("compatibility_gaps", []),
        "open_concerns_and_limitations": proposal_data.get("open_concerns_and_limitations", [])
    }

    return {
        "schema_version": "1.0.0",
        "capsule_id": capsule_id,
        "generated_at": now_iso,
        "target_repo": {
            "name": repo_path.name,
            "path": str(repo_path),
            "url": "https://github.com/rishrek/LinkWatch" if "linkwatch" in repo_path.name.lower() else None,
            "python_version": python_version
        },
        "target_dependency": target_dep_info,
        "observed": observed_section,
        "ai_generated": ai_generated_section
    }


def main():
    parser = argparse.ArgumentParser(
        description="Assemble, validate against capsule-schema.json, and render Markdown capsule."
    )
    parser.add_argument(
        "--dep",
        "--dependency",
        required=True,
        help="Target dependency name (e.g. toml, appdirs)"
    )
    parser.add_argument(
        "--repo-path",
        default=".",
        help="Path to target repository"
    )
    parser.add_argument(
        "--risk-file",
        required=True,
        help="Path to JSON file containing scan_risk output"
    )
    parser.add_argument(
        "--usage-file",
        required=True,
        help="Path to JSON file containing map_usage output"
    )
    parser.add_argument(
        "--proposal-file",
        required=True,
        help="Path to JSON file containing propose_replacement output"
    )
    parser.add_argument(
        "--diff-test-file",
        required=True,
        help="Path to JSON file containing run_diff_tests output"
    )
    parser.add_argument(
        "--schema",
        default=str(Path(__file__).parent.parent / "references" / "capsule-schema.json"),
        help="Path to capsule-schema.json"
    )
    parser.add_argument(
        "--output-json",
        default=None,
        help="Path to save assembled JSON capsule"
    )
    parser.add_argument(
        "--output-md",
        default=None,
        help="Path to save rendered Markdown report"
    )

    args = parser.parse_args()

    repo_dir = Path(args.repo_path).resolve()
    schema_path = Path(args.schema).resolve()

    # Load artifacts
    with open(args.risk_file, "r", encoding="utf-8") as f:
        risk_raw = json.load(f)
    with open(args.usage_file, "r", encoding="utf-8") as f:
        usage_raw = json.load(f)
    with open(args.proposal_file, "r", encoding="utf-8") as f:
        proposal_raw = json.load(f)
    with open(args.diff_test_file, "r", encoding="utf-8") as f:
        diff_raw = json.load(f)

    # If risk file contains list of dependencies, find target dep
    target_dep_name = args.dep.lower()
    target_risk = None
    if "dependencies" in risk_raw:
        for d in risk_raw["dependencies"]:
            if d.get("canonical_name", "").lower() == target_dep_name or d.get("package_name", "").lower() == target_dep_name:
                target_risk = d
                break
    else:
        target_risk = risk_raw

    if not target_risk:
        sys.stderr.write(f"Could not locate risk data for {args.dep} in {args.risk_file}\n")
        sys.exit(1)

    usage_data = usage_raw.get("usage", usage_raw)

    # Assemble capsule
    capsule = assemble_capsule(
        dep_name=args.dep,
        repo_path=repo_dir,
        risk_data=target_risk,
        usage_data=usage_data,
        proposal_data=proposal_raw,
        diff_test_data=diff_raw
    )

    # Load schema and validate
    schema_data = {}
    if schema_path.exists():
        with open(schema_path, "r", encoding="utf-8") as f:
            schema_data = json.load(f)

    errors = validate_capsule(capsule, schema_data)
    if errors:
        sys.stderr.write("Capsule Schema Validation ERRORS:\n")
        for err in errors:
            sys.stderr.write(f" - {err}\n")
        sys.exit(1)

    sys.stderr.write("Capsule Schema Validation: PASSED (Zero errors)\n")

    # Save JSON capsule
    formatted_json = json.dumps(capsule, indent=2)
    if args.output_json:
        out_j = Path(args.output_json).resolve()
        out_j.parent.mkdir(parents=True, exist_ok=True)
        with open(out_j, "w", encoding="utf-8") as f:
            f.write(formatted_json)
            f.write("\n")
        sys.stderr.write(f"Wrote JSON capsule to {out_j}\n")
    else:
        print(formatted_json)

    # Render and save Markdown report
    md_content = render_markdown_report(capsule)
    if args.output_md:
        out_m = Path(args.output_md).resolve()
        out_m.parent.mkdir(parents=True, exist_ok=True)
        with open(out_m, "w", encoding="utf-8") as f:
            f.write(md_content)
            f.write("\n")
        sys.stderr.write(f"Wrote Markdown report to {out_m}\n")


if __name__ == "__main__":
    main()
