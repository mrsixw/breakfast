# Pluggable Seasonal Calendars

**Issue:** [#196](https://github.com/mrsixw/breakfast/issues/196)  
**Status:** Implemented

## Problem

The seasonal colour easter egg in breakfast was hard-coded to the western/Gregorian calendar (Christmas, Easter, Pride Month, Halloween). Teams that celebrate different cultural holidays — Hanukkah, Diwali, Eid al-Fitr, Holi, Vaisakhi — got no seasonal love.

## Solution

A pluggable calendar system driven by a `seasonal-calendar` config key. Each calendar is a function `(today: datetime.date) -> str | list[str] | None` registered in a `CALENDARS` dict. The caller picks which calendar to use; `"off"` disables the feature entirely.

## Calendar Interface

```python
CalendarFn = Callable[[datetime.date], str | list[str] | None]
```

- **`None`** — no holiday today, return text unstyled.
- **`str`** — single ANSI escape code, applied uniformly.
- **`list[str]`** — list of colours for PR-number cycling (e.g., December candy-cane, Pride rainbow, Holi rainbow).

## Calendars

| Key | Holidays | Notes |
| --- | --- | --- |
| `"western"` | Christmas 🎄 (candy-cane), Easter 🐣, Pride Month 🌈, Halloween 🎃, Valentine's Day 💕, Lunar New Year 🧧 | Default. January is always purple — Steve's birthday month must never be overridden. |
| `"jewish"` | Hanukkah 🕎 (8 nights, blue), Rosh Hashanah 🍎 (2 days, gold), Passover 🪬 (7 days, spring green) | Uses pre-computed tables for 2024–2045. |
| `"islamic"` | Eid al-Fitr 🌙 (3 days, green) | Uses pre-computed tables for 2024–2045. Dates are approximate (moon-sighting varies by location). |
| `"hindu"` | Diwali 🪔 (5 days, gold), Holi 🌈 (2 days, rainbow) | Uses pre-computed tables for 2024–2045. |
| `"sikh"` | Vaisakhi 🌾 (April 13, spring green), Bandi Chhor Divas 🪔 (5 days, gold) | Vaisakhi is fixed; Bandi Chhor Divas shares Diwali dates. |
| `"off"` | — | Disables all seasonal colours. |

## Implementation

### `src/breakfast/ui.py`

- Pre-computed lookup tables (`_ROSH_HASHANAH`, `_HANUKKAH_START`, `_PASSOVER_START`, `_EID_AL_FITR`, `_DIWALI`, `_HOLI`) covering 2024–2045.
- `_in_holiday_window(today, table, days)` helper.
- `_western_calendar(today)` — refactored from the old `apply_seasonal_colour` logic. Returns `list` for cycling effects (December, June), `str` for fixed colours, `None` otherwise.
- `_jewish_calendar`, `_islamic_calendar`, `_hindu_calendar`, `_sikh_calendar` — same signature.
- `CALENDARS` dict maps string keys to calendar functions.
- `apply_seasonal_colour(text, pr_number, calendar="western")` — looks up the calendar function, dispatches, and handles list cycling via `pr_number % len(result)`.
- `render_pr_summary` parameter renamed from `seasonal_colours: bool` to `calendar: str`.

### `src/breakfast/config.py`

- Added `seasonal-calendar = "western"` commented block to `_DEFAULT_CONFIG_CONTENT`.
- `load_config()`: maps `seasonal-colours = false` → `seasonal-calendar = "off"` for backward compatibility.

### `src/breakfast/cli.py`

- Reads `seasonal-calendar` from config (default `"western"`).
- Overrides to `"off"` when `seasonal-colours = false` for backward compat.
- Passes `calendar=seasonal_calendar` to all `apply_seasonal_colour` calls and `render_pr_summary`.

## Backward Compatibility

`seasonal-colours = false` continues to work — `load_config()` maps it to `seasonal-calendar = "off"` so existing configs need no changes.

## Constraint: January Is Always Purple

January is Steve's birthday month. The western calendar function returns `SEASONAL_PALETTES["purple"]` for January **before** checking for Lunar New Year, which can fall in January. LNY gold is only applied when LNY falls in February.
