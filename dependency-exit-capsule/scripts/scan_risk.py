#!/usr/bin/env python3
"""
scan_risk.py - Scan Python dependencies for factual risk indicators.

Reads requirements*.txt and pyproject.toml in a repository.
Queries PyPI JSON API and GitHub REST API for:
- Last release date and days elapsed
- Yanked status and reason
- Repository archive status and last push date
- Explicit deprecation statements in metadata / description

Outputs strict empirical risk indicators in JSON to stdout.
Contains NO opinions or subjective assessments.
"""

import argparse
import datetime
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# Python 3.11+ stdlib tomllib
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib  # fallback if running on older Python
    except ImportError:
        tomllib = None

# Regex to detect dependency specifications in requirements.txt
REQ_PATTERN = re.compile(
    r"^\s*([A-Za-z0-9_.\-]+)\s*([<>=!~].*)?$"
)

# Common deprecation phrases to search for in package description/readme
DEPRECATION_PATTERNS = [
    re.compile(r"\b(?:is\s+)?deprecated\b", re.IGNORECASE),
    re.compile(r"\bno\s+longer\s+maintained\b", re.IGNORECASE),
    re.compile(r"\bunmaintained\b", re.IGNORECASE),
    re.compile(r"\bend\s+of\s+life\b", re.IGNORECASE),
    re.compile(r"\barchived\s+repository\b", re.IGNORECASE),
    re.compile(r"\bsuperseded\s+by\b", re.IGNORECASE),
    re.compile(r"\bplease\s+use\s+[a-zA-Z0-9_\-]+\s+instead\b", re.IGNORECASE),
]


def normalize_name(name: str) -> str:
    """Canonicalize Python package name per PEP 503."""
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_requirements_txt(file_path: Path) -> list[dict]:
    """Parse dependency names and specifiers from a requirements*.txt file."""
    dependencies = []
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            for line_no, raw_line in enumerate(f, start=1):
                line = raw_line.strip()
                # Ignore empty lines and full line comments
                if not line or line.startswith("#"):
                    continue
                # Strip inline comments
                if " #" in line:
                    line = line.split(" #", 1)[0].strip()
                # Ignore flags like -r, -i, --extra-index-url
                if line.startswith("-"):
                    continue

                # Strip environment markers (e.g., ; python_version < '3.8')
                spec_part = line.split(";", 1)[0].strip()

                match = REQ_PATTERN.match(spec_part)
                if match:
                    pkg_name = match.group(1)
                    specifier = (match.group(2) or "").strip()
                    dependencies.append({
                        "name": pkg_name,
                        "canonical_name": normalize_name(pkg_name),
                        "specifier": specifier,
                        "source_file": file_path.name,
                        "line": line_no
                    })
    except Exception as e:
        sys.stderr.write(f"[WARN] Failed to read {file_path}: {e}\n")
    return dependencies


def parse_pyproject_toml(file_path: Path) -> list[dict]:
    """Parse dependency names and specifiers from pyproject.toml."""
    dependencies = []
    if not tomllib:
        sys.stderr.write("[WARN] tomllib not available, skipping pyproject.toml\n")
        return dependencies

    try:
        with open(file_path, "rb") as f:
            data = tomllib.load(f)

        raw_deps = []
        # PEP 621 project.dependencies
        project_table = data.get("project", {})
        raw_deps.extend(project_table.get("dependencies", []))

        # PEP 621 project.optional-dependencies
        opt_deps = project_table.get("optional-dependencies", {})
        for group in opt_deps.values():
            if isinstance(group, list):
                raw_deps.extend(group)

        # Poetry dependencies
        poetry_deps = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
        for name, spec in poetry_deps.items():
            if name.lower() != "python":
                if isinstance(spec, str):
                    raw_deps.append(f"{name}{spec}")
                else:
                    raw_deps.append(name)

        for dep_str in raw_deps:
            clean_str = dep_str.strip().split(";", 1)[0].strip()
            match = REQ_PATTERN.match(clean_str)
            if match:
                pkg_name = match.group(1)
                specifier = (match.group(2) or "").strip()
                dependencies.append({
                    "name": pkg_name,
                    "canonical_name": normalize_name(pkg_name),
                    "specifier": specifier,
                    "source_file": file_path.name,
                    "line": None
                })
    except Exception as e:
        sys.stderr.write(f"[WARN] Failed to parse {file_path}: {e}\n")

    return dependencies


def extract_github_coords(urls: list[str]) -> tuple[str | None, str | None, str | None]:
    """Extract owner and repo from a list of URLs if any point to GitHub."""
    for url in urls:
        if not url or "github.com" not in url:
            continue
        # Match github.com/<owner>/<repo>
        match = re.search(r"github\.com/([A-Za-z0-9_.\-]+)/([A-Za-z0-9_.\-]+)", url)
        if match:
            owner = match.group(1)
            repo = match.group(2)
            if repo.endswith(".git"):
                repo = repo[:-4]
            # Filter out non-repo paths like github.com/sponsors, github.com/features
            if owner.lower() in ("sponsors", "features", "topics", "collections"):
                continue
            canonical_url = f"https://github.com/{owner}/{repo}"
            return owner, repo, canonical_url
    return None, None, None


def query_pypi(package_name: str, timeout: int = 10) -> dict:
    """Query PyPI JSON API for release history and metadata."""
    url = f"https://pypi.org/pypi/{urllib.parse.quote(package_name)}/json"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "dependency-exit-capsule/1.0 (+https://agentskills.io)"}
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
            return {"success": True, "data": data, "error": None}
    except urllib.error.HTTPError as e:
        return {"success": False, "data": None, "error": f"HTTP {e.code}: {e.reason}"}
    except Exception as e:
        return {"success": False, "data": None, "error": str(e)}


def query_github_repo(owner: str, repo: str, token: str | None = None, timeout: int = 10) -> dict:
    """Query GitHub REST API for repository archive status and last push date."""
    url = f"https://api.github.com/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(repo)}"
    headers = {
        "User-Agent": "dependency-exit-capsule/1.0",
        "Accept": "application/vnd.github.v3+json"
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
            return {"success": True, "data": data, "error": None}
    except urllib.error.HTTPError as e:
        return {"success": False, "data": None, "error": f"HTTP {e.code}: {e.reason}"}
    except Exception as e:
        return {"success": False, "data": None, "error": str(e)}


def scan_dependency_risk(dep: dict, github_token: str | None = None, timeout: int = 10) -> dict:
    """Gather factual risk indicators for a single dependency without subjective opinions."""
    pkg_name = dep["name"]
    pypi_url_endpoint = f"https://pypi.org/pypi/{urllib.parse.quote(pkg_name)}/json"
    pypi_result = query_pypi(pkg_name, timeout=timeout)
    now = datetime.datetime.now(datetime.timezone.utc)
    fetch_ts = now.isoformat()

    result = {
        "package_name": pkg_name,
        "canonical_name": dep["canonical_name"],
        "declared_specifier": dep["specifier"],
        "source_file": dep["source_file"],
        "pypi_verified": False,
        "latest_version": None,
        "pypi_url": f"https://pypi.org/project/{pkg_name}/",
        "last_release_date": None,
        "days_since_last_release": None,
        "yanked": False,
        "yanked_reason": None,
        "repository_url": None,
        "github_archived": None,
        "github_last_push": None,
        "days_since_last_push": None,
        "deprecation_signals": [],
        "risk_status": "unverified",
        "indicator_metadata": {
            "staleness_statement": "Staleness is an empirical indicator of inactivity, not proof of project abandonment.",
            "indicators": {}
        },
        "notes": []
    }

    if not pypi_result["success"]:
        result["risk_status"] = "not_testable"
        result["notes"].append(f"PyPI API error: {pypi_result['error']}")
        result["indicator_metadata"]["indicators"]["pypi_status"] = {
            "source_url": pypi_url_endpoint,
            "fetched_at": fetch_ts,
            "raw_value": "unavailable",
            "status": "unavailable",
            "error": pypi_result["error"]
        }
        return result

    pypi_data = pypi_result["data"]
    info = pypi_data.get("info", {})
    result["pypi_verified"] = True
    result["latest_version"] = info.get("version")
    result["yanked"] = bool(info.get("yanked", False))
    result["yanked_reason"] = info.get("yanked_reason")

    # Record PyPI indicators with full provenance
    result["indicator_metadata"]["indicators"]["yanked"] = {
        "source_url": pypi_url_endpoint,
        "fetched_at": fetch_ts,
        "raw_value": result["yanked"],
        "reason": result["yanked_reason"]
    }

    # Find latest release date from releases dictionary
    releases = pypi_data.get("releases", {})
    latest_upload_dt = None

    for ver, files in releases.items():
        for f in files:
            upload_str = f.get("upload_time_iso_8601")
            if upload_str:
                try:
                    clean_ts = upload_str.replace("Z", "+00:00")
                    dt = datetime.datetime.fromisoformat(clean_ts)
                    if latest_upload_dt is None or dt > latest_upload_dt:
                        latest_upload_dt = dt
                except Exception:
                    pass

    if latest_upload_dt:
        result["last_release_date"] = latest_upload_dt.isoformat()
        result["days_since_last_release"] = (now - latest_upload_dt).days
        result["indicator_metadata"]["indicators"]["last_release"] = {
            "source_url": pypi_url_endpoint,
            "fetched_at": fetch_ts,
            "raw_value": result["last_release_date"],
            "days_elapsed": result["days_since_last_release"]
        }
    else:
        result["indicator_metadata"]["indicators"]["last_release"] = {
            "source_url": pypi_url_endpoint,
            "fetched_at": fetch_ts,
            "raw_value": "unavailable",
            "days_elapsed": None
        }

    # Search for candidate repository URLs
    url_candidates = []
    if info.get("project_urls"):
        url_candidates.extend(info["project_urls"].values())
    if info.get("home_page"):
        url_candidates.append(info["home_page"])
    if info.get("package_url"):
        url_candidates.append(info["package_url"])

    owner, repo, gh_url = extract_github_coords(url_candidates)
    if gh_url:
        result["repository_url"] = gh_url

    # Check for deprecation signals in package summary and description
    description_text = (info.get("summary") or "") + "\n" + (info.get("description") or "")
    for pattern in DEPRECATION_PATTERNS:
        matches = pattern.finditer(description_text)
        for m in matches:
            start = max(0, m.start() - 40)
            end = min(len(description_text), m.end() + 60)
            snippet = description_text[start:end].replace("\n", " ").strip()
            snippet = re.sub(r"\s+", " ", snippet)
            if snippet not in result["deprecation_signals"]:
                result["deprecation_signals"].append(snippet)
                if len(result["deprecation_signals"]) >= 5:
                    break
        if len(result["deprecation_signals"]) >= 5:
            break

    # Query GitHub if repository coordinates found
    if owner and repo:
        gh_endpoint = f"https://api.github.com/repos/{owner}/{repo}"
        gh_result = query_github_repo(owner, repo, token=github_token, timeout=timeout)
        if gh_result["success"]:
            gh_data = gh_result["data"]
            result["github_archived"] = gh_data.get("archived", False)
            pushed_at = gh_data.get("pushed_at")
            if pushed_at:
                result["github_last_push"] = pushed_at
                try:
                    pushed_dt = datetime.datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
                    result["days_since_last_push"] = (now - pushed_dt).days
                except Exception:
                    pass
            result["risk_status"] = "verified"
            result["indicator_metadata"]["indicators"]["github_status"] = {
                "source_url": gh_endpoint,
                "fetched_at": fetch_ts,
                "raw_value": {
                    "archived": result["github_archived"],
                    "pushed_at": result["github_last_push"],
                    "days_since_last_push": result["days_since_last_push"]
                }
            }
        else:
            err_msg = gh_result["error"]
            result["notes"].append(f"GitHub API: {err_msg}")
            result["risk_status"] = "verified"  # PyPI facts are verified
            result["indicator_metadata"]["indicators"]["github_status"] = {
                "source_url": gh_endpoint,
                "fetched_at": fetch_ts,
                "raw_value": "unavailable",
                "error": err_msg
            }
    else:
        result["risk_status"] = "verified"
        result["indicator_metadata"]["indicators"]["github_status"] = {
            "source_url": None,
            "fetched_at": fetch_ts,
            "raw_value": "unavailable",
            "reason": "no_github_repository_url_declared"
        }

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Scan dependencies in requirements*.txt and pyproject.toml for objective risk indicators."
    )
    parser.add_argument(
        "--repo-path",
        default=".",
        help="Path to repository root (default: current directory)"
    )
    parser.add_argument(
        "--dep",
        "--dependency",
        dest="target_dep",
        default=None,
        help="Optional name of a single dependency to scan"
    )
    parser.add_argument(
        "--github-token",
        default=os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN"),
        help="GitHub Personal Access Token for rate limit bypass (or env GITHUB_TOKEN)"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=10,
        help="HTTP request timeout in seconds (default: 10)"
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Path to write JSON output file (default: stdout)"
    )

    args = parser.parse_args()
    repo_dir = Path(args.repo_path).resolve()

    if not repo_dir.exists() or not repo_dir.is_dir():
        sys.stderr.write(f"Error: repo path does not exist or is not a directory: {repo_dir}\n")
        sys.exit(1)

    # Collect dependencies from requirements*.txt and pyproject.toml
    found_deps: dict[str, dict] = {}

    # Scan requirements*.txt
    for req_file in sorted(repo_dir.glob("requirements*.txt")):
        for item in parse_requirements_txt(req_file):
            cname = item["canonical_name"]
            if cname not in found_deps:
                found_deps[cname] = item

    # Scan pyproject.toml
    pyproject = repo_dir / "pyproject.toml"
    if pyproject.is_file():
        for item in parse_pyproject_toml(pyproject):
            cname = item["canonical_name"]
            if cname not in found_deps:
                found_deps[cname] = item

    if not found_deps:
        sys.stderr.write("No dependencies discovered in requirements*.txt or pyproject.toml.\n")
        output_payload = {
            "target_repo": str(repo_dir),
            "scan_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "total_dependencies": 0,
            "dependencies": []
        }
        json.dump(output_payload, sys.stdout, indent=2)
        sys.exit(0)

    # Filter by specific dependency if requested
    target_canonical = normalize_name(args.target_dep) if args.target_dep else None
    deps_to_scan = [
        d for d in found_deps.values()
        if not target_canonical or d["canonical_name"] == target_canonical
    ]

    if not deps_to_scan and target_canonical:
        sys.stderr.write(f"Dependency '{args.target_dep}' not found in requirements or pyproject.toml.\n")
        sys.exit(1)

    from concurrent.futures import ThreadPoolExecutor, as_completed

    scan_results = []
    # Use ThreadPoolExecutor for fast parallel scanning across dependencies
    max_workers = min(8, len(deps_to_scan))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_dep = {
            executor.submit(
                scan_dependency_risk,
                dep,
                github_token=args.github_token,
                timeout=args.timeout
            ): dep
            for dep in deps_to_scan
        }
        for future in as_completed(future_to_dep):
            try:
                res = future.result()
                scan_results.append(res)
            except Exception as e:
                dep_orig = future_to_dep[future]
                sys.stderr.write(f"[ERROR] Scanning {dep_orig['name']} failed: {e}\n")

    # Sort results by days_since_last_release descending (most stale first)
    def sort_key(item):
        days = item.get("days_since_last_release")
        return -1 if days is None else days

    scan_results.sort(key=sort_key, reverse=True)

    payload = {
        "target_repo": str(repo_dir),
        "scan_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "total_dependencies": len(scan_results),
        "dependencies": scan_results
    }

    formatted_json = json.dumps(payload, indent=2)

    if args.output:
        out_path = Path(args.output).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(formatted_json)
            f.write("\n")
        sys.stderr.write(f"Wrote scan results to {out_path}\n")
    else:
        print(formatted_json)


if __name__ == "__main__":
    main()
