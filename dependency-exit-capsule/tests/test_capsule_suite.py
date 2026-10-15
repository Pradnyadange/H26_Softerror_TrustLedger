"""
Unit tests for dependency-exit-capsule skill scripts.
"""

import ast
import json
import tempfile
from pathlib import Path
import pytest
import sys

# Add scripts directory to sys.path
SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import scan_risk
import map_usage
import propose_replacement
import run_diff_tests
import build_capsule


# ============================================================================
# 1. scan_risk.py Tests
# ============================================================================

def test_parse_requirements_txt(tmp_path):
    req_file = tmp_path / "requirements.txt"
    req_file.write_text(
        "toml==0.10.2\n"
        "# Commented line\n"
        "requests>=2.28.0 # inline comment\n"
        "-r other.txt\n"
        "six; python_version < '3.8'\n",
        encoding="utf-8"
    )

    deps = scan_risk.parse_requirements_txt(req_file)
    names = [d["canonical_name"] for d in deps]
    assert "toml" in names
    assert "requests" in names
    assert "six" in names
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
    signals = []
    for pat in scan_risk.DEPRECATION_PATTERNS:
        matches = pat.finditer(sample_text)
        for m in matches:
            signals.append(sample_text[m.start():m.end()])
    assert len(signals) >= 2


# ============================================================================
# 2. map_usage.py Tests
# ============================================================================

def test_map_usage_ast_static_imports(tmp_path):
    code = """
import toml
import toml as t_alias
from toml import load as custom_load

def read_config(path):
    data1 = toml.load(path)
    data2 = t_alias.loads('key = 1')
    data3 = custom_load(path)
    return data1
"""
    py_file = tmp_path / "sample.py"
    py_file.write_text(code, encoding="utf-8")

    result = map_usage.map_dependency_usage(tmp_path, "toml")
    assert result["status"] == "verified"
    assert result["dynamic_imports_detected"] is False
    assert len(result["imports"]) == 3
    assert len(result["calls"]) == 3


def test_map_usage_dynamic_imports_marked_uncertain(tmp_path):
    code = """
import importlib

def dynamic_loader(module_name):
    mod = importlib.import_module(module_name)
    return mod
"""
    py_file = tmp_path / "dynamic_sample.py"
    py_file.write_text(code, encoding="utf-8")

    result = map_usage.map_dependency_usage(tmp_path, "toml")
    assert result["dynamic_imports_detected"] is True
    assert result["status"] == "uncertain"
    assert any(imp["status"] == "uncertain" for imp in result["imports"])


# ============================================================================
# 3. propose_replacement.py Tests
# ============================================================================

def test_validate_proposed_package_stdlib():
    val = propose_replacement.validate_proposed_package("tomllib", "stdlib")
    assert val["status"] == "verified"
    assert val["is_valid"] is True
    assert val["validation_source"] == "sys.stdlib_module_names"


def test_validate_proposed_package_pypi():
    val = propose_replacement.validate_proposed_package("platformdirs", "pypi")
    assert val["status"] == "verified"
    assert val["is_valid"] is True
    assert val["validation_source"] == "pypi"


def test_validate_proposed_package_hallucination_rejected():
    val = propose_replacement.validate_proposed_package("nonexistent-hallucinated-package-xyz-999", "pypi")
    assert val["status"] == "verified"
    assert val["is_valid"] is False
    assert val["validation_source"] == "none"


def test_extract_json_block():
    markdown_wrapped = "```json\n{\"test\": 123}\n```"
    parsed = propose_replacement.extract_json_block(markdown_wrapped)
    assert parsed == {"test": 123}


# ============================================================================
# 4. run_diff_tests.py Tests
# ============================================================================

def test_parse_junit_xml(tmp_path):
    xml_content = """<?xml version="1.0" encoding="utf-8"?>
<testsuite name="pytest" tests="3" errors="0" failures="1" skipped="0" time="1.5">
    <testcase classname="test_mod" name="test_one" time="0.1" />
    <testcase classname="test_mod" name="test_two" time="0.2">
        <failure message="assertion failed">traceback</failure>
    </testcase>
    <testcase classname="test_mod" name="test_three" time="0.3" />
</testsuite>"""
    xml_file = tmp_path / "test.xml"
    xml_file.write_text(xml_content, encoding="utf-8")

    parsed = run_diff_tests.parse_junit_xml(xml_file)
    assert parsed["total"] == 3
    assert parsed["passed"] == 2
    assert parsed["failed"] == 1
    assert "test_mod::test_two" in parsed["failures"]


# ============================================================================
# 5. build_capsule.py Tests
# ============================================================================

def test_build_capsule_validation_strict_separation():
    # Valid sample payload
    valid_capsule = {
        "schema_version": "1.0.0",
        "capsule_id": "capsule-test-1",
        "generated_at": "2026-10-15T00:00:00Z",
        "target_repo": {"name": "test", "path": "/test", "python_version": "3.12"},
        "target_dependency": {
            "name": "toml",
            "declared_specifier": "==0.10.2",
            "source_file": "requirements.txt",
            "latest_pypi_version": "0.10.2",
            "pypi_url": "https://pypi.org/project/toml/",
            "repository_url": "https://github.com/uiri/toml"
        },
        "observed": {
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
            "model_metadata": {"name": "gemma", "version": "2b", "access_method": "ollama", "license": "Gemma"},
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
        "schema_version": "1.0.0",
        "capsule_id": "capsule-test-1",
        "generated_at": "2026-10-15T00:00:00Z",
        "target_repo": {"name": "test", "path": "/test", "python_version": "3.12"},
        "target_dependency": {
            "name": "toml",
            "declared_specifier": "==0.10.2",
            "source_file": "requirements.txt",
            "latest_pypi_version": "0.10.2",
            "pypi_url": "https://pypi.org/project/toml/",
            "repository_url": "https://github.com/uiri/toml"
        },
        "observed": {
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
            "model_metadata": {"name": "gemma", "version": "2b", "access_method": "ollama", "license": "Gemma"},
            "proposed_replacement": {
                "package_name": "tomllib",
                "type": "stdlib",
                "version_specifier": None,
                "rationale": "Builtin",
                "validation": {"status": "verified", "is_valid": True, "validation_source": "sys.stdlib_module_names", "details": "Verified"}
            },
            "migration_steps": [],
            "suggested_tests": [],
            "compatibility_gaps": [],
            "open_concerns_and_limitations": []
        }
    }
    md = build_capsule.render_markdown_report(capsule)
    assert "# 🛡️ Dependency Exit Capsule: `toml`" in md
    assert "Part 1: Observed Evidence" in md
    assert "Part 2: AI-Generated Migration Proposal" in md


# ============================================================================
# 5. Version-Compatibility Fix & Extension Tests
# ============================================================================

def test_propose_replacement_compatibility_expert():
    usage_sample = {
        "status": "verified",
        "total_occurrences": 3,
        "imports": [{"file": "linkwatch/report.py", "line": 3, "imported_symbol": "jinja2.Environment", "status": "verified"}],
        "calls": [{"file": "linkwatch/report.py", "line": 9, "call_expression": "Environment()", "status": "verified"}]
    }
    res = propose_replacement.propose_replacement(
        dep_name="jinja2",
        usage_evidence=usage_sample,
        provider="reference",
        issue="ImportError: cannot import name 'soft_unicode' from 'markupsafe'"
    )
    assert res["proposed_replacement"]["package_name"].lower() == "jinja2"
    assert res["proposed_replacement"]["type"] == "pypi"
    assert res["proposed_replacement"]["validation"]["is_valid"] is True
    assert res["proposed_replacement"]["validation"]["validation_source"] == "pypi"
    assert len(res["migration_steps"]) >= 1


def test_propose_replacement_type_correction():
    # If LLM hallucinates type="stdlib" for a PyPI package (Jinja2), type must be corrected to "pypi"
    val = propose_replacement.validate_proposed_package("jinja2", "stdlib")
    assert val["is_valid"] is True
    assert val["validation_source"] == "pypi"


def test_apply_replacement_patch_jinja2(tmp_path):
    repo = tmp_path / "repo_B"
    repo.mkdir()
    req = repo / "requirements.txt"
    req.write_text("toml==0.10.2\nJinja2==2.11.3\n", encoding="utf-8")
    pyproj = repo / "pyproject.toml"
    pyproj.write_text('[project]\ndependencies = [\n    "Jinja2==2.11.3",\n]\n', encoding="utf-8")

    # Test candidate B: upgrade Jinja2
    run_diff_tests.apply_replacement_patch(repo, "jinja2", "Jinja2>=3.1.2")
    assert "Jinja2>=3.1.2" in req.read_text(encoding="utf-8")
    assert "Jinja2==2.11.3" not in req.read_text(encoding="utf-8")
    assert '"Jinja2>=3.1.2"' in pyproj.read_text(encoding="utf-8")
