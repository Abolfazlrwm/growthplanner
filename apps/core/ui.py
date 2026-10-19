"""UI preferences that live in cookies: interface language and colour palette."""
SUPPORTED_LANGS = ("fa", "en")
DEFAULT_LANG = "fa"
LANG_COOKIE = "lang"

DEFAULT_PALETTE = "tile"
PALETTE_COOKIE = "palette"
# key, Persian name (the English names live in i18n_en)
PALETTES = (
    ("tile", "کاشی و بامداد"),
    ("sunset", "غروب"),
    ("forest", "جنگل"),
    ("ocean", "اقیانوس"),
    ("orchid", "ارکیده"),
    ("saffron", "زعفران"),
    ("rose", "گل رز"),
    ("graphite", "گرافیت"),
)
PALETTE_KEYS = tuple(k for k, _ in PALETTES)

COOKIE_MAX_AGE = 60 * 60 * 24 * 365


def clean_lang(value):
    return value if value in SUPPORTED_LANGS else DEFAULT_LANG


def clean_palette(value):
    return value if value in PALETTE_KEYS else DEFAULT_PALETTE
