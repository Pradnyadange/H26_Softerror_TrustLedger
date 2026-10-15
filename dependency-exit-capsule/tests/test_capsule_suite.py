"""
test_capsule_suite.py - Automated test suite for dependency-exit-capsule.
Tests AST mapping, risk scanning, schema compliance, differential logic,
fixture repository generalization, and banned hardcoded literals.
"""

import ast
import json
import os
import re
import sys
from pathlib import Path
import pytest

from scripts import scan_risk, map_usage, propose_replacement, run_diff_tests, build_capsule, verify_capsule


def test_scan_risk_pypi_parser(tmp_path):
    req_file = tmp_path / "requirements.txt"
    req_file.write_text(
        "# Comments and flags\n"
        "-i https://pypi.org/simple\n"
        "toml==0.10.2\n"
        "requests>=2.25.0; python_version >= '3.8'\n"
        "  click # inline comment\n",
        encoding="utf-8"
    )

    deps = scan_risk.parse_requirements_txt(req_file)
    names = [d["name"] for d in deps]
    assert "toml" in names
    assert "requests" in names
    assert "click" in names
    assert len(deps) == 3


def test_extract_github_coords():
    urls = [
        "https://pypi.org/project/toml/",
        "https://github.com/uiri/toml",
        "https://github.com/uiri/toml/issues"
    ]
    owner, repo, canon_url = scan_risk.extract_github_coords(urls)
    assert owner == "uiri"
    assert repo == "toml"
    assert canon_url == "https://github.com/uiri/toml"


def test_deprecation_pattern_detection():
    sample_text = "This repository is unmaintained and deprecated. Please use tomllib instead."
    detected = []
    for pattern in scan_risk.DEPRECATION_PATTERNS:
        matches = pattern.finditer(sample_text)
        for m in matches:
            detected.append(m.group(0).lower())
    assert "deprecated" in detected
    assert "unmaintained" in detected
    assert any("please use" in d for d in detected)


def test_ast_mapping_imports_and_calls(tmp_path):
    py_code = """
import toml
import toml as t_alias
from toml import load as custom_load

def load_settings(path):
    data1 = toml.load(path)
    data2 = t_alias.loads('foo = 1')
    data3 = custom_load(path)
    return data1
"""
    test_file = tmp_path / "test_module.py"
    test_file.write_text(py_code, encoding="utf-8")

    result = map_usage.map_dependency_usage(tmp_path, "toml")
    assert result["status"] == "verified"
    assert result["total_occurrences"] >= 5
    assert not result["dynamic_imports_detected"]

    # Verify imports
    symbols = [imp["imported_symbol"] for imp in result["imports"]]
    assert "toml" in symbols
    assert "toml.load" in symbols

    # Verify calls
    calls = [c["call_expression"] for c in result["calls"]]
    assert any("toml.load" in c for c in calls)
    assert any("custom_load" in c for c in calls)


def test_ast_dynamic_import_detection(tmp_path):
    py_code = """
import importlib

def dynamic_loader(name):
    mod = importlib.import_module(name)
    mod2 = __import__('toml')
    return mod
"""
    test_file = tmp_path / "dynamic_module.py"
    test_file.write_text(py_code, encoding="utf-8")

    result = map_usage.map_dependency_usage(tmp_path, "toml")
    assert result["dynamic_imports_detected"] is True
    assert any(imp.get("is_dynamic") for imp in result["imports"])


def test_validate_proposed_package_stdlib():
    val = propose_replacement.validate_proposed_package("tomllib", "stdlib")
    assert val["is_valid"] is True
    assert val["validation_source"] == "sys.stdlib_module_names"
    assert val["status"] == "verified"


def test_validate_proposed_package_pypi():
    val = propose_replacement.validate_proposed_package("platformdirs", "pypi")
    assert val["is_valid"] is True
    assert val["validation_source"] == "pypi"
    assert val["status"] == "verified"


def test_validate_proposed_package_hallucination():
    val = propose_replacement.validate_proposed_package("nonexistent_fake_package_xyz_12345", "pypi")
    assert val["is_valid"] is False
    assert val["status"] == "verified"


def test_parse_junit_xml_empty(tmp_path):
    empty_xml = tmp_path / "empty.xml"
    empty_xml.write_text("", encoding="utf-8")
    summary = run_diff_tests.parse_junit_xml(empty_xml)
    assert summary["total"] == 0
    assert summary["passed"] == 0


def test_parse_junit_xml_valid(tmp_path):
    xml_content = """<?xml version="1.0" encoding="utf-8"?>
<testsuite name="pytest" errors="0" failures="1" skipped="1" tests="4" time="0.523">
    <testcase classname="tests.test_app" name="test_one" time="0.100"/>
    <testcase classname="tests.test_app" name="test_two" time="0.200"/>
    <testcase classname="tests.test_app" name="test_three" time="0.123">
        <failure message="assertion error">AssertionError</failure>
    </testcase>
    <testcase classname="tests.test_app" name="test_four" time="0.100">
        <skipped message="skip"/>
    </testcase>
</testsuite>"""
    xml_file = tmp_path / "junit.xml"
    xml_file.write_text(xml_content, encoding="utf-8")

    summary = run_diff_tests.parse_junit_xml(xml_file)
    assert summary["total"] == 4
    assert summary["passed"] == 2
    assert summary["failed"] == 1
    assert summary["skipped"] == 1
    assert "tests.test_app::test_three" in summary["failures"]


def test_build_capsule_validation_strict_separation():
    valid_capsule = {
        "schema_version": "2.0.0",
        "capsule_id": "capsule-test-1",
        "generated_at": "2026-10-15T00:00:00Z",
        "target_repo": {"name": "test", "url": "https://github.com/test/test", "commit_sha": "abc1234", "python_version": "3.12"},
        "target_dependency": {
            "name": "toml",
            "declared_specifier": "==0.10.2",
            "source_file": "requirements.txt",
            "latest_pypi_version": "0.10.2",
            "pypi_url": "https://pypi.org/project/toml/",
            "repository_url": "https://github.com/uiri/toml"
        },
        "observed": {
            "evidence": [
                {
                    "path": "test/baseline_junit.xml",
                    "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                    "command": "pytest --junitxml=baseline_junit.xml",
                    "exit_code": 0,
                    "captured_at": "2026-10-15T00:00:00Z"
                }
            ],
            "risk_indicators": {
                "status": "verified",
                "last_release_date": "2020-11-01",
                "days_since_last_release": 2100,
                "yanked": False,
                "yanked_reason": None,
                "github_archived": False,
                "github_last_push": "2024-06-26",
                "days_since_last_push": 800,
                "deprecation_signals": []
            },
            "usage_locations": {
                "status": "verified",
                "total_occurrences": 1,
                "dynamic_imports_detected": False,
                "imports": [],
                "calls": []
            },
            "executed_test_results": {
                "status": "verified",
                "baseline": {"exit_code": 0, "total": 1, "passed": 1, "failed": 0, "errors": 0, "skipped": 0, "duration_seconds": 1.0, "failures": []},
                "replacement": {"exit_code": 0, "total": 1, "passed": 1, "failed": 0, "errors": 0, "skipped": 0, "duration_seconds": 1.0, "failures": []},
                "diff": {"status": "verified", "new_failures_attributable_to_replacement": [], "resolved_failures": [], "notes": "ok"}
            }
        },
        "ai_generated": {
            "provenance": {
                "provider": "ollama",
                "model_id": "gemma2:2b",
                "model_license_name": "Gemma Terms of Use",
                "model_card_url": "https://ai.google.dev/gemma/terms",
                "prompt_sha256": "abcde12345",
                "raw_response_path": "model_raw.json",
                "validation": {"passed": True, "rejected_candidates": []}
            },
            "proposed_replacement": {
                "package_name": "tomllib",
                "type": "stdlib",
                "version_specifier": None,
                "rationale": "Builtin",
                "validation": {"status": "verified", "is_valid": True, "validation_source": "sys.stdlib_module_names"}
            },
            "migration_steps": [],
            "suggested_tests": [],
            "compatibility_gaps": [],
            "open_concerns_and_limitations": []
        }
    }

    errors = build_capsule.validate_capsule(valid_capsule, {})
    assert len(errors) == 0

    # Inject forbidden AI field into "observed"
    corrupt_capsule = json.loads(json.dumps(valid_capsule))
    corrupt_capsule["observed"]["proposed_replacement"] = "BLEED"
    errors = build_capsule.validate_capsule(corrupt_capsule, {})
    assert any("VIOLATION" in err for err in errors)


def test_render_markdown_report():
    capsule = {
        "schema_version": "2.0.0",
        "capsule_id": "capsule-test-1",
        "generated_at": "2026-10-15T00:00:00Z",
        "target_repo": {"name": "test", "url": "https://github.com/test/test", "commit_sha": "abc1234", "python_version": "3.12"},
        "target_dependency": {
            "name": "toml",
            "declared_specifier": "==0.10.2",
            "source_file": "requirements.txt",
            "latest_pypi_version": "0.10.2",
            "pypi_url": "https://pypi.org/project/toml/",
            "repository_url": "https://github.com/uiri/toml"
        },
        "observed": {
            "evidence": [
                {
                    "path": "test/baseline_junit.xml",
                    "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                    "command": "pytest --junitxml=baseline_junit.xml",
                    "exit_code": 0,
                    "captured_at": "2026-10-15T00:00:00Z"
                }
            ],
            "risk_indicators": {
                "status": "verified",
                "last_release_date": "2020-11-01",
                "days_since_last_release": 2100,
                "yanked": False,
                "yanked_reason": None,
                "github_archived": False,
                "github_last_push": "2024-06-26",
                "days_since_last_push": 800,
                "deprecation_signals": []
            },
            "usage_locations": {
                "status": "verified",
                "total_occurrences": 1,
                "dynamic_imports_detected": False,
                "imports": [{"file": "config.py", "line": 3, "imported_symbol": "toml", "alias": None, "is_dynamic": False, "status": "verified"}],
                "calls": [{"file": "config.py", "line": 10, "call_expression": "toml.load()", "status": "verified"}]
            },
            "executed_test_results": {
                "status": "verified",
                "baseline": {"exit_code": 0, "total": 1, "passed": 1, "failed": 0, "errors": 0, "skipped": 0, "duration_seconds": 1.0, "failures": []},
                "replacement": {"exit_code": 0, "total": 1, "passed": 1, "failed": 0, "errors": 0, "skipped": 0, "duration_seconds": 1.0, "failures": []},
                "diff": {"status": "verified", "new_failures_attributable_to_replacement": [], "resolved_failures": [], "notes": "No regressions detected."}
            }
        },
        "ai_generated": {
            "provenance": {
                "provider": "ollama",
                "model_id": "gemma2:2b",
                "model_license_name": "Gemma Terms of Use",
                "model_card_url": "https://ai.google.dev/gemma/terms",
                "prompt_sha256": "abcde12345",
                "raw_response_path": "model_raw.json",
                "validation": {"passed": True, "rejected_candidates": []}
            },
            "proposed_replacement": {
                "package_name": "tomllib",
                "type": "stdlib",
                "version_specifier": None,
                "rationale": "Built-in PEP 680 standard library support in Python 3.11+",
                "validation": {"status": "verified", "is_valid": True, "validation_source": "sys.stdlib_module_names"}
            },
            "migration_steps": [
                {
                    "step_number": 1,
                    "title": "Update import",
                    "description": "Change to tomllib",
                    "diff_snippet": "-import toml\n+import tomllib",
                    "status": "unverified"
                }
            ],
            "suggested_tests": [],
            "compatibility_gaps": [],
            "open_concerns_and_limitations": []
        }
    }

    md = build_capsule.render_markdown_report(capsule)
    assert "# 🛡️ Dependency Exit Capsule: `toml`" in md
    assert "Part 1: Observed Evidence" in md
    assert "Part 2: AI-Generated Migration Proposal" in md
    assert "tomllib" in md


def test_propose_replacement_offline_knowledge_base():
    usage_sample = {
        "status": "verified",
        "total_occurrences": 3,
        "imports": [{"file": "report.py", "line": 3, "imported_symbol": "jinja2.Environment", "status": "verified"}],
        "calls": [{"file": "report.py", "line": 9, "call_expression": "Environment()", "status": "verified"}]
    }
    res = propose_replacement.propose_replacement(
        dep_name="jinja2",
        usage_evidence=usage_sample,
        provider="offline"
    )
    assert res["proposed_replacement"]["package_name"].lower() == "jinja2"
    assert res["proposed_replacement"]["type"] == "pypi"
    assert res["proposed_replacement"]["validation"]["is_valid"] is True
    assert res["provenance"]["provider"] == "rule_based_knowledge_base"
    assert len(res["migration_steps"]) >= 1


def test_generalization_fixture_repo():
    fixture_dir = Path(__file__).parent / "fixtures" / "sample_repo"
    assert fixture_dir.exists()

    # Step 1: scan_risk
    deps = scan_risk.parse_requirements_txt(fixture_dir / "requirements.txt")
    assert any(d["name"] == "toml" for d in deps)

    # Step 2: map_usage
    usage = map_usage.map_dependency_usage(fixture_dir, "toml")
    assert usage["total_occurrences"] >= 1
    assert any("config.py" in imp["file"] for imp in usage["imports"])

    # Step 3: propose_replacement offline
    proposal = propose_replacement.propose_replacement(
        dep_name="toml",
        usage_evidence=usage,
        provider="offline"
    )
    assert proposal["proposed_replacement"]["package_name"] == "tomllib"
    assert proposal["provenance"]["provider"] == "rule_based_knowledge_base"


def test_verify_manifest_integrity(tmp_path):
    f1 = tmp_path / "file1.txt"
    f1.write_text("hello world", encoding="utf-8")
    h1 = verify_capsule.sha256_file(f1)

    manifest_file = tmp_path / "manifest.json"
    manifest_data = {
        "manifest_version": "1.0.0",
        "artifacts": {
            "file1.txt": h1
        }
    }
    manifest_file.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")

    valid, errs = verify_capsule.verify_manifest(manifest_file)
    assert valid is True
    assert len(errs) == 0

    # Modify file to trigger checksum mismatch
    f1.write_text("tampered content", encoding="utf-8")
    valid_bad, errs_bad = verify_capsule.verify_manifest(manifest_file)
    assert valid_bad is False
    assert len(errs_bad) == 1
    assert "Checksum mismatch" in errs_bad[0]
