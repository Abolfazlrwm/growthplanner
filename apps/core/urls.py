from django.urls import path

from . import views, discovery

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("manus-routes.json", discovery.route_manifest, name="route_manifest"),
    path("robots.txt", discovery.robots, name="robots"),
    path("sitemap.xml", discovery.sitemap, name="sitemap"),
    path("review/", views.review, name="review"),
    path("stats/", views.stats, name="stats"),
    path("lang/<str:code>/", views.set_language, name="set_language"),
    path("focus/", views.focus, name="focus"),
    path("focus/log/", views.focus_log, name="focus_log"),
    path("healthz/", views.healthz, name="healthz"),
    path("offline/", views.offline_page, name="offline"),
    path("sw.js", views.service_worker, name="service_worker"),
]
