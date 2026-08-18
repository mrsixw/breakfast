"""Project-wide constant definitions and data payloads."""

# ── GitHub API Configuration ───────────────────────────────────────────────

GITHUB_API_URL = "https://api.github.com"
GITHUB_GRAPHQL_URL = "https://api.github.com/graphql"

_MAX_GRAPHQL_ERROR_TYPES = 3
_MAX_GRAPHQL_ERROR_MESSAGE_LENGTH = 120
_MAX_STORED_GRAPHQL_ERRORS = 10
_MAX_RETRIES = 3
_RETRY_STATUSES = {502, 503, 504}
_REQUEST_TIMEOUT = (5, 30)
_GRAPHQL_REPOSITORY_PAGE_SIZE = 25

# ── Cache Configuration ────────────────────────────────────────────────────

DEFAULT_CACHE_TTL = 300
CACHE_DIR_ENV_VAR = "BREAKFAST_CACHE_DIR"
CACHE_DISABLED_ENV_VAR = "BREAKFAST_NO_CACHE"
_SUFFIX_MAP = {"s": 1, "m": 60, "h": 3600}

# ── Legendary PRs & Table Rendering ────────────────────────────────────────

_LEGENDARY_COMMENT_THRESHOLD = 100
_LEGENDARY_AGE_THRESHOLD_DAYS = 30
_LEGENDARY_EMOJI = "⚔️"

_COLUMN_DISPLAY_NAMES: dict[str, str] = {
    "org": "Org",
    "repo": "Repo",
    "title": "PR Title",
    "author": "Author",
    "state": "State",
    "files": "Files",
    "commits": "Commits",
    "diff": "+/-",
    "comments": "Comments",
    "age": "Age",
    "checks": "Checks",
    "approvals": "Approved",
    "head-branch": "Head Branch",
    "base-branch": "Base Branch",
    "reviewers": "Reviewers",
    "labels": "Labels",
    "mergeable": "Mergeable?",
    "link": "Link",
}

_DROPPABLE_COLUMNS = [
    "State",
    "Commits",
    "Files",
    "+/-",
    "Cmt",
    "Age",
    "Checks",
    "Apr",
    "Reviewers",
    "Labels",
    "Head Branch",
    "Base Branch",
    "Mrg",
]

# ── UI & Theming ───────────────────────────────────────────────────────────

SEASONAL_PALETTES = {
    "purple": "\033[38;5;141m",  # January (Steve's birthday month 🎂)
    "yellow": "\033[38;5;226m",  # Easter
    "orange": "\033[38;5;208m",  # Halloween 🎃
    "red_white": "\033[38;5;203m",  # Christmas 🎄 (candy-cane red)
    "green": "\033[32m",
    "red": "\033[31m",
    "pink": "\033[38;5;218m",
    "lny": "\033[38;5;196m",
    "blue": "\033[38;5;75m",
    "spring_green": "\033[38;5;120m",
    "gold": "\033[38;5;220m",
}

# Pride Month 🏳️‍🌈 rainbow: one colour per row, cycling by PR number.
PRIDE_RAINBOW = [
    "\033[31m",  # red
    "\033[38;5;208m",  # orange
    "\033[38;5;226m",  # yellow
    "\033[32m",  # green
    "\033[38;5;63m",  # blue
    "\033[38;5;141m",  # purple
]

# Holi rainbow: a burst of festival colours for the Festival of Colours 🎨
HOLI_RAINBOW = [
    "\033[38;5;218m",  # pink
    "\033[38;5;226m",  # yellow
    "\033[32m",  # green
    "\033[38;5;208m",  # orange
    "\033[38;5;141m",  # purple
    "\033[38;5;75m",  # blue
]

BREAKFAST_ITEMS = [
    "☕️",
    "🥐",
    "🥞",
    "🍳",
    "🥓",
    "🥯",
    "🍩",
    "🍪",
    "🥛",
    "🍵",
    "🍎",
    "🍌",
    "🍉",
    "🍇",
    "🍓",
    "🍒",
    "🍑",
    "🍍",
    "🥖",
    "🥨",
    "🥯",
    "🥞",
    "🧇",
    "🧀",
    "🍗",
    "🥩",
    "🥓",
    "🍔",
    "🍟",
    "🍕",
    "🌭",
    "🥪",
    "🌮",
    "🌯",
    "🥙",
]

# ── Holiday Date Tables (2024–2045) ────────────────────────────────────────

_DIWALI: dict[int, tuple[int, int]] = {
    2024: (11, 1),
    2025: (10, 20),
    2026: (11, 8),
    2027: (10, 29),
    2028: (10, 17),
    2029: (11, 5),
    2030: (10, 26),
    2031: (11, 14),
    2032: (11, 2),
    2033: (10, 22),
    2034: (11, 11),
    2035: (11, 1),
    2036: (10, 19),
    2037: (11, 7),
    2038: (10, 28),
    2039: (10, 18),
    2040: (11, 4),
    2041: (10, 24),
    2042: (11, 13),
    2043: (11, 3),
    2044: (10, 21),
    2045: (11, 9),
}

_EID_AL_ADHA: dict[int, tuple[int, int]] = {
    2024: (6, 16),
    2025: (6, 6),
    2026: (5, 26),
    2027: (5, 16),
    2028: (5, 4),
    2029: (4, 24),
    2030: (4, 13),
    2031: (4, 2),
    2032: (3, 22),
    2033: (3, 11),
    2034: (3, 1),
    2035: (2, 18),
    2036: (2, 7),
    2037: (1, 26),
    2038: (1, 16),
    2039: (12, 26),
    2040: (12, 14),
    2041: (12, 4),
    2042: (11, 23),
    2043: (11, 13),
    2044: (11, 1),
    2045: (10, 22),
}

_EID_AL_FITR: dict[int, tuple[int, int]] = {
    2024: (4, 10),
    2025: (3, 30),
    2026: (3, 20),
    2027: (3, 9),
    2028: (2, 26),
    2029: (2, 15),
    2030: (2, 4),
    2031: (1, 24),
    2032: (1, 13),
    2033: (1, 2),
    2034: (12, 11),
    2035: (11, 30),
    2036: (11, 19),
    2037: (11, 8),
    2038: (10, 28),
    2039: (10, 17),
    2040: (10, 6),
    2041: (9, 25),
    2042: (9, 14),
    2043: (9, 4),
    2044: (8, 23),
    2045: (8, 12),
}

_HANUKKAH_START: dict[int, tuple[int, int]] = {
    2024: (12, 25),
    2025: (12, 14),
    2026: (12, 4),
    2027: (12, 24),
    2028: (12, 12),
    2029: (12, 1),
    2030: (12, 20),
    2031: (12, 9),
    2032: (11, 27),
    2033: (12, 16),
    2034: (12, 5),
    2035: (12, 25),
    2036: (12, 13),
    2037: (12, 2),
    2038: (12, 22),
    2039: (12, 11),
    2040: (11, 29),
    2041: (12, 18),
    2042: (12, 8),
    2043: (12, 27),
    2044: (12, 15),
    2045: (12, 5),
}

_HOLI: dict[int, tuple[int, int]] = {
    2024: (3, 25),
    2025: (3, 14),
    2026: (3, 3),
    2027: (3, 22),
    2028: (3, 11),
    2029: (3, 1),
    2030: (3, 20),
    2031: (3, 10),
    2032: (2, 27),
    2033: (3, 17),
    2034: (3, 7),
    2035: (3, 26),
    2036: (3, 14),
    2037: (3, 4),
    2038: (3, 23),
    2039: (3, 13),
    2040: (3, 1),
    2041: (3, 19),
    2042: (3, 8),
    2043: (3, 28),
    2044: (3, 16),
    2045: (3, 5),
}

_MID_AUTUMN: dict[int, tuple[int, int]] = {
    2024: (9, 17),
    2025: (10, 6),
    2026: (9, 25),
    2027: (9, 15),
    2028: (10, 3),
    2029: (9, 22),
    2030: (9, 12),
    2031: (10, 1),
    2032: (9, 19),
    2033: (9, 8),
    2034: (9, 27),
    2035: (9, 16),
    2036: (10, 4),
    2037: (9, 24),
    2038: (9, 13),
    2039: (10, 2),
    2040: (9, 20),
    2041: (9, 9),
    2042: (9, 28),
    2043: (9, 17),
    2044: (10, 5),
    2045: (9, 24),
}

_PASSOVER_START: dict[int, tuple[int, int]] = {
    2024: (4, 22),
    2025: (4, 12),
    2026: (4, 1),
    2027: (4, 21),
    2028: (4, 10),
    2029: (3, 29),
    2030: (4, 17),
    2031: (4, 7),
    2032: (3, 27),
    2033: (4, 14),
    2034: (4, 3),
    2035: (4, 23),
    2036: (4, 11),
    2037: (4, 1),
    2038: (4, 20),
    2039: (4, 9),
    2040: (3, 29),
    2041: (4, 16),
    2042: (4, 6),
    2043: (4, 25),
    2044: (4, 13),
    2045: (4, 3),
}

_ROSH_HASHANAH: dict[int, tuple[int, int]] = {
    2024: (10, 2),
    2025: (9, 22),
    2026: (9, 11),
    2027: (10, 1),
    2028: (9, 20),
    2029: (9, 9),
    2030: (9, 27),
    2031: (9, 18),
    2032: (9, 5),
    2033: (9, 24),
    2034: (9, 14),
    2035: (10, 3),
    2036: (9, 21),
    2037: (9, 10),
    2038: (9, 29),
    2039: (9, 19),
    2040: (9, 7),
    2041: (9, 25),
    2042: (9, 15),
    2043: (10, 4),
    2044: (9, 22),
    2045: (9, 12),
}

_SUKKOT_START: dict[int, tuple[int, int]] = {
    2024: (10, 16),
    2025: (10, 6),
    2026: (9, 25),
    2027: (10, 15),
    2028: (10, 4),
    2029: (9, 23),
    2030: (10, 12),
    2031: (10, 1),
    2032: (9, 19),
    2033: (10, 8),
    2034: (9, 28),
    2035: (10, 17),
    2036: (10, 4),
    2037: (9, 24),
    2038: (10, 13),
    2039: (10, 3),
    2040: (9, 21),
    2041: (10, 10),
    2042: (9, 30),
    2043: (10, 18),
    2044: (10, 5),
    2045: (9, 25),
}

# ── Pizza Easter Egg Recipes ───────────────────────────────────────────────

PIZZA_RECIPES = [
    {
        "title": "Kenji's Foolproof Cast Iron Pan Pizza",
        "style": "Pan Pizza (Crispy & Fried Bottom Crust)",
        "dough": (
            "400g bread flour, 275g water (68%), 8g salt, 4g instant yeast, "
            "8g olive oil. Mix, ferment 12-24h, stretch in well-oiled 10-inch "
            "cast iron skillet, proof 2h."
        ),
        "toppings": (
            "Crushed San Marzano tomatoes seasoned with salt & oregano, "
            "low-moisture mozzarella spread edge-to-edge touching the skillet "
            "walls, fresh basil."
        ),
        "bake": (
            "550°F (290°C) on the bottom oven rack for 12-15 min until bubbly "
            "on top and golden-brown on the bottom."
        ),
        "tip": (
            "Spread cheese all the way to the skillet wall for a crispy, "
            "caramelized frico crust!"
        ),
    },
    {
        "title": "Detroit-Style Crispy Edge Pan Pizza",
        "style": "Detroit Square (Frico Crown & Red Top Stripes)",
        "dough": (
            "300g bread flour, 220g warm water (73%), 6g salt, 4g yeast. Mix, "
            "rest, dimple into heavily buttered/oiled pan, proof 2-3h until airy."
        ),
        "toppings": (
            "Cubed Wisconsin brick cheese (or 50/50 Monterey Jack and mozzarella) "
            "pushed right against the pan edges. Warm seasoned tomato sauce "
            "ladled in 2 racing stripes on top."
        ),
        "bake": (
            "500°F (260°C) for 15 min until the cheese edges are deep "
            "golden-brown and sizzling."
        ),
        "tip": (
            "Sauce goes ON TOP of the cheese (racing stripes) to keep the crust "
            "super airy and crisp."
        ),
    },
    {
        "title": "Classic Neapolitan Skillet-Broiler Pizza",
        "style": "Neapolitan (Leopard-Spotted, High-Heat Hack)",
        "dough": (
            "250g '00' flour, 160g cold water (65%), 5g sea salt, 1g instant "
            "yeast. Cold ferment in fridge for 24-48h."
        ),
        "toppings": (
            "Hand-crushed San Marzano tomatoes, torn fresh mozzarella "
            "(thoroughly drained), fresh basil leaves, extra virgin olive oil drizzle."
        ),
        "bake": (
            "Heat dry cast iron skillet screaming hot on stovetop. Drop stretched "
            "dough in, top quickly. Once bottom chars (~90s), transfer directly "
            "under high oven broiler for 2 min."
        ),
        "tip": (
            "Dry your fresh mozzarella with paper towels before topping to "
            "prevent sogginess under the broiler."
        ),
    },
    {
        "title": "New York-Style Foldable Thin Crust",
        "style": "NY Street Slice (Crisp Undercarriage, Foldable)",
        "dough": (
            "350g bread flour, 230g water (65%), 7g salt, 4g yeast, 5g sugar "
            "(for oven browning), 10g olive oil. Cold ferment 48-72h."
        ),
        "toppings": (
            "Lightly simmered tomato sauce with garlic and oregano, shredded "
            "whole-milk low-moisture mozzarella, grated Pecorino Romano."
        ),
        "bake": (
            "550°F (290°C) on a preheated pizza steel or stone (preheat 1h) for "
            "6-8 min until blistered and bubbly."
        ),
        "tip": (
            "A pizza steel transfers heat 3x faster than a ceramic stone, "
            "giving you authentic NY blistered crust."
        ),
    },
]
