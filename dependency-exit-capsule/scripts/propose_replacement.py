#!/usr/bin/env python3
"""
propose_replacement.py - Propose validated replacements for at-risk dependencies.

- Primary: Query open-weight LLM (Ollama or hosted API) using real AST usage evidence.
- Validation Gate: Validate stdlib (sys.stdlib_module_names) or PyPI existence + Python 3.12 compatibility.
- Fallback: Clearly named rule-based knowledge base stored as DATA (references/known_migrations.json).
- Never silently fall back. Enforce --no-fallback to mandate real model output.
"""

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SYSTEM_PROMPT = """You are an expert Python software maintenance agent working under the agentskills.io standard.
Your objective is to propose a safe, backward-compatible replacement or upgrade for an at-risk, abandoned, or incompatible Python dependency.

CRITICAL INSTRUCTIONS:
1. Ground your proposal strictly in the provided AST usage evidence from the codebase.
2. Propose either a Python standard library module (type="stdlib") or an active PyPI package (type="pypi").
3. DO NOT hallucinate nonexistent packages or standard library modules.
4. Output MUST be a valid JSON object matching the required schema. Do not write introductory or concluding prose.
5. Provide step-by-step migration instructions with unified diff snippets, suggested tests, and compatibility gaps.

JSON Schema format:
{
  "proposed_replacement": {
    "package_name": "string (e.g. tomllib, platformdirs, Jinja2)",
    "type": "stdlib" | "pypi",
    "version_specifier": "string or null (e.g. '>=3.0.0')",
    "rationale": "Clear technical justification"
  },
  "migration_steps": [
    {
      "step_number": 1,
      "title": "Short title",
      "description": "Exact refactoring instructions",
      "diff_snippet": "-old_code\\n+new_code"
    }
  ],
  "suggested_tests": [
    {
      "test_name": "test_...",
      "description": "What this test verifies",
      "code_snippet": "def test_...():\\n    ..."
    }
  ],
  "compatibility_gaps": [
    {
      "area": "Topic",
      "description": "Known divergence or API difference",
      "mitigation": "How to handle it"
    }
  ],
  "open_concerns_and_limitations": [
    {
      "title": "Title",
      "description": "Details",
      "severity": "low" | "medium" | "high" | "critical"
    }
  ]
}
"""


def validate_proposed_package(package_name: str, package_type: str, version_spec: str | None = None, timeout: int = 10) -> dict:
    """Validate that proposed package exists in Python standard library or on PyPI and supports Python 3.12."""
    if not package_name:
        return {
            "status": "not_testable",
            "is_valid": False,
            "validation_source": "none",
            "details": "Empty package name proposed."
        }

    clean_name = package_name.strip()

    # 1. Check Python Standard Library
    if clean_name in sys.stdlib_module_names:
        return {
            "status": "verified",
            "is_valid": True,
            "validation_source": "sys.stdlib_module_names",
            "details": f"Module '{clean_name}' is verified in the Python {sys.version_info.major}.{sys.version_info.minor} standard library catalog."
        }
    elif package_type == "stdlib":
        # Check if the model meant PyPI instead of stdlib
        pass

    # 2. Check PyPI JSON API
    pypi_url = f"https://pypi.org/pypi/{urllib.parse.quote(clean_name)}/json"
    req = urllib.request.Request(
        pypi_url,
        headers={"User-Agent": "dependency-exit-capsule/2.0 (+https://agentskills.io)"}
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
            info = data.get("info", {})
            latest = info.get("version", "unknown")
            requires_python = info.get("requires_python") or ""

            # Check Python 3.12 compatibility hint if requires_python is present
            py312_compatible = True
            if requires_python and "<" in requires_python:
                # e.g., "<3.10" or "<3.11"
                if re.search(r"<\s*3\.(?:[0-9]|1[0-1])\b", requires_python):
                    py312_compatible = False

            if not py312_compatible:
                return {
                    "status": "verified",
                    "is_valid": False,
                    "validation_source": "pypi",
                    "details": f"Package '{clean_name}' exists on PyPI but requires_python ('{requires_python}') is incompatible with Python 3.12."
                }

            version_note = ""
            if version_spec:
                releases = data.get("releases", {})
                ver_match = re.search(r"([0-9]+(?:\.[0-9]+)*)", version_spec)
                if ver_match:
                    ver_candidate = ver_match.group(1)
                    if ver_candidate in releases:
                        version_note = f" (verified release {ver_candidate} on PyPI, latest: {latest})"
                    elif ">=" in version_spec or "~=" in version_spec:
                        version_note = f" (compatible with latest {latest} on PyPI)"

            return {
                "status": "verified",
                "is_valid": True,
                "validation_source": "pypi",
                "details": f"Package '{clean_name}' verified on PyPI{version_note} (requires_python: '{requires_python or 'any'}')."
            }
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {
                "status": "verified",
                "is_valid": False,
                "validation_source": "none",
                "details": f"Package '{clean_name}' does not exist on PyPI (HTTP 404) and is not in Python stdlib."
            }
        return {
            "status": "not_testable",
            "is_valid": False,
            "validation_source": "none",
            "details": f"PyPI check failed with HTTP {e.code}: {e.reason}."
        }
    except Exception as e:
        return {
            "status": "not_testable",
            "is_valid": False,
            "validation_source": "none",
            "details": f"Network error querying PyPI: {e}."
        }


def extract_json_block(text: str) -> dict:
    """Extract and parse JSON object from LLM response text."""
    clean = text.strip()
    if "```json" in clean:
        clean = clean.split("```json", 1)[1]
        if "```" in clean:
            clean = clean.split("```", 1)[0]
    elif "```" in clean:
        clean = clean.split("```", 1)[1]
        if "```" in clean:
            clean = clean.split("```", 1)[0]

    clean = clean.strip()
    return json.loads(clean)


def query_ollama(prompt: str, host: str = "http://localhost:11434", model: str = "llama3.2:3b", timeout: int = 120) -> tuple[dict, str]:
    """Query local Ollama instance with JSON format requirement, returning (parsed_dict, raw_str)."""
    url = f"{host.rstrip('/')}/api/generate"
    payload = {
        "model": model,
        "system": SYSTEM_PROMPT,
        "prompt": prompt,
        "format": "json",
        "stream": False
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        res_data = json.loads(response.read().decode("utf-8"))
        raw_content = res_data.get("response", "{}")
        parsed = extract_json_block(raw_content)
        return parsed, raw_content


def query_hosted_api(prompt: str, api_base: str, api_key: str, model: str = "google/gemma-2-9b-it", timeout: int = 120) -> tuple[dict, str]:
    """Query hosted OpenAI-compatible endpoint with JSON mode, returning (parsed_dict, raw_str)."""
    url = f"{api_base.rstrip('/')}/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.1
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        res_data = json.loads(response.read().decode("utf-8"))
        raw_content = res_data["choices"][0]["message"]["content"]
        parsed = extract_json_block(raw_content)
        return parsed, raw_content


def load_known_migration(dep_name: str) -> dict | None:
    """Load known rule-based migration from references/known_migrations.json."""
    kb_path = Path(__file__).resolve().parent.parent / "references" / "known_migrations.json"
    if kb_path.exists():
        try:
            with open(kb_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("migrations", {}).get(dep_name.lower())
        except Exception:
            pass
    return None


def propose_replacement(
    dep_name: str,
    usage_evidence: dict,
    provider: str = "auto",
    ollama_host: str = "http://localhost:11434",
    ollama_model: str = "llama3.2:3b",
    api_base: str | None = None,
    api_key: str | None = None,
    hosted_model: str = "google/gemma-2-9b-it",
    issue: str | None = None,
    no_fallback: bool = False,
    timeout: int = 120,
    evidence_dir: Path | None = None
) -> dict:
    """Query open-weight model for replacement proposal and enforce strict package validation."""
    issue_section = f"\nObserved Compatibility Issue / Error:\n{issue}\n" if issue else ""
    prompt = (
        f"Target at-risk dependency: {dep_name}\n"
        f"{issue_section}\n"
        f"Empirical AST Usage Evidence from codebase:\n"
        f"{json.dumps(usage_evidence, indent=2)}\n\n"
        f"Please provide your migration proposal in strict JSON format. "
        f"Specify target package name, type ('stdlib' or 'pypi'), version specifier if applicable, and migration steps."
    )

    prompt_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    raw_proposal = None
    raw_response_str = None
    call_provider = None
    model_id = None
    model_license = None
    model_card = None
    rejected_candidates = []
    failure_reason = None

    # Try Hosted API
    if provider in ("auto", "hosted") and api_base and api_key:
        try:
            raw_proposal, raw_response_str = query_hosted_api(prompt, api_base, api_key, model=hosted_model, timeout=timeout)
            call_provider = "hosted"
            model_id = hosted_model
            model_license = "Gemma Terms of Use" if "gemma" in hosted_model.lower() else "Open-Weights Community License"
            model_card = "https://ai.google.dev/gemma/terms" if "gemma" in hosted_model.lower() else "https://huggingface.co/"
        except Exception as e:
            failure_reason = f"Hosted API query failed: {e}"
            sys.stderr.write(f"[WARN] {failure_reason}\n")

    # Try Local Ollama
    if raw_proposal is None and provider in ("auto", "ollama"):
        try:
            raw_proposal, raw_response_str = query_ollama(prompt, host=ollama_host, model=ollama_model, timeout=timeout)
            call_provider = "ollama"
            model_id = ollama_model
            if "gemma" in ollama_model.lower():
                model_license = "Gemma Terms of Use"
                model_card = "https://ai.google.dev/gemma/terms"
            elif "llama" in ollama_model.lower():
                model_license = "Llama 3.2 Community License Agreement"
                model_card = "https://github.com/meta-llama/llama-models"
            else:
                model_license = "Open-Weights Community License"
                model_card = "https://ollama.ai/library"
        except Exception as e:
            failure_reason = f"Ollama query failed ({ollama_model}): {e}"
            sys.stderr.write(f"[WARN] {failure_reason}\n")

    # Offline / Fallback handling
    if raw_proposal is None:
        if no_fallback:
            sys.stderr.write(f"[ERROR] Model query failed and --no-fallback was specified: {failure_reason}\n")
            return {
                "provenance": {
                    "provider": "ollama" if provider == "ollama" else "hosted",
                    "model_id": ollama_model if provider == "ollama" else hosted_model,
                    "model_license_name": "N/A",
                    "model_card_url": "N/A",
                    "prompt_sha256": prompt_sha256,
                    "raw_response_path": "none",
                    "validation": {"passed": False, "rejected_candidates": ["no_response_from_model"]}
                },
                "status": "no_valid_proposal",
                "error": failure_reason or "No valid model response received"
            }

        sys.stderr.write(f"[INFO] Accessing rule-based knowledge base (Reason: {failure_reason or 'Explicit offline mode'})\n")
        known = load_known_migration(dep_name)
        if known:
            raw_proposal = known
            raw_response_str = json.dumps(known, indent=2)
            call_provider = "rule_based_knowledge_base"
            model_id = "references/known_migrations.json"
            model_license = "MIT"
            model_card = "https://agentskills.io"
        else:
            return {
                "provenance": {
                    "provider": "rule_based_knowledge_base",
                    "model_id": "none",
                    "model_license_name": "none",
                    "model_card_url": "none",
                    "prompt_sha256": prompt_sha256,
                    "raw_response_path": "none",
                    "validation": {"passed": False, "rejected_candidates": [dep_name]}
                },
                "status": "no_valid_proposal",
                "error": f"No valid proposal generated and no rule-based migration found for '{dep_name}'."
            }

    # Save raw response artifact if evidence_dir provided
    raw_response_path = "in_memory"
    if evidence_dir:
        evidence_dir.mkdir(parents=True, exist_ok=True)
        raw_file = evidence_dir / f"model_raw_response_{dep_name}.json"
        raw_file.write_text(raw_response_str or "{}", encoding="utf-8")
        raw_response_path = str(raw_file.name)

    # Extract proposed package details
    prop_obj = raw_proposal.get("proposed_replacement", {})
    package_name = prop_obj.get("package_name", "").strip()
    package_type = prop_obj.get("type", "pypi")
    rationale = prop_obj.get("rationale", "")
    version_spec = prop_obj.get("version_specifier")

    # VALIDATION GATE
    validation_info = validate_proposed_package(package_name, package_type, version_spec=version_spec, timeout=10)

    gate_passed = validation_info.get("is_valid", False)
    if not gate_passed:
        rejected_candidates.append(f"{package_name}: {validation_info.get('details')}")
        sys.stderr.write(f"[WARN] Validation gate REJECTED '{package_name}': {validation_info.get('details')}\n")

    if validation_info.get("validation_source") == "pypi" and package_type == "stdlib":
        package_type = "pypi"
    elif validation_info.get("validation_source") == "sys.stdlib_module_names":
        package_type = "stdlib"

    provenance = {
        "provider": call_provider,
        "model_id": model_id,
        "model_license_name": model_license,
        "model_card_url": model_card,
        "prompt_sha256": prompt_sha256,
        "raw_response_path": raw_response_path,
        "validation": {
            "passed": gate_passed,
            "rejected_candidates": rejected_candidates
        }
    }

    if not gate_passed:
        return {
            "provenance": provenance,
            "status": "no_valid_proposal",
            "proposed_replacement": {
                "package_name": package_name,
                "type": "none",
                "version_specifier": None,
                "rationale": "Validation gate failed to verify existence or compatibility.",
                "validation": validation_info
            },
            "migration_steps": [],
            "suggested_tests": [],
            "compatibility_gaps": [],
            "open_concerns_and_limitations": []
        }

    # Format steps and findings
    migration_steps = []
    for step in raw_proposal.get("migration_steps", []):
        migration_steps.append({
            "step_number": step.get("step_number", len(migration_steps) + 1),
            "title": step.get("title", ""),
            "description": step.get("description", ""),
            "diff_snippet": step.get("diff_snippet"),
            "status": "unverified"
        })

    suggested_tests = []
    for t in raw_proposal.get("suggested_tests", []):
        suggested_tests.append({
            "test_name": t.get("test_name", ""),
            "description": t.get("description", ""),
            "code_snippet": t.get("code_snippet", ""),
            "status": "unverified"
        })

    compatibility_gaps = []
    for g in raw_proposal.get("compatibility_gaps", []):
        compatibility_gaps.append({
            "area": g.get("area", ""),
            "description": g.get("description", ""),
            "mitigation": g.get("mitigation"),
            "status": "unverified"
        })

    open_concerns = []
    for c in raw_proposal.get("open_concerns_and_limitations", []):
        open_concerns.append({
            "title": c.get("title", ""),
            "description": c.get("description", ""),
            "severity": c.get("severity", "low"),
            "status": "unverified"
        })

    return {
        "provenance": provenance,
        "proposed_replacement": {
            "package_name": package_name,
            "type": package_type,
            "version_specifier": version_spec,
            "rationale": rationale,
            "validation": validation_info
        },
        "migration_steps": migration_steps,
        "suggested_tests": suggested_tests,
        "compatibility_gaps": compatibility_gaps,
        "open_concerns_and_limitations": open_concerns
    }


def main():
    parser = argparse.ArgumentParser(
        description="Propose validated replacement for at-risk dependency with open-weight model."
    )
    parser.add_argument(
        "--dep",
        "--dependency",
        required=True,
        help="Target dependency name (e.g. toml)"
    )
    parser.add_argument(
        "--usage-file",
        required=True,
        help="Path to JSON file containing AST usage mapping from map_usage.py"
    )
    parser.add_argument(
        "--provider",
        choices=["auto", "ollama", "hosted", "offline"],
        default="auto",
        help="Model provider (default: auto)"
    )
    parser.add_argument(
        "--ollama-host",
        default=os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
        help="Ollama host URL"
    )
    parser.add_argument(
        "--ollama-model",
        default=os.environ.get("OLLAMA_MODEL", "gemma2:2b"),
        help="Ollama model name (e.g. gemma2:2b, llama3.2:3b)"
    )
    parser.add_argument(
        "--api-base",
        default=os.environ.get("GEMMA_API_BASE"),
        help="Hosted OpenAI-compatible API base URL"
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("GEMMA_API_KEY"),
        help="Hosted API authorization key"
    )
    parser.add_argument(
        "--hosted-model",
        default="google/gemma-2-9b-it",
        help="Hosted model identifier (default: google/gemma-2-9b-it)"
    )
    parser.add_argument(
        "--no-fallback",
        action="store_true",
        help="Disallow falling back to knowledge base; mandate live model response"
    )
    parser.add_argument(
        "--issue",
        "--context",
        default=None,
        help="Description of observed issue or incompatibility to guide proposal"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Inference request timeout in seconds (default: 120)"
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Path to write JSON output file (default: stdout)"
    )

    args = parser.parse_args()

    usage_path = Path(args.usage_file).resolve()
    if not usage_path.exists():
        sys.stderr.write(f"Usage file not found: {usage_path}\n")
        sys.exit(1)

    with open(usage_path, "r", encoding="utf-8") as f:
        usage_data = json.load(f)

    result = propose_replacement(
        dep_name=args.dep,
        usage_evidence=usage_data.get("usage", usage_data),
        provider=args.provider,
        ollama_host=args.ollama_host,
        ollama_model=args.ollama_model,
        api_base=args.api_base,
        api_key=args.api_key,
        hosted_model=args.hosted_model,
        issue=args.issue,
        no_fallback=args.no_fallback,
        timeout=args.timeout
    )

    formatted = json.dumps(result, indent=2)
    if args.output:
        out_path = Path(args.output).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(formatted)
            f.write("\n")
        sys.stderr.write(f"Wrote proposal to {out_path}\n")
    else:
        print(formatted)


if __name__ == "__main__":
    main()
