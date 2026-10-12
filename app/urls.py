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
]