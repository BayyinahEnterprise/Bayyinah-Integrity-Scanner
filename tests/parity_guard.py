"""Which tests compare against the frozen reference implementations.

A test that calls ``bayyinah_v0`` or ``bayyinah_v0_1`` (directly, or
through a helper defined in the same module) compares the current
scanner with a version that lacked the v2.1 passes. Such a test must
carry ``@pytest.mark.legacy_parity`` so it runs with
``BAYYINAH_LEGACY_PARITY=1``. This module finds those tests by reading
the syntax tree, so the rule is "every test that touches the reference
is marked", not "every test whose name looks like a parity test".
"""

from __future__ import annotations

import ast
from pathlib import Path

REFERENCE_MODULES = {"bayyinah_v0", "bayyinah_v0_1"}
MARK = "legacy_parity"
TESTS_DIR = Path(__file__).parent


def _reference_aliases(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[-1] in REFERENCE_MODULES or a.name in REFERENCE_MODULES:
                    names.add((a.asname or a.name).split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            mod = (node.module or "")
            if mod.split(".")[-1] in REFERENCE_MODULES:
                names.update(a.asname or a.name for a in node.names)
            else:
                names.update(a.asname or a.name for a in node.names
                             if a.name in REFERENCE_MODULES)
    return names


def _uses(node: ast.AST, names: set[str]) -> bool:
    return any(isinstance(n, ast.Name) and n.id in names for n in ast.walk(node))


def _has_mark(decorators: list[ast.expr]) -> bool:
    return any(MARK in ast.unparse(d) for d in decorators)


def tests_touching_reference(path: Path) -> list[tuple[str, int, bool]]:
    """(qualified test name, line, is_marked) for each test in ``path``
    that reaches a reference module."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    tainted = _reference_aliases(tree)
    if not tainted:
        return []
    module_marked = any(
        isinstance(n, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "pytestmark" for t in n.targets)
        and MARK in ast.unparse(n.value) for n in tree.body)
    # Helpers and fixtures that reach the reference taint their own names.
    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                    and not node.name.startswith("test") \
                    and node.name not in tainted and _uses(node, tainted):
                tainted.add(node.name)
                changed = True
        # Module-level names only: a local variable named ``report`` in
        # one test says nothing about a ``report`` in another.
        for node in tree.body:
            if isinstance(node, ast.Assign) and _uses(node.value, tainted):
                for t in node.targets:
                    if isinstance(t, ast.Name) and t.id not in tainted:
                        tainted.add(t.id)
                        changed = True
    out: list[tuple[str, int, bool]] = []

    def visit(body: list[ast.stmt], prefix: str, inherited: bool) -> None:
        for node in body:
            if isinstance(node, ast.ClassDef):
                visit(node.body, f"{prefix}{node.name}::",
                      inherited or _has_mark(node.decorator_list))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                    and node.name.startswith("test"):
                args = {a.arg for a in node.args.args}
                if _uses(node, tainted) or args & tainted:
                    out.append((f"{prefix}{node.name}", node.lineno,
                                inherited or _has_mark(node.decorator_list)))

    visit(tree.body, "", module_marked)
    return out


def all_reference_tests() -> list[tuple[Path, str, int, bool]]:
    found = []
    for path in sorted(TESTS_DIR.rglob("test_*.py")):
        for name, line, marked in tests_touching_reference(path):
            found.append((path, name, line, marked))
    return found
