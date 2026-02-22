"""
Django middleware'leri
"""
from django.shortcuts import redirect
from django.urls import resolve


class LoginRequiredMiddleware:
    """
    Global login zorunlulugu middleware'i.
    Belirli URL'ler disinda tum sayfalara giris gerektirir.
    """

    # Giris gerektirmeyen URL isimleri
    EXEMPT_URLS = [
        'auth_login',
        'auth_logout',
        'lawyer_voting_check',
        'lawyer_voting_check_api',
        'admin:index',
        'admin:login',
    ]

    # Giris gerektirmeyen URL onekleri
    EXEMPT_URL_PREFIXES = [
        '/admin/',
        '/auth/login/',
        '/lawyer/',
        '/static/',
        '/media/',
    ]

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Oturum acik mi kontrol et
        if not request.user.is_authenticated:
            # URL'i coz
            path = request.path

            # Statik dosyalar ve medya dosyalari icin kontrol yapma
            for prefix in self.EXEMPT_URL_PREFIXES:
                if path.startswith(prefix):
                    return self.get_response(request)

            # URL ismini bul
            try:
                url_name = resolve(path).url_name
            except:
                url_name = None

            # Muaf URL'ler icin kontrol yapma
            if url_name and url_name in self.EXEMPT_URLS:
                return self.get_response(request)

            # Giris sayfasina yonlendir
            from django.conf import settings
            login_url = getattr(settings, 'LOGIN_URL', '/auth/login/')
            return redirect(f'{login_url}?next={path}')

        return self.get_response(request)
