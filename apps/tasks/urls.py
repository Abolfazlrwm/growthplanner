from django.urls import path

from . import smart_views, views

app_name = "tasks"

urlpatterns = [
    path("", views.task_list, name="list"),
    path("smart/", smart_views.smart_add, name="smart_add"),
    path("board/", smart_views.board, name="board"),
    path("search/", views.task_search, name="search"),
    path("export.ics", views.task_export_ics, name="export_ics"),
    path("create/", views.task_create, name="create"),
    path("<int:pk>/status/<str:status>/", views.task_set_status, name="set_status"),
    path("<int:pk>/fail/", views.task_fail, name="fail"),
    path("<int:pk>/move/", views.task_move, name="move"),
    path("<int:pk>/reschedule/", views.task_reschedule, name="reschedule"),
    path("<int:pk>/duplicate/", views.task_duplicate, name="duplicate"),
    path("<int:pk>/delete/", views.task_delete, name="delete"),
    path("<int:pk>/", views.task_detail, name="detail"),
]
