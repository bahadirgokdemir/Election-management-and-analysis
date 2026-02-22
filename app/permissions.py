"""
Yetkilendirme decoratorleri ve DRF permission siniflari
"""
from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.http import JsonResponse
from rest_framework import permissions


def get_user_profile(user):
    """Kullanici profilini guvenli sekilde getir"""
    if not user.is_authenticated:
        return None
    try:
        return user.profile
    except AttributeError:
        return None


# ============================================
# Django View Decoratorleri
# ============================================

def login_required_custom(view_func):
    """
    Giris yapmis kullanici gerektirir.
    Middleware yerine view bazinda kullanilabilir.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.warning(request, 'Bu sayfayi goruntulemek icin giris yapmaniz gerekiyor.')
            return redirect('auth_login')
        return view_func(request, *args, **kwargs)
    return wrapper


def admin_required(view_func):
    """
    Admin rolu gerektirir.
    Superuser veya admin rolundeki kullanicilar erisebilir.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.warning(request, 'Bu sayfayi goruntulemek icin giris yapmaniz gerekiyor.')
            return redirect('auth_login')

        # Superuser her zaman admin yetkisine sahiptir
        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)

        profile = get_user_profile(request.user)
        if not profile or not profile.is_admin():
            # JSON istegi ise JSON yanit don
            if request.headers.get('Content-Type') == 'application/json' or request.headers.get('Accept') == 'application/json':
                return JsonResponse({'error': 'Bu islem icin admin yetkisi gerekiyor.'}, status=403)
            messages.error(request, 'Bu islem icin admin yetkisi gerekiyor.')
            return redirect('ui_dashboard')

        return view_func(request, *args, **kwargs)
    return wrapper


def uploader_required(view_func):
    """
    Veri yukleyici veya admin rolu gerektirir.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.warning(request, 'Bu sayfayi goruntulemek icin giris yapmaniz gerekiyor.')
            return redirect('auth_login')

        # Superuser her zaman yetkilidir
        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)

        profile = get_user_profile(request.user)
        if not profile or not profile.is_uploader():
            if request.headers.get('Content-Type') == 'application/json' or request.headers.get('Accept') == 'application/json':
                return JsonResponse({'error': 'Bu islem icin yukleyici yetkisi gerekiyor.'}, status=403)
            messages.error(request, 'Bu islem icin yukleyici yetkisi gerekiyor.')
            return redirect('ui_dashboard')

        return view_func(request, *args, **kwargs)
    return wrapper


def read_only_allowed(view_func):
    """
    Tum roller erisebilir (en dusuk yetki seviyesi).
    Sadece giris kontrolu yapar.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.warning(request, 'Bu sayfayi goruntulemek icin giris yapmaniz gerekiyor.')
            return redirect('auth_login')
        return view_func(request, *args, **kwargs)
    return wrapper


# ============================================
# DRF Permission Siniflari
# ============================================

class IsAdmin(permissions.BasePermission):
    """
    Admin rolu veya superuser gerektirir
    """
    message = 'Bu islem icin admin yetkisi gerekiyor.'

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        profile = get_user_profile(request.user)
        return profile and profile.is_admin()


class IsUploader(permissions.BasePermission):
    """
    Uploader veya admin rolu gerektirir
    """
    message = 'Bu islem icin yukleyici yetkisi gerekiyor.'

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        profile = get_user_profile(request.user)
        return profile and profile.is_uploader()


class IsReadOnly(permissions.BasePermission):
    """
    Giris yapmis tum kullanicilar erisebilir
    """
    message = 'Bu islem icin giris yapmaniz gerekiyor.'

    def has_permission(self, request, view):
        return request.user.is_authenticated


class IsAdminOrReadOnly(permissions.BasePermission):
    """
    GET istekleri icin giris yeterli, diger metodlar icin admin gerekir
    """
    message = 'Bu islem icin admin yetkisi gerekiyor.'

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False

        # GET, HEAD, OPTIONS - sadece okuma
        if request.method in permissions.SAFE_METHODS:
            return True

        # Diger metodlar icin admin gerekir
        if request.user.is_superuser:
            return True
        profile = get_user_profile(request.user)
        return profile and profile.is_admin()


class IsUploaderOrReadOnly(permissions.BasePermission):
    """
    GET istekleri icin giris yeterli, diger metodlar icin uploader gerekir
    """
    message = 'Bu islem icin yukleyici yetkisi gerekiyor.'

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False

        # GET, HEAD, OPTIONS - sadece okuma
        if request.method in permissions.SAFE_METHODS:
            return True

        # Diger metodlar icin uploader gerekir
        if request.user.is_superuser:
            return True
        profile = get_user_profile(request.user)
        return profile and profile.is_uploader()
