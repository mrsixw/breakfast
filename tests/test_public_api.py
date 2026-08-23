"""Guard the public/private boundary between modules.

A leading underscore means "internal to this module". Nothing enforces that:
ruff's PLC2701 deliberately ignores intra-package relative imports, and SLF001
only catches attribute access, not imports. So the rule is checked here.

Tests reaching into the internals of the module they test are fine and are not
covered by this file — the boundary that matters is the one between modules.
"""

import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parent.parent / "src" / "breakfast"


def _modules():
    return sorted(p for p in PACKAGE.glob("*.py") if p.name != "__init__.py")


def _parsed(path: Path) -> ast.Module:
    return ast.parse(path.read_text(), filename=str(path))


@pytest.mark.parametrize("path", _modules(), ids=lambda p: p.name)
def test_no_private_names_imported_across_modules(path: Path):
    """A module must not import a `_name` from a sibling module.

    If a name is needed elsewhere in the package it is not private, and the
    underscore misleads whoever reads it next. Either drop the underscore or
    stop importing it.
    """
    offenders = []
    for node in ast.walk(_parsed(path)):
        if not isinstance(node, ast.ImportFrom):
            continue
        # A sibling is either a relative import (level > 0) or an absolute one
        # spelled `from breakfast.x import ...`. Catching only the first would
        # leave the absolute spelling as a way around this check.
        sibling = node.level > 0 or (node.module or "").startswith(f"{PACKAGE.name}.")
        if not sibling:
            continue
        offenders += [
            f"{path.name}:{node.lineno} imports {alias.name} from "
            f"{'.' * node.level}{node.module or ''}"
            for alias in node.names
            if alias.name.startswith("_")
        ]
    assert not offenders, "private names crossing a module boundary:\n  " + "\n  ".join(
        offenders
    )


@pytest.mark.parametrize("path", _modules(), ids=lambda p: p.name)
def test_no_private_attribute_access_across_modules(path: Path):
    """A module must not reach a sibling's `_name` via attribute access.

    Catches the `othermodule._thing` form that the import check cannot see.
    Only names bound by a relative import are treated as sibling modules, so
    `self._x`, `path._x` and third-party access are left alone.
    """
    tree = _parsed(path)
    siblings = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and (node.level > 0 or (node.module or "").startswith(f"{PACKAGE.name}."))
        for alias in node.names
    }
    offenders = [
        f"{path.name}:{node.lineno} reads {node.value.id}.{node.attr}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id in siblings
        and node.attr.startswith("_")
    ]
    assert not offenders, "private attribute access across modules:\n  " + "\n  ".join(
        offenders
    )


@pytest.mark.parametrize("path", _modules(), ids=lambda p: p.name)
def test_every_module_declares_all(path: Path):
    """Each module states its public surface, rather than implying it.

    `__all__` is the only machine-readable contract available here; without it
    "public" means nothing more than "somebody forgot an underscore".
    """
    tree = _parsed(path)
    declared = [
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets)
    ]
    assert declared, f"{path.name} has no __all__"


@pytest.mark.parametrize("path", _modules(), ids=lambda p: p.name)
def test_all_entries_exist_and_are_public(path: Path):
    """`__all__` must not name anything private or absent.

    A stale entry would make `from module import *` raise at import time, so
    this fails fast in CI instead.
    """
    module = __import__(f"breakfast.{path.stem}", fromlist=["__all__"])
    exported = getattr(module, "__all__", [])

    # Ordering is RUF022's job, not this test's — the two use different
    # conventions (RUF022 groups SCREAMING_CASE before CamelCase before
    # snake_case) and asserting plain sorted() here just fights the linter.
    assert len(exported) == len(set(exported)), f"{path.name}: __all__ has duplicates"

    for name in exported:
        assert not name.startswith("_"), f"{path.name}: __all__ exports private {name}"
        assert hasattr(module, name), f"{path.name}: __all__ names missing {name}"
