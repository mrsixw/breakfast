"""Bind every scenario under ``features/``.

``scenarios()`` walks directories recursively, so one module covers all three
feature files. The ``@e2e`` and ``@live`` tags that decide what runs where are
declared in the feature files themselves — see ``docs/design/testing.md``.
"""

from pytest_bdd import scenarios

scenarios("features")
