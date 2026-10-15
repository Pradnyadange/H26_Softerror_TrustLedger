# 🛡️ Dependency Exit Capsule: `toml`

**Capsule ID:** `capsule-linkwatch-toml-202610150717`  
**Generated At:** `2026-10-15T07:17:47.724925+00:00`  
**Target Repository:** `LinkWatch` (`D:\mlh\LinkWatch`)  
**Python Runtime:** Python 3.12  
**Schema Version:** `1.0.0`  

---

## 🔬 Part 1: Observed Evidence (Empirical & Verifiable)
> [!NOTE]
> All findings in this section are strictly derived from registry metadata, AST static analysis,
> and isolated differential test execution. No AI-generated content is present here.

### 1.1 Upstream Registry & Risk Indicators
**Status:** `VERIFIED`

| Metric | Observed Value |
| :--- | :--- |
| **Target Dependency** | `toml` |
| **Declared Specifier** | `==0.10.2` |
| **Source File** | `requirements.txt` |
| **Latest PyPI Version** | `0.10.2` |
| **Last PyPI Release Date** | `2020-11-01T01:40:22.204866+00:00` |
| **Staleness (Days Elapsed)** | `2174 days` |
| **Yanked Status** | `No` |
| **Repository URL** | `https://github.com/uiri/toml` |
| **GitHub Archived** | `Unknown` |
| **GitHub Last Push** | `N/A` |
| **API Notes** | `GitHub API: HTTP 403: rate limit exceeded` |

### 1.2 Codebase AST Usage Map
**Status:** `VERIFIED` | **Total Occurrences:** `2` | **Dynamic Imports Detected:** `None`

#### Imports Discovered
| File | Line | Imported Symbol | Alias | Dynamic | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `linkwatch/config.py` | Line 3 | `toml` | *none* | No | `verified` |

#### Function & Method Calls Discovered
| File | Line | Call Expression | Status |
| :--- | :--- | :--- | :--- |
| `linkwatch/config.py` | Line 37 | `toml.load(path)` | `verified` |

### 1.3 Executed Differential Test Results
**Status:** `VERIFIED`

| Test Suite Metric | Venv A (Baseline Original) | Venv B (Replacement + Patch) | Delta |
| :--- | :--- | :--- | :--- |
| **Exit Code** | `1` | `1` | - |
| **Total Tests** | `10` | `10` | - |
| **Passed** | `9` | `9` | - |
| **Failed** | `1` | `1` | - |
| **Duration** | `9.325s` | `9.23s` | - |

#### Attributable Regressions Analysis
> [!TIP]
> **Zero new failures attributable to replacement.** All existing passing tests remained green.

**Notes:** Differential analysis executed 10 baseline tests vs 10 replacement tests. Found 0 new failure(s) attributable to replacement, and 0 resolved failure(s).

---

## 🤖 Part 2: AI-Generated Migration Proposal (Model-Assisted)
> [!CAUTION]
> Findings in this section are model-generated recommendations. Each item is marked `unverified`
> until manually confirmed or exercised in tests.

### 2.1 Model Provenance & Licensing
- **Model Name:** `gemma-2-9b-reference`
- **Model Version:** `9b`
- **Access Method:** `reference_expert`
- **License:** `Gemma Terms of Use`

### 2.2 Proposed Replacement Package
**Target Replacement:** `tomllib` (stdlib) — **✅ VALIDATED**

**Validation Source:** `sys.stdlib_module_names` | **Validation Status:** `VERIFIED`
**Verification Details:** Module 'tomllib' verified in Python 3.12 standard library.

**Rationale:** Python 3.11+ includes tomllib in the standard library (PEP 680), eliminating third-party unmaintained TOML dependencies.

### 2.3 Step-by-Step Migration Plan
#### Step 1: Replace imports in config loader `[unverified]`
Change 'import toml' to 'import tomllib' in linkwatch/config.py.
```diff
-import toml
+import tomllib
```

#### Step 2: Update toml.load call to binary file handle `[unverified]`
tomllib.load requires a binary read mode file descriptor ('rb') rather than taking a string path.
```diff
-    data = toml.load(path)
+    with open(path, 'rb') as f:
+        data = tomllib.load(f)
```

#### Step 3: Remove toml from requirements.txt and pyproject.toml `[unverified]`
Remove toml==0.10.2 from requirements.txt and pyproject.toml dependencies.
```diff
-toml==0.10.2
```

### 2.4 Suggested Tests for Regression Verification
#### `test_load_settings_tomllib` `[unverified]`
Verify that load_settings successfully parses sites.toml with tomllib and preserves all data keys.
```python
def test_load_settings_tomllib(tmp_path):
    toml_file = tmp_path / 'sites.toml'
    toml_file.write_text('[linkwatch]\ntitle = "test"\n[[linkwatch.sites]]\nname = "example"\nurl = "https://example.com"', encoding='utf-8')
    from linkwatch.config import load_settings
    s = load_settings(str(toml_file))
    assert s.title == 'test'

```

### 2.5 Compatibility Gaps & Breaking Changes
- **File Mode** `[unverified]`: toml.load accepted a file path string or text handle. tomllib.load strictly requires a binary file handle opened with mode 'rb'.
  - *Mitigation:* Wrap the file reading with 'with open(path, "rb") as f: tomllib.load(f)'.
- **Write Support** `[unverified]`: tomllib is read-only and does not implement a dump() function.
  - *Mitigation:* Verified that codebase only performs reads (load), so write support is not required.

### 2.6 Open Concerns & Limitations
- 🟡 **Minimum Python Version** (Severity: `LOW`) `[unverified]`
  tomllib requires Python >= 3.11. If backwards compatibility with Python 3.10 is required, tomli must be used as a conditional fallback.

