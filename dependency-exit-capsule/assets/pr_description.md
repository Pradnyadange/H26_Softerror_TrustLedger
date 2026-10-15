# Pull Request Description: Fix Jinja2 / MarkupSafe incompatibility (`soft_unicode` removal)

## Suggested Commit Message
```text
fix(deps): upgrade Jinja2 to >=3.1.2 to resolve MarkupSafe incompatibility

Jinja2 2.11.3 depended on `markupsafe.soft_unicode`, which was deprecated
in MarkupSafe 2.0.0 and removed in MarkupSafe 2.1.0+. When LinkWatch is
installed in any modern Python 3.12 environment from requirements.txt,
pip resolves MarkupSafe 3.x, causing an `ImportError` on report generation
and breaking `test_report_renders_all_sites`.

Upgrading Jinja2 to `>=3.1.2` (resolving to 3.1.6 on PyPI) fixes the import
crash by using standard string handling, restores clean compatibility with
MarkupSafe 3.x, and passes the entire test suite without regressions.
```

---

## 1. Problem Description

When setting up `LinkWatch` in a fresh Python 3.12 environment following the instructions in `README.md` (`make test` or `pip install -r requirements.txt -r requirements-dev.txt`), running the test suite fails on `tests/test_report.py::test_report_renders_all_sites`:

```text
tests/test_report.py::test_report_renders_all_sites FAILED               [100%]
...
E   ImportError: cannot import name 'soft_unicode' from 'markupsafe'
```

Additionally, any execution of `python -m linkwatch.cli report` fails with the same unhandled `ImportError`.

---

## 2. Steps to Reproduce

In a clean virtual environment (Python 3.12):
```powershell
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
pytest -v
```
Result: **9 passed, 1 failed** (`tests/test_report.py::test_report_renders_all_sites`).

---

## 3. Root Cause

`requirements.txt` pinned `Jinja2==2.11.3` (released January 2021). Jinja2 2.11.3 depended on `from markupsafe import soft_unicode`. 
`markupsafe` deprecated `soft_unicode` in version 2.0.0 and permanently removed it in version 2.1.0 (released March 2022).
Because `requirements.txt` left `markupsafe` unpinned, `pip` installs the modern release of `markupsafe` (currently `3.0.4`), triggering an immediate `ImportError: cannot import name 'soft_unicode' from 'markupsafe'`.

---

## 4. Change Applied

In `requirements.txt`:
```diff
--- a/requirements.txt
+++ b/requirements.txt
@@ -1,7 +1,7 @@
 toml==0.10.2
 appdirs==1.4.4
 requests==2.31.0
-Jinja2==2.11.3
+Jinja2>=3.1.2
 pydantic==1.10.13
 click>=7
 six
```

Jinja2 3.1.x eliminates all internal calls to `soft_unicode`, natively supports Python 3.12, and is fully compatible with MarkupSafe 2.x and 3.x.

---

## 5. Verification Evidence

All verification steps were performed directly against real virtual environments:

1. **`pip check` Verification:**
   ```text
   No broken requirements found.
   ```
   Confirmed clean resolution without conflicting constraints.

2. **Test Suite Execution (`pytest -v`):**
   ```text
   ======================== 10 passed, 1 warning in 8.88s ========================
   ```
   Ran twice consecutively in a clean virtual environment to confirm 100% pass rate and zero flakiness. All 10 tests pass, including `test_report_renders_all_sites`.

3. **Rendered HTML Parity:**
   Rendered the HTML status page with fixed inputs and compared outputs via byte-level file comparison:
   ```text
   FC: no differences encountered
   ```
   Rendered HTML output is identical to baseline expectations.

---

## 6. Risks and Alternatives Considered

- **Alternative Evaluated (Candidate A):** Constraining MarkupSafe to `<2.1.0` while keeping `Jinja2==2.11.3`. While this restores `soft_unicode`, it locks the repository onto an obsolete, unmaintained version of Jinja2 (2.11.3 from 2021) and forces ancient versions of MarkupSafe lacking pre-built wheels on modern Python releases.
- **Candidate B (Selected):** Upgrading `Jinja2>=3.1.2`. Jinja2 3.x maintains backwards-compatible template syntax and standard API parity for the functions used in LinkWatch (`Environment`, `FileSystemLoader`, `select_autoescape`). Risk is minimal and confined to template rendering.

---

## 7. AI Disclosure

This contribution was analyzed, developed, and verified using the `dependency-exit-capsule` agent skill. The initial compatibility proposal was assisted by the open-weight model `llama3.2:3b` running locally via Ollama (`http://localhost:11434/api/generate`, licensed under the Llama 3.2 Community License Agreement). All findings, test runs, diffs, and package validations were empirically executed and verified directly on the host runtime.
