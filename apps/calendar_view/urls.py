from django.urls import path

from . import feeds, views

app_name = "calendar_view"

urlpatterns = [
    path("subscription/", feeds.subscription, name="subscription"),
    path("feed/<str:token>.ics", feeds.calendar_feed, name="feed"),
    path("", views.month_view, name="month"),
    path("<int:year>/<int:month>/", views.month_view, name="month"),
    path("week/", views.week_view, name="week"),
    path("week/<str:date>/", views.week_view, name="week"),
    path("timeline/", views.day_timeline, name="timeline"),
    path("timeline/<str:date>/", views.day_timeline, name="timeline"),
]
