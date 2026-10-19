import json
from django.conf import settings

from .i18n_en import JS_EN
from .ui import PALETTES


def ui(request):
    """Language, text direction and palette for the base template."""
    lang = getattr(request, "ui_lang", "fa")
    palette = getattr(request, "ui_palette", "tile")
    context = {
        "ui_lang": lang,
        "ui_dir": "ltr" if lang == "en" else "rtl",
        "ui_palette": palette,
        "ui_palettes": PALETTES,
        "public_origin": settings.PUBLIC_ORIGIN,
    }
    if lang == "en":
        # Safe inside a <script>: "<" is escaped so the JSON can never close the tag.
        context["ui_js_i18n"] = json.dumps(JS_EN, ensure_ascii=False).replace("<", "\\u003c")
    return context
