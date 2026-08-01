"""Guards against the module import graph regrowing a cycle.

Each module package used to re-export its router, and ``core.dependencies``
imports ``identity.models``. Importing any submodule therefore dragged the
whole router graph back through ``core.dependencies``, so
``import helprs.core.dependencies`` failed on its own with

    ImportError: cannot import name 'CurrentUser' from partially initialized
    module 'helprs.core.dependencies'

The application booted only because ``main.py`` happened to import
``admin.views`` -- which imports a *model* -- before any router. Re-sorting
those imports would have broken startup, and the cycle was the reason two
services carried function-level imports as workarounds.

Each module is imported in a fresh interpreter: once anything pulls in
``helprs.main``, the modules are already in ``sys.modules`` and a cycle is
invisible.
"""

import subprocess
import sys
from pathlib import Path

import pytest

import helprs.modules

STANDALONE_IMPORTS = [
    "helprs.core.dependencies",
    "helprs.modules.container.models",
    "helprs.modules.container.service",
    "helprs.modules.identity.service",
    "helprs.modules.installation.service",
    "helprs.modules.webhook.tasks",
    "helprs.admin.views",
]


@pytest.mark.parametrize("module", STANDALONE_IMPORTS)
def test_module_imports_without_a_cycle(module: str) -> None:
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"importing {module} on its own failed:\n{result.stderr}"


def test_module_packages_import_nothing() -> None:
    """The re-exports are what created the cycle, so the inits stay bare.

    Asserted against the source rather than the imported module: once any
    submodule has been imported it shows up as an attribute of its package,
    which is ordinary Python and not a re-export.
    """
    modules_dir = Path(helprs.modules.__file__).parent
    for package in ("container", "identity", "installation", "webhook"):
        source = (modules_dir / package / "__init__.py").read_text()
        offenders = [
            line
            for line in source.splitlines()
            if line.startswith(("import ", "from ")) and not line.lstrip().startswith("#")
        ]
        assert offenders == [], f"helprs.modules.{package}.__init__ imports {offenders}"
