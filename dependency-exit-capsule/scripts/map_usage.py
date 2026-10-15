#!/usr/bin/env python3
"""
map_usage.py - AST-based usage mapper for Python dependencies.

Inspects all Python files in a target directory using the Python standard
library `ast` module. Discovers every import, alias, and function/method call
originating from a specified dependency with exact file and line coordinates.

Marks dynamic imports (e.g. importlib, __import__) as "uncertain".
Outputs strict empirical JSON to stdout.
"""

import argparse
import ast
import json
import os
import sys
from pathlib import Path

# Directories to ignore during recursive search
IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".tox",
    "build",
    "dist",
    "node_modules",
}


def normalize_name(name: str) -> str:
    """Normalize package/module name for comparison."""
    return name.replace("-", "_").lower()


class UsageVisitor(ast.NodeVisitor):
    def __init__(self, target_modules: list[str], rel_path: str):
        super().__init__()
        self.targets = [normalize_name(t) for t in target_modules]
        self.rel_path = rel_path
        self.imports = []
        self.calls = []
        self.dynamic_imports_detected = False

        # Maps locally bound name -> canonical symbol
        self.bound_names: dict[str, str] = {}

    def _matches_any_target(self, name: str) -> str | None:
        norm = normalize_name(name)
        for t in self.targets:
            if norm == t or norm.startswith(f"{t}."):
                return t
        return None

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            matched_target = self._matches_any_target(alias.name)
            if matched_target:
                local_name = alias.asname or alias.name
                self.bound_names[local_name] = alias.name
                self.imports.append({
                    "file": self.rel_path,
                    "line": node.lineno,
                    "target_dependency": matched_target,
                    "imported_symbol": alias.name,
                    "alias": alias.asname,
                    "is_dynamic": False,
                    "status": "verified"
                })
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module:
            matched_target = self._matches_any_target(node.module)
            if matched_target:
                for alias in node.names:
                    local_name = alias.asname or alias.name
                    full_symbol = f"{node.module}.{alias.name}"
                    self.bound_names[local_name] = full_symbol
                    self.imports.append({
                        "file": self.rel_path,
                        "line": node.lineno,
                        "target_dependency": matched_target,
                        "imported_symbol": full_symbol,
                        "alias": alias.asname,
                        "is_dynamic": False,
                        "status": "verified"
                    })
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        # 1. Check for dynamic imports: __import__(...) or importlib.import_module(...)
        if self._is_dynamic_import(node):
            self._handle_dynamic_import(node)

        # 2. Check for regular calls on tracked symbols
        resolved_symbol = self._resolve_callee(node.func)
        if resolved_symbol:
            call_code = ""
            try:
                call_code = ast.unparse(node)
            except Exception:
                call_code = f"<call at line {node.lineno}>"

            matched_target = self._matches_any_target(resolved_symbol)
            self.calls.append({
                "file": self.rel_path,
                "line": node.lineno,
                "target_dependency": matched_target,
                "call_expression": call_code,
                "resolved_symbol": resolved_symbol,
                "status": "verified"
            })

        self.generic_visit(node)

    def _is_dynamic_import(self, node: ast.Call) -> bool:
        """Detect __import__ or importlib.import_module calls."""
        if isinstance(node.func, ast.Name) and node.func.id == "__import__":
            return True
        if isinstance(node.func, ast.Attribute):
            if node.func.attr == "import_module":
                if isinstance(node.func.value, ast.Name) and node.func.value.id == "importlib":
                    return True
        return False

    def _handle_dynamic_import(self, node: ast.Call):
        """Analyze arguments to dynamic import call."""
        if not node.args:
            return

        arg0 = node.args[0]
        # Static string literal in dynamic import
        if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
            matched = self._matches_any_target(arg0.value)
            if matched:
                self.dynamic_imports_detected = True
                self.imports.append({
                    "file": self.rel_path,
                    "line": node.lineno,
                    "target_dependency": matched,
                    "imported_symbol": arg0.value,
                    "alias": None,
                    "is_dynamic": True,
                    "status": "uncertain"
                })
        else:
            # Dynamic expression (variable, function call, concat) - uncertain!
            self.dynamic_imports_detected = True
            self.imports.append({
                "file": self.rel_path,
                "line": node.lineno,
                "target_dependency": self.targets[0] if self.targets else "unknown",
                "imported_symbol": "<dynamic expression>",
                "alias": None,
                "is_dynamic": True,
                "status": "uncertain"
            })

    def _resolve_callee(self, func_node: ast.AST) -> str | None:
        """Resolve a Call func AST node against tracked bound names."""
        if isinstance(func_node, ast.Name):
            if func_node.id in self.bound_names:
                return self.bound_names[func_node.id]

        elif isinstance(func_node, ast.Attribute):
            chain = []
            curr = func_node
            while isinstance(curr, ast.Attribute):
                chain.append(curr.attr)
                curr = curr.value
            if isinstance(curr, ast.Name):
                chain.append(curr.id)
                chain.reverse()
                root = chain[0]
                if root in self.bound_names:
                    canonical_root = self.bound_names[root]
                    remainder = chain[1:]
                    return ".".join([canonical_root] + remainder)
        return None


def map_dependency_usage(target_dir: Path, target_modules: str | list[str]) -> dict:
    """Analyze all python files in target_dir for usage of target_modules."""
    if isinstance(target_modules, str):
        # Support comma-separated modules e.g. "Jinja2,markupsafe"
        modules_list = [m.strip() for m in target_modules.split(",") if m.strip()]
    else:
        modules_list = list(target_modules)

    all_imports = []
    all_calls = []
    any_dynamic = False

    for root_dir, dirs, files in os.walk(target_dir):
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.startswith(".")]

        for fname in files:
            if not fname.endswith(".py"):
                continue

            full_path = Path(root_dir) / fname
            try:
                rel_path = full_path.relative_to(target_dir).as_posix()
            except ValueError:
                rel_path = full_path.as_posix()

            try:
                source_code = full_path.read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(source_code, filename=str(full_path))
            except SyntaxError as e:
                sys.stderr.write(f"[WARN] Syntax error in {rel_path}: {e}\n")
                continue
            except Exception as e:
                sys.stderr.write(f"[WARN] Could not parse {rel_path}: {e}\n")
                continue

            visitor = UsageVisitor(target_modules=modules_list, rel_path=rel_path)
            visitor.visit(tree)

            all_imports.extend(visitor.imports)
            all_calls.extend(visitor.calls)
            if visitor.dynamic_imports_detected:
                any_dynamic = True

    total_occurrences = len(all_imports) + len(all_calls)
    status = "uncertain" if any_dynamic else "verified"

    return {
        "status": status,
        "total_occurrences": total_occurrences,
        "dynamic_imports_detected": any_dynamic,
        "imports": all_imports,
        "calls": all_calls
    }


def main():
    parser = argparse.ArgumentParser(
        description="AST-based usage mapper to find all imports, aliases, and calls of a dependency."
    )
    parser.add_argument(
        "--repo-path",
        default=".",
        help="Path to repository root (default: current directory)"
    )
    parser.add_argument(
        "--dep",
        "--dependency",
        required=True,
        help="Name of dependency module to map (e.g. toml, appdirs)"
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

    usage_data = map_dependency_usage(repo_dir, args.dep)

    result = {
        "target_dependency": args.dep,
        "target_repo": str(repo_dir),
        "usage": usage_data
    }

    formatted = json.dumps(result, indent=2)
    if args.output:
        out_path = Path(args.output).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(formatted)
            f.write("\n")
        sys.stderr.write(f"Wrote usage mapping to {out_path}\n")
    else:
        print(formatted)


if __name__ == "__main__":
    main()
