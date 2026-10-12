# User-Defined Seasonal Calendars

Status: Implemented — [#478](https://github.com/mrsixw/breakfast/issues/478),
part one of [#477](https://github.com/mrsixw/breakfast/issues/477).

## Problem

[Pluggable seasonal calendars](pluggable-calendars.md) gave breakfast seven
built-in calendars, each a Python function keyed by name in `ui.CALENDARS`.
Between them they cover a good spread of public holidays and nothing else. A
birthday, a launch date, a team hack week or Pizza Friday 🍕 cannot be
expressed at all, and neither can "I want Tuesdays in teal".

Adding each such day to `ui.py` does not scale: they are personal, and one
person's launch date is noise in everybody else's terminal.

## Solution

A `[calendar]` table in `config.toml`, selected with
`seasonal-calendar = "custom"`. Each `[[calendar.event]]` pairs a date rule
with a colour. The first matching event wins; unmatched days fall through to
an optional `extends` calendar.

```toml
seasonal-calendar = "custom"

[calendar]
extends = "western"

[[calendar.event]]
name   = "My birthday"
date   = "03-14"
colour = "pink"

[[calendar.event]]
name    = "Pizza Friday"
weekday = "friday"
colour  = "orange"

[[calendar.event]]
name   = "Hack week"
start  = "2026-10-05"
end    = "2026-10-09"
colour = ["red", "orange", "yellow"]
```

### Date rules

An event carries exactly one, so there is never a question of which applies:

| Rule | Shape | Recurs |
| --- | --- | --- |
| `date` | `"MM-DD"` | every year |
| `start` + `end` | `"YYYY-MM-DD"`, inclusive | no, one-off |
| `dates` | list of `"YYYY-MM-DD"` | only on the dates listed |
| `weekday` | `"monday"` … `"sunday"` | every week |
| `month` | `1`–`12` | every year |

`days` widens a `date` or `dates` window (default `1`). `start`/`end` carry
their own span, and `weekday`/`month` are periods rather than points, so
`days` does not apply to them.

`dates` exists for movable feasts. Anything whose date is computed rather
than declared — Easter, Lunar New Year, Diwali — already has a built-in
calendar; `dates` is the escape hatch for the ones that do not, at the cost
of spelling out a year at a time.

### Colours

`parse_calendar_colour` accepts a palette name, `"pride"`/`"holi"`, a
256-colour number, a `#rrggbb` hex value, or a list of any of those. A list
cycles by PR number, the same mechanism December's candy-cane and June's
Pride rows already use.

Hex is worth the extra branch: a user picking their own colours has a brand
or a terminal theme in mind, and snapping it to the nearest of eleven palette
entries would be a poor joke to play on someone who asked for `#ff69b4`.

### Resolution order

```text
seasonal-colours = false / --no-colour / NO_COLOR   → nothing
first matching event                                → its colour
no match, January                                   → birthday purple (if extends)
no match                                            → extends calendar, or nothing
```

A matching event beats the January purple override. Purple is a default
speaking for a user who never expressed a preference; an event is that
expression, on that exact date. `rainbow` won its own exemption for the same
reason in [#377](https://github.com/mrsixw/breakfast/issues/377).

On fall-through the purple stands, because `extends` is a delegation to a
built-in calendar and those observe January.

### Validation

A malformed event warns on stderr, naming the event, and is skipped. The rest
of the calendar still loads.

Aborting the run would be the wrong trade. breakfast is the first thing its
user looks at in the morning, and a typo in a decoration is no reason to
withhold their pull requests. This matches how unknown config keys already
behave.

`seasonal-calendar = "custom"` with no `[calendar]` table warns and leaves
the day unthemed. Falling back to `western` would be worse: the output would
look themed, so the user would assume their events had loaded and silently
failed to match.

### Reserved keys

`gift` and `message` are accepted and ignored. They belong to
[#479](https://github.com/mrsixw/breakfast/issues/479) and
[#481](https://github.com/mrsixw/breakfast/issues/481), and accepting them
early means a config written against the finished feature does not spray
warnings on this release.

## Implementation notes

- `ui.py` holds `CalendarEvent` (a frozen dataclass that knows how to match a
  date), `CustomCalendar` (an ordered list of events plus an `extends`
  fallback) and `parse_calendar_colour`. `CustomCalendar` is callable, so it
  is interchangeable with the seven built-in calendar functions.
- `config.py` holds the parsing and validation, and hands back a
  `CustomCalendar`. Keeping validation out of `ui.py` leaves that module
  about colour and leaves config errors where every other config error lives.
- `apply_seasonal_colour` now takes either a calendar name or a
  `CustomCalendar`. The January rule moved into `_resolve_calendar_colour`,
  where the three exemptions can be read side by side.

### Two dates that bite

- **29 February.** A leap-day event degrades to the 28th in common years.
  Serving a birthday three years in four is the kind of bug that looks like
  indifference, and it would surface once every four years — the worst
  possible review cycle.
- **Windows that cross new year.** `date = "12-30"` with `days = 4` runs into
  January, so matching checks both this year's anchor and last year's.

### `--update-config` had to change

It appended missing options to the end of the file. TOML binds every key
after a table header to that table, so an appended `workers = 64` landed
inside `[calendar]` — parsed, accepted, and silently ignored. Options are now
spliced in above the first table header.

## Alternatives considered

**A separate `calendar.toml`.** Rejected: two files to find, two to back up,
and `--update-config` would have to learn about both. The config file is
already the place where breakfast's behaviour is declared.

**Cron expressions instead of date rules.** Rejected: `0 0 14 3 *` is a
worse way to say "my birthday", and the five rules cover what a wall calendar
can express.

**Validating strictly and exiting.** Rejected — see above.
