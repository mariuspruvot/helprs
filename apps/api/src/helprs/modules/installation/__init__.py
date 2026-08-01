"""Installation module — GitHub App installation management."""

# Deliberately no re-exports. Importing a router here made every
# submodule import pull the whole router graph back through
# core.dependencies, which imports identity.models -- a cycle that left
# `import helprs.core.dependencies` broken on its own and made startup
# depend on main.py happening to import admin.views first. Import
# submodules by their full path instead.
