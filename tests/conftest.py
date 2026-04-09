import pytest

from breakfast import api, cache


@pytest.fixture(autouse=True)
def isolate_cache(tmp_path, monkeypatch):
    """Redirect the PR cache to a per-test temp dir so tests don't share cache state."""
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path / "breakfast_cache")
    api.get_required_approving_review_count.cache_clear()
