import pytest

from breakfast import api, cache


@pytest.fixture(autouse=True)
def isolate_cache(tmp_path, monkeypatch):
    """Redirect the PR cache to a per-test temp dir so tests don't share cache state."""
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path / "breakfast_cache")
    api.reset_api_stats()
    api.get_required_approving_review_count.cache_clear()


@pytest.fixture(autouse=True)
def wrap_monkeypatch(monkeypatch):
    original_setattr = monkeypatch.setattr

    def custom_setattr(target, name, value, *args, **kwargs):
        if target is api.requests and name in ("get", "post"):
            original_value = value
            import inspect

            def wrapped(*w_args, **w_kwargs):
                if not callable(original_value):
                    return original_value
                try:
                    sig = inspect.signature(original_value)
                    has_kwargs = any(
                        p.kind == p.VAR_KEYWORD for p in sig.parameters.values()
                    )
                    has_timeout = "timeout" in sig.parameters
                    if not (has_kwargs or has_timeout):
                        w_kwargs.pop("timeout", None)
                except (ValueError, TypeError):
                    pass
                return original_value(*w_args, **w_kwargs)

            value = wrapped
        return original_setattr(target, name, value, *args, **kwargs)

    monkeypatch.setattr = custom_setattr
