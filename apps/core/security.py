"""Small application boundary: auth rate limiting and private response headers."""
from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse
import hashlib


class ApplicationSecurityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        guarded = request.path in ("/accounts/login/", "/accounts/register/", "/accounts/password-reset/", "/api/token/")
        if guarded and request.method == "POST":
            # Never trust client supplied X-Forwarded-For; proxy address forms a conservative bucket.
            raw = request.META.get("REMOTE_ADDR", "unknown")
            key = "auth:" + hashlib.sha256(raw.encode()).hexdigest()
            cache.add(key, 0, 300)
            try:
                count = cache.incr(key)
            except ValueError:
                cache.set(key, 1, 300)
                count = 1
            if count > settings.AUTH_RATE_LIMIT:
                response = HttpResponse("درخواست‌های زیادی ارسال شده است. پنج دقیقه بعد دوباره تلاش کنید.", status=429)
                response["Retry-After"] = "300"
                return response
        response = self.get_response(request)
        if request.user.is_authenticated or request.path.startswith(("/api/", "/calendar/feed/", "/accounts/")):
            response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        if not response.has_header("Referrer-Policy"):
            response["Referrer-Policy"] = "same-origin"
        response["Content-Security-Policy"] = "frame-ancestors " + " ".join(settings.FRAME_ANCESTORS)
        if settings.MANAGED_HOSTING:
            response.headers.pop("X-Frame-Options", None)
        return response
