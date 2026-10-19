"""Crawler and Preview discovery, without exposing private user data."""
from django.conf import settings
from django.http import HttpResponse


def route_manifest(request):
    return HttpResponse((settings.BASE_DIR / 'static' / 'manus-routes.json').read_text(encoding='utf-8'), content_type='application/json')


def robots(request):
    text = 'User-agent: *\nAllow: /$\nDisallow: /accounts/\nDisallow: /api/\nDisallow: /admin/\nDisallow: /tasks/\nDisallow: /goals/\nDisallow: /habits/\nDisallow: /journal/\nDisallow: /calendar/\nDisallow: /assistant/\nDisallow: /stats/\nDisallow: /focus/\n'
    if settings.PUBLIC_ORIGIN:
        text += 'Sitemap: ' + settings.PUBLIC_ORIGIN + '/sitemap.xml\n'
    return HttpResponse(text, content_type='text/plain')


def sitemap(request):
    if not settings.PUBLIC_ORIGIN:
        return HttpResponse('<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"></urlset>', content_type='application/xml')
    from xml.sax.saxutils import escape
    return HttpResponse('<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>' + escape(settings.PUBLIC_ORIGIN + '/') + '</loc></url></urlset>', content_type='application/xml')
