# Issue: Deprecation of `pkg_resources` API in `linkwatch/resources.py`

**Status:** Unverified AI Suggestion (Draft Follow-Up Issue)  
**Target Repository:** `rishrek/LinkWatch`  
**File:** [`linkwatch/resources.py`](file:///d:/mlh/work/LinkWatch-fix/linkwatch/resources.py#L1-L8)  
**Observed Warning:**
```text
linkwatch\resources.py:1: DeprecationWarning: pkg_resources is deprecated as an API. See https://setuptools.pypa.io/en/latest/pkg_resources.html
  import pkg_resources
```

---

## 1. Description of the Problem

In `linkwatch/resources.py`, template directory resolution currently utilizes `pkg_resources.resource_filename`:

```python
import pkg_resources

TEMPLATE_NAME = "status.html.j2"


def template_dir():
    return pkg_resources.resource_filename("linkwatch", "templates")
```

`pkg_resources` was formally deprecated by the `setuptools` maintainers (PEP 451, PEP 616, and Python packaging standards). In modern Python versions (Python 3.12+), importing `pkg_resources` triggers a runtime `DeprecationWarning`. Furthermore, `pkg_resources` adds unnecessary startup overhead and maintains an external runtime dependency on `setuptools`.

---

## 2. Reproduction Steps

In any Python 3.12 virtual environment:
```powershell
python -W error::DeprecationWarning -c "import linkwatch.resources"
```
Or run `pytest`:
```text
linkwatch\resources.py:1
  DeprecationWarning: pkg_resources is deprecated as an API. See https://setuptools.pypa.io/en/latest/pkg_resources.html
```

---

## 3. Suggested Migration Direction [AI-GENERATED - UNVERIFIED]

> [!NOTE]
> Per the project contribution boundary rules, this suggestion has not been implemented or verified in the current pull request and is tracked here as an isolated future task.

Replace `pkg_resources` with the standard library `importlib.resources` (available natively in Python 3.9+ without third-party dependencies):

```python
from importlib import resources

TEMPLATE_NAME = "status.html.j2"


def template_dir():
    # importlib.resources.files returns a Traversable object compatible with str() or Path
    return str(resources.files("linkwatch") / "templates")
```

### Benefits of Migration
1. **Zero External Dependency:** Removes runtime dependency on `setuptools` for resource resolution.
2. **Standard Library Compliance:** Uses PEP 586 / Python 3.9+ standard library `importlib.resources`.
3. **Clean Test Runs:** Eliminates the `DeprecationWarning` across all test executions.
