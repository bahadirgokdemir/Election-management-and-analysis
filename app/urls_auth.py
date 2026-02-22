"""
Auth URL configuration
"""
from django.urls import path
from . import views_auth

urlpatterns = [
    # Giris/Cikis
    path('login/', views_auth.auth_login, name='auth_login'),
    path('logout/', views_auth.auth_logout, name='auth_logout'),

    # Kullanici Yonetimi (Admin)
    path('users/', views_auth.auth_users, name='auth_users'),
    path('users/create/', views_auth.auth_create_user, name='auth_create_user'),
    path('users/<int:user_id>/role/', views_auth.auth_change_user_role, name='auth_change_user_role'),

    # Erisim Kodlari (Admin)
    path('access-codes/', views_auth.auth_access_codes, name='auth_access_codes'),
    path('access-codes/generate/', views_auth.auth_generate_access_code, name='auth_generate_access_code'),
    path('access-codes/<int:code_id>/toggle/', views_auth.auth_toggle_access_code, name='auth_toggle_access_code'),
    path('access-codes/<int:code_id>/delete/', views_auth.auth_delete_access_code, name='auth_delete_access_code'),
]
