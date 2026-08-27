"""Step definitions for the end-to-end suite.

Split out of ``conftest.py``, which is for fixtures. ``process`` holds the steps
that talk about a subprocess and its streams; ``fixture_repo`` holds the ones
that know about the frozen fixture repository.

These modules are imported into ``tests/e2e/conftest.py`` — see the note there
on why that import is load-bearing.
"""
