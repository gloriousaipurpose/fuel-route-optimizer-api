from django.urls import path
from . import views

urlpatterns = [
    path('api/route/', views.route_api, name='route_api'),
    path('api/cities/', views.cities_api, name='cities_api'),
    path('route-map/', views.map_view, name='map_view'),
]
