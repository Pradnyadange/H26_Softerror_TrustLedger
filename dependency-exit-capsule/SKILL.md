---
name: dependency-exit-capsule
description: Find at-risk Python dependencies (abandoned, unmaintained, yanked, or deprecated), map real AST usage, propose validated replacements using Gemma, run isolated differential test suites, and generate a verified Dependency Exit Capsule.
---

# Dependency Exit Capsule (`dependency-exit-capsule`)

An Agent Skill adhering to the `agentskills.io` standard for discovering at-risk dependencies in Python repositories, mapping their exact AST call sites, generating validated replacements via Gemma, differentials testing before/after regressions, and producing an empirical **Dependency Exit Capsule**.

> [!IMPORTANT]
> **Zero Vulnerability Focus:** This skill deliberately ignores security CVEs and advisory alerts. It focuses exclusively on software maintenance risk (unmaintained packages, stale releases, yanked versions, dead repositories, deprecation announcements, and stdlib migration opportunities).

---

## When to Use This Skill

Activate this skill when:
1. Auditing a Python repository for stale, unmaintained, or legacy dependencies (e.g. `toml`, `appdirs`, `six`, `nose`).
2. Preparing an upgrade plan to migrate away from an unmaintained package to modern standard library modules (e.g., `tomllib` in Python 3.11+) or active community alternatives (e.g., `platformdirs`).
3. Verifying that a dependency replacement does not cause silent behavioral regressions by running isolated differential pytest runs.
4. Generating a strict, auditable **Dependency Exit Capsule** where empirical evidence is segregated from AI hypotheses.

---

## Architecture & Directory Layout

```
dependency-exit-capsule/
├── SKILL.md                          # Skill definition & agent instruction manual
├── README.md                         # Architecture, model provenance, and usage
├── references/
│   └── capsule-schema.json          # JSON Schema enforcing observed vs ai_generated separation
├── scripts/
│   ├── scan_risk.py                 # Factual risk discovery across PyPI and GitHub
│   ├── map_usage.py                 # AST-based static import and call site mapper
│   ├── propose_replacement.py       # Gemma client with stdlib/PyPI existence validation
│   ├── run_diff_tests.py            # Isolated venv baseline vs replacement diff tester
│   └── build_capsule.py             # Capsule assembler, schema validator, and Markdown renderer
├── assets/                          # Generated capsules and intermediate artifacts
└── tests/
    └── test_capsule_suite.py        # Automated test suite (pytest)
```

---

## Step-by-Step Execution Workflow

To audit and exit an at-risk dependency, execute the scripts sequentially:

### Step 1: Scan Repository for Factual Risk Indicators
Scan `requirements*.txt` and `pyproject.toml`. PyPI and GitHub APIs are queried concurrently. Contains zero subjective opinions.

```bash
# Scan all dependencies in a target repo
python scripts/scan_risk.py --repo-path <PATH_TO_REPO> --output assets/scan_results.json

# Or scan a single candidate dependency
python scripts/scan_risk.py --repo-path <PATH_TO_REPO> --dep toml --output assets/scan_toml.json
```

**Key Flags:**
- `--repo-path`: Path to target repository root (default: `.`)
- `--dep`: Optional filter for a specific dependency name
- `--github-token`: Optional GitHub token (or set `GITHUB_TOKEN` environment variable)
- `--timeout`: HTTP network timeout in seconds (default: 10)
- `--output`: File destination for output JSON

---

### Step 2: Map Real Codebase Usage via AST
Map all imports, aliases, and function/method call sites for the targeted dependency using the Python standard library `ast` module. Dynamic imports (`importlib`, `__import__`) are automatically flagged as `uncertain`.

```bash
python scripts/map_usage.py --repo-path <PATH_TO_REPO> --dep toml --output assets/usage_toml.json
```

**Key Flags:**
- `--repo-path`: Path to target repository
- `--dep`: Name of dependency module to track (e.g. `toml`, `appdirs`)
- `--output`: File destination for AST mapping JSON

---

### Step 3: Propose Replacement with Gemma & Validate Existence
Send the dependency name and empirical AST usage evidence to Gemma. Enforce JSON output. Then, validate that the suggested package exists in Python's standard library (`sys.stdlib_module_names`) or on PyPI. Reject hallucinations.

```bash
# Via local Ollama (Gemma or any local LLM)
python scripts/propose_replacement.py --dep toml --usage-file assets/usage_toml.json --provider ollama --ollama-model gemma2:2b --output assets/proposal_toml.json

# Via Hosted OpenAI-compatible API
python scripts/propose_replacement.py --dep toml --usage-file assets/usage_toml.json --provider hosted --api-base https://api.groq.com/openai/v1 --api-key $API_KEY --hosted-model google/gemma-2-9b-it --output assets/proposal_toml.json

# Deterministic reference expert mode (offline / CI)
python scripts/propose_replacement.py --dep toml --usage-file assets/usage_toml.json --provider reference --output assets/proposal_toml.json
```

**Key Flags:**
- `--dep`: Target dependency name
- `--usage-file`: Path to JSON file generated in Step 2
- `--issue`: Optional description of compatibility error / deprecation failure
- `--provider`: `auto` | `ollama` | `hosted` | `reference`
- `--ollama-host`: Host URL for Ollama daemon (default: `http://localhost:11434`)
- `--ollama-model`: Model tag (default: `gemma2:2b`, e.g. `llama3.2:3b`)
- `--output`: File destination for proposal JSON

---

### Step 4: Run Isolated Differential Tests
Copy the repository into a temporary directory (never editing original code). Create Virtualenv A (original dependencies) and Virtualenv B (replacement + code patch). Execute `pytest --junitxml` in both. Compare results per test. Built-in migration templates are available for `toml`, `appdirs`, and `Jinja2`.

> [!IMPORTANT]
> Report ONLY new failures as attributable to the replacement. Pre-existing test failures that failed in baseline are excluded.

```bash
python scripts/run_diff_tests.py --repo-path <PATH_TO_REPO> --dep toml --replacement tomllib --type stdlib --output assets/diff_tests_toml.json
```

**Key Flags:**
- `--repo-path`: Path to original target repo
- `--dep`: Original dependency name (e.g. `toml`, `Jinja2`)
- `--replacement`: Proposed replacement package name (e.g. `tomllib`, `platformdirs`, or `Jinja2>=3.1.2`)
- `--type`: `stdlib` or `pypi`
- `--patch-file`: Optional unified diff patch file (built-in templates used if omitted)
- `--output`: File destination for differential results JSON

---

### Step 5: Assemble and Validate Dependency Exit Capsule
Assemble the findings from Steps 1–4, validate against `references/capsule-schema.json`, and render the final Markdown Exit Capsule.

```bash
python scripts/build_capsule.py \
  --dep toml \
  --repo-path <PATH_TO_REPO> \
  --risk-file assets/scan_toml.json \
  --usage-file assets/usage_toml.json \
  --proposal-file assets/proposal_toml.json \
  --diff-test-file assets/diff_tests_toml.json \
  --schema references/capsule-schema.json \
  --output-json assets/capsule_toml.json \
  --output-md assets/capsule_toml.md
```

---

## Capsule Inviolable Rules

1. **Two Separate Top-Level Sections:**
   - `"observed"`: Script outputs, test results, PyPI/GitHub risk facts, AST usage locations.
   - `"ai_generated"`: Replacement proposal, migration steps, suggested tests, gap analysis, model provenance.
2. **Never Mix AI Claims into Observed:**
   - Schema validation fails immediately if any AI hypothesis is found in the `observed` block.
3. **Status Taxonomy:**
   - Every single observation and AI finding must declare a status: `verified`, `unverified`, or `not_testable`.
   - AI proposals are marked `unverified` by default.
   - Package existence check and test runs are marked `verified`.
