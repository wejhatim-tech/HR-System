from django.urls import path
from . import views

urlpatterns = [
    path('', views.index),
    path('register', views.register),
    path('login', views.login),
    path('logout', views.logout),
    path('dashboard', views.dashboard),
    path('about', views.about),
    path('employees', views.employees),
    path('employees/<int:id>/edit', views.edit_employee),
    path('employees/<int:id>/update', views.update_employee),
    path('check_in', views.check_in),
    path('check_out', views.check_out),
    path('leaves', views.leaves),
    path('leaves/add', views.add_leave),
    path('leaves/<int:id>/decide', views.decide_leave),
]