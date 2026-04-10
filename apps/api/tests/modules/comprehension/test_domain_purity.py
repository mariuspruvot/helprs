"""AST-level guard that the comprehension domain layer stays dependency-free.

Story 3.1 AC #1/#4/#6 lock the rule "domain imports only stdlib + Pydantic"
at the type level. Walking the AST (rather than snapshotting ``sys.modules``)
is deterministic: it doesn't matter whether other tests loaded SQLAlchemy
earlier in the session.
"""

import ast
import pathlib

_FORBIDDEN = {"sqlalchemy", "fastapi", "httpx", "pydantic_ai"}

# apps/api/tests/modules/comprehension/test_domain_purity.py
# → apps/api/src/helprs/modules/comprehension/domain/
_DOMAIN_DIR = pathlib.Path(__file__).resolve().parents[3] / "src" / "helprs" / "modules" / "comprehension" / "domain"


def test_domain_dir_exists() -> None:
    """Sanity check — if this fails the path math above is wrong."""
    assert _DOMAIN_DIR.is_dir(), f"domain dir not found at {_DOMAIN_DIR}"


def test_domain_files_do_not_import_frameworks() -> None:
    """No top-level ``import`` or ``from`` statement in any domain file may
    reference the banned roots. Relative imports within the domain package
    are allowed.
    """
    py_files = sorted(_DOMAIN_DIR.rglob("*.py"))
    assert py_files, "expected at least one .py file under domain/"

    violations: list[str] = []
    for py in py_files:
        tree = ast.parse(py.read_text(), filename=str(py))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".", 1)[0]
                    if root in _FORBIDDEN:
                        violations.append(f"{py.name}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".", 1)[0]
                if root in _FORBIDDEN:
                    violations.append(f"{py.name}: from {node.module} import ...")

    assert not violations, "Domain layer leaked framework imports:\n  " + "\n  ".join(violations)
