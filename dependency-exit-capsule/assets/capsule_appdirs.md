# 🛡️ Dependency Exit Capsule: `appdirs`

**Capsule ID:** `capsule-linkwatch-appdirs-202610150721`  
**Generated At:** `2026-10-15T07:21:57.063023+00:00`  
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
| **Target Dependency** | `appdirs` |
| **Declared Specifier** | `==1.4.4` |
| **Source File** | `requirements.txt` |
| **Latest PyPI Version** | `1.4.4` |
| **Last PyPI Release Date** | `2020-05-11T07:59:51.037820+00:00` |
| **Staleness (Days Elapsed)** | `2347 days` |
| **Yanked Status** | `No` |
| **Repository URL** | `https://github.com/ActiveState/appdirs` |
| **GitHub Archived** | `Unknown` |
| **GitHub Last Push** | `N/A` |
| **API Notes** | `GitHub API: HTTP 403: rate limit exceeded` |

### 1.2 Codebase AST Usage Map
**Status:** `VERIFIED` | **Total Occurrences:** `2` | **Dynamic Imports Detected:** `None`

#### Imports Discovered
| File | Line | Imported Symbol | Alias | Dynamic | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `linkwatch/cache.py` | Line 4 | `appdirs.user_cache_dir` | *none* | No | `verified` |

#### Function & Method Calls Discovered
| File | Line | Call Expression | Status |
| :--- | :--- | :--- | :--- |
| `linkwatch/cache.py` | Line 10 | `user_cache_dir('linkwatch')` | `verified` |

### 1.3 Executed Differential Test Results
**Status:** `VERIFIED`

| Test Suite Metric | Venv A (Baseline Original) | Venv B (Replacement + Patch) | Delta |
| :--- | :--- | :--- | :--- |
| **Exit Code** | `1` | `1` | - |
| **Total Tests** | `10` | `10` | - |
| **Passed** | `9` | `9` | - |
| **Failed** | `1` | `1` | - |
| **Duration** | `9.309s` | `9.331s` | - |

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
**Target Replacement:** `platformdirs` (pypi) — **✅ VALIDATED**

**Validation Source:** `pypi` | **Validation Status:** `VERIFIED`
**Verification Details:** Package 'platformdirs' verified on PyPI (latest version: 4.13.0).

**Rationale:** platformdirs is the actively maintained, direct community successor to appdirs with exact API parity for user_cache_dir.

### 2.3 Step-by-Step Migration Plan
#### Step 1: Replace appdirs import with platformdirs `[unverified]`
Change 'from appdirs import user_cache_dir' to 'from platformdirs import user_cache_dir' in linkwatch/cache.py.
```diff
-from appdirs import user_cache_dir
+from platformdirs import user_cache_dir
```

#### Step 2: Update requirements files `[unverified]`
Replace appdirs==1.4.4 with platformdirs>=3.0.0 in requirements.txt and pyproject.toml.
```diff
-appdirs==1.4.4
+platformdirs>=3.0.0
```

### 2.4 Suggested Tests for Regression Verification
#### `test_cache_dir_platformdirs` `[unverified]`
Ensure cache_dir returns a valid directory path created by platformdirs.
```python
def test_cache_dir_platformdirs():
    from linkwatch.cache import cache_dir
    path = cache_dir()
    assert os.path.exists(path)
    assert 'linkwatch' in path

```

### 2.5 Compatibility Gaps & Breaking Changes
- **macOS Cache Paths** `[unverified]`: platformdirs defaults to ~/Library/Caches/<appname> on macOS matching modern Apple HIG, whereas older appdirs had minor path variations.
  - *Mitigation:* Test and verify cache migration if persisting cache across upgrades.

### 2.6 Open Concerns & Limitations
- 🟡 **Cache Directory Migration** (Severity: `LOW`) `[unverified]`
  Existing user cache directories might need to be discovered if legacy cache persistence is critical.

