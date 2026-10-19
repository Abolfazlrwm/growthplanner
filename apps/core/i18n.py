"""Server-side English translation of rendered Persian HTML.

The app's source language is Persian. When the visitor chose English, every HTML response
(full pages *and* HTMX fragments) is passed through `translate_html`, which

* swaps `lang`/`dir` to en/ltr and mirrors the few direction-specific icons,
* translates visible text and a whitelist of attributes using the dictionary in
  `i18n_en.EN` (entries may contain `{}` placeholders for numbers/names),
* converts Persian digits and punctuation to their Latin forms,
* leaves everything it does not know (usernames, task titles, goal names...) untouched.

Dates and week layout are handled in `utils.dates`; this module is only about words.
"""
import json
import re

from .i18n_en import EN

PERSIAN_LETTER = re.compile(r"[\u0600-\u06FF]")
HAS_PERSIAN_DIGIT = re.compile(r"[۰-۹]")
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٫٬", "0123456789.,")
_PUNCT = str.maketrans({"٪": "%", "،": ",", "؛": ";", "؟": "?"})

_TAG_SPLIT = re.compile(
    r"(<!--.*?-->|<script\b.*?</script>|<style\b.*?</style>|<textarea\b.*?</textarea>|<[^>]+>)", re.S
)
_ATTR = re.compile(
    r'(\s(?:aria-label|title|placeholder|alt|data-msg-[\w-]+|data-tip|data-toast|data-label|data-title|data-text)=")([^"]*)(")'
)
_META_CONTENT = re.compile(r'(\scontent=")([^"]*)(")')
_JSON_LD = re.compile(r'(<script type="application/ld\+json">)(.*?)(</script>)', re.S)
_HTML_TAG = re.compile(r'<html lang="fa" dir="rtl"')

# Directional icons: in a left-to-right layout "next" points right, so swap the pairs.
_ICON_SWAPS = (
    ('href="#i-chevron-right"', 'href="#i-chevron-left__"'),
    ('href="#i-chevron-left"', 'href="#i-chevron-right"'),
    ('href="#i-chevron-left__"', 'href="#i-chevron-left"'),
    ('href="#i-forward"', 'href="#i-forward-r"'),
)

_EXACT = {}
_PLACEHOLDER_RULES = []  # (compiled regex, english template)


_PLACEHOLDER = re.compile(r"(\{d\}|\{\})")
_NUMBER_GROUP = r"([۰-۹0-9]+(?:[.٫][۰-۹0-9]+)?)"


def _build_tables():
    """`{d}` in a key matches a number only; `{}` matches anything (a title, a date...).

    Numbers-only placeholders matter: a loose "{} از {}" rule would otherwise rewrite any
    user text that happens to contain the word "از".
    """
    for key, value in EN.items():
        norm = " ".join(key.split())
        if _PLACEHOLDER.search(norm):
            regex = ""
            for part in _PLACEHOLDER.split(norm):
                if part == "{d}":
                    regex += _NUMBER_GROUP
                elif part == "{}":
                    regex += "(.+?)"
                else:
                    regex += re.escape(part)
            _PLACEHOLDER_RULES.append((len(norm), re.compile("^" + regex + "$", re.S), value))
        else:
            _EXACT[norm] = value
    # Longer (more specific) templates first so "{d} of {d} tasks" wins over "{d} of {d}".
    _PLACEHOLDER_RULES.sort(key=lambda r: -r[0])


_build_tables()


def latin_digits(text):
    return text.translate(_DIGITS)


def _finish(text, translated):
    """Digit/punctuation cleanup for a chunk. Persian letters mean user text: digits only."""
    text = latin_digits(text)
    if not PERSIAN_LETTER.search(text) or translated:
        text = text.translate(_PUNCT)
    return text


def translate_chunk(core, _depth=0):
    """Translate one whitespace-normalised piece of text; return it unchanged if unknown."""
    if not (PERSIAN_LETTER.search(core) or HAS_PERSIAN_DIGIT.search(core) or "٪" in core):
        return core
    hit = _EXACT.get(core)
    if hit is not None:
        return hit
    for _, rx, tpl in _PLACEHOLDER_RULES:
        m = rx.match(core)
        if m:
            groups = [translate_chunk(g, _depth + 1) if _depth < 3 else g for g in m.groups()]
            out = tpl
            for g in groups:
                out = out.replace("{}", _finish(g, True) if not PERSIAN_LETTER.search(g) else g, 1)
            return out
    if _depth < 3:
        for sep, joiner in ((" · ", " · "), ("، ", ", "), (" — ", " — ")):
            if sep in core:
                parts = core.split(sep)
                translated = [translate_chunk(p, _depth + 1) for p in parts]
                if translated != parts or all(not PERSIAN_LETTER.search(p) for p in translated):
                    return joiner.join(translated)
    return _finish(core, False)


def _translate_text(text):
    lead = text[: len(text) - len(text.lstrip())]
    trail = text[len(text.rstrip()):]
    core = " ".join(text.split())
    if not core:
        return text
    return lead + translate_chunk(core) + trail


def _translate_attr_value(value):
    core = " ".join(value.split())
    return translate_chunk(core) if core else value


def _translate_tag(tag):
    if tag.startswith("<meta"):
        tag = _META_CONTENT.sub(lambda m: m.group(1) + _translate_attr_value(m.group(2)) + m.group(3), tag)
    tag = _ATTR.sub(lambda m: m.group(1) + _translate_attr_value(m.group(2)) + m.group(3), tag)
    if "#i-" in tag:
        for old, new in _ICON_SWAPS:
            tag = tag.replace(old, new)
    return tag


def _translate_json_ld(match):
    try:
        data = json.loads(match.group(2))
    except ValueError:
        return match.group(0)

    def walk(node):
        if isinstance(node, dict):
            return {k: ("en" if k == "inLanguage" else walk(v)) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v) for v in node]
        if isinstance(node, str):
            return _translate_attr_value(node)
        return node

    return match.group(1) + json.dumps(walk(data), ensure_ascii=False) + match.group(3)


def translate_html(html):
    """Translate a rendered Persian HTML document or fragment to English."""
    html = _JSON_LD.sub(_translate_json_ld, html)
    html = _HTML_TAG.sub('<html lang="en" dir="ltr"', html, count=1)
    out = []
    for piece in _TAG_SPLIT.split(html):
        if not piece:
            continue
        if piece.startswith("<"):
            if piece.startswith(("<!--", "<script", "<style", "<textarea")):
                out.append(piece)
            else:
                out.append(_translate_tag(piece))
        else:
            out.append(_translate_text(piece))
    return "".join(out)


# Language names are shown in their own script on purpose.
NATIVE_LANGUAGE_NAMES = {"فارسی"}


def visible_persian(html):
    """Persian words still visible after translation (used by tests to find missing strings)."""
    leftovers = []
    for piece in _TAG_SPLIT.split(html):
        if not piece:
            continue
        if piece.startswith("<"):
            if piece.startswith(("<!--", "<script", "<style", "<textarea")):
                continue
            for _, value, _ in _ATTR.findall(piece):
                if PERSIAN_LETTER.search(value) and " ".join(value.split()) not in NATIVE_LANGUAGE_NAMES:
                    leftovers.append(" ".join(value.split()))
        elif PERSIAN_LETTER.search(piece) and " ".join(piece.split()) not in NATIVE_LANGUAGE_NAMES:
            leftovers.append(" ".join(piece.split()))
    return leftovers
