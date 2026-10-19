"""Applies the visitor's interface language and, for English, translates the rendered HTML."""
from django.utils import translation
from django.utils.cache import patch_vary_headers

from .i18n import translate_html
from .ui import LANG_COOKIE, PALETTE_COOKIE, clean_lang, clean_palette


class UiPreferencesMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        lang = clean_lang(request.COOKIES.get(LANG_COOKIE))
        request.ui_lang = lang
        request.ui_palette = clean_palette(request.COOKIES.get(PALETTE_COOKIE))
        request.LANGUAGE_CODE = lang
        translation.activate(lang)
        try:
            response = self.get_response(request)
        finally:
            translation.deactivate()

        patch_vary_headers(response, ("Cookie",))
        response.headers.setdefault("Content-Language", lang)
        content_type = response.headers.get("Content-Type", "")
        if lang == "en" and content_type.startswith("text/html") and not response.streaming:
            charset = response.charset or "utf-8"
            response.content = translate_html(response.content.decode(charset)).encode(charset)
            if response.has_header("Content-Length"):
                response.headers["Content-Length"] = str(len(response.content))
        return response
