"""Tests for constants in breakfast.constants."""

import breakfast.constants as constants


def test_api_constants():
    assert constants.GITHUB_API_URL == "https://api.github.com"
    assert constants.GITHUB_GRAPHQL_URL == "https://api.github.com/graphql"
    assert constants._MAX_RETRIES == 3
    assert constants._RETRY_STATUSES == {502, 503, 504}


def test_cache_constants():
    assert constants.DEFAULT_CACHE_TTL == 300
    assert constants.CACHE_DIR_ENV_VAR == "BREAKFAST_CACHE_DIR"
    assert constants.CACHE_DISABLED_ENV_VAR == "BREAKFAST_NO_CACHE"
    assert constants._SUFFIX_MAP == {"s": 1, "m": 60, "h": 3600}


def test_ui_constants():
    assert len(constants.BREAKFAST_ITEMS) > 0
    assert "purple" in constants.SEASONAL_PALETTES
    assert len(constants.PRIDE_RAINBOW) == 6
    assert len(constants.HOLI_RAINBOW) == 6


def test_holiday_tables():
    assert 2026 in constants._DIWALI
    assert 2026 in constants._EID_AL_ADHA
    assert 2026 in constants._EID_AL_FITR
    assert 2026 in constants._HANUKKAH_START
    assert 2026 in constants._HOLI
    assert 2026 in constants._MID_AUTUMN
    assert 2026 in constants._PASSOVER_START
    assert 2026 in constants._ROSH_HASHANAH
    assert 2026 in constants._SUKKOT_START


def test_pizza_recipes():
    assert len(constants.PIZZA_RECIPES) >= 4
    for recipe in constants.PIZZA_RECIPES:
        assert "title" in recipe
        assert "style" in recipe
        assert "dough" in recipe
        assert "toppings" in recipe
        assert "bake" in recipe
        assert "tip" in recipe
