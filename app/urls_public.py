"""
Public URL configuration - Giris gerektirmeyen sayfalar
"""
from django.urls import path
from . import views_public

urlpatterns = [
    # Avukat oy durumu kontrolu
    path('check/', views_public.lawyer_voting_check, name='lawyer_voting_check'),
    path('check/api/', views_public.lawyer_voting_check_api, name='lawyer_voting_check_api'),
]
