"""
Kimlik dogrulama ve erisim kodu view'lari
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from datetime import timedelta
from django.core.paginator import Paginator
from django.db.models import Q

from .models import Lawyer, Election, LawyerAccessCode, UserProfile
from .permissions import admin_required


@require_http_methods(["GET", "POST"])
def auth_login(request):
    """Giris sayfasi"""
    if request.user.is_authenticated:
        return redirect('ui_dashboard')

    if request.method == "POST":
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')

        if not username or not password:
            messages.error(request, 'Kullanıcı Adı ve Şifre zorunludur.')
            return render(request, 'app/auth/login.html')

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            messages.success(request, f'Hosgeldiniz, {user.get_full_name() or user.username}!')

            # Yonlendirme - next parametresi varsa oraya, yoksa dashboard'a
            next_url = request.GET.get('next') or request.POST.get('next')
            if next_url:
                return redirect(next_url)
            return redirect('ui_dashboard')
        else:
            messages.error(request, 'Gecersiz Kullanıcı Adı veya Şifre.')

    return render(request, 'app/auth/login.html')


@require_http_methods(["GET", "POST"])
def auth_logout(request):
    """Cikis yap"""
    logout(request)
    messages.success(request, 'Basariyla cikis yaptiniz.')
    return redirect('landing')


@admin_required
@require_http_methods(["GET"])
def auth_access_codes(request):
    """Erisim kodlari listesi (Admin)"""
    q = request.GET.get('q', '').strip()
    lawyer_id = request.GET.get('lawyer')
    election_id = request.GET.get('election')
    status_filter = request.GET.get('status', 'all')  # all, active, expired

    qs = LawyerAccessCode.objects.select_related('lawyer', 'election', 'created_by').order_by('-created_at')

    if q:
        qs = qs.filter(
            Q(code__icontains=q) |
            Q(lawyer__sicil_no__icontains=q) |
            Q(lawyer__ad__icontains=q) |
            Q(lawyer__soyad__icontains=q)
        )

    if lawyer_id and lawyer_id != 'None':
        qs = qs.filter(lawyer_id=lawyer_id)

    if election_id and election_id != 'None':
        qs = qs.filter(election_id=election_id)

    now = timezone.now()
    if status_filter == 'active':
        qs = qs.filter(is_active=True, expires_at__gt=now)
    elif status_filter == 'expired':
        qs = qs.filter(Q(is_active=False) | Q(expires_at__lte=now))

    page = Paginator(qs, 20).get_page(request.GET.get('page'))

    return render(request, 'app/auth/access_codes.html', {
        'page': page,
        'q': q,
        'lawyers': Lawyer.objects.all().order_by('ad', 'soyad'),
        'elections': Election.objects.all().order_by('-election_date'),
        'selected_lawyer_id': lawyer_id,
        'selected_election_id': election_id,
        'status_filter': status_filter,
    })


@admin_required
@require_http_methods(["GET", "POST"])
def auth_generate_access_code(request):
    """Erisim kodu olusturma (Admin)"""
    if request.method == "POST":
        lawyer_id = request.POST.get('lawyer_id')
        election_id = request.POST.get('election_id')
        expires_days = int(request.POST.get('expires_days', 30))

        if not lawyer_id or not election_id:
            messages.error(request, 'Avukat ve secim secimi zorunludur.')
            return redirect('auth_generate_access_code')

        lawyer = get_object_or_404(Lawyer, id=lawyer_id)
        election = get_object_or_404(Election, id=election_id)

        # Mevcut aktif kod var mi kontrol et
        existing = LawyerAccessCode.objects.filter(
            lawyer=lawyer,
            election=election,
            is_active=True,
            expires_at__gt=timezone.now()
        ).first()

        if existing:
            messages.warning(request, f'Bu avukat ve secim icin zaten aktif bir kod mevcut: {existing.code}')
            return redirect('auth_access_codes')

        # Yeni kod olustur
        code = LawyerAccessCode.objects.create(
            lawyer=lawyer,
            election=election,
            expires_at=timezone.now() + timedelta(days=expires_days),
            created_by=request.user
        )

        messages.success(request, f'Erisim kodu olusturuldu: {code.code}')
        return redirect('auth_access_codes')

    # GET - Form goster
    return render(request, 'app/auth/generate_access_code.html', {
        'lawyers': Lawyer.objects.all().order_by('ad', 'soyad'),
        'elections': Election.objects.all().order_by('-election_date'),
    })


@admin_required
@csrf_exempt
@require_http_methods(["POST"])
def auth_toggle_access_code(request, code_id):
    """Erisim kodunu aktif/pasif yap"""
    code = get_object_or_404(LawyerAccessCode, id=code_id)
    code.is_active = not code.is_active
    code.save()

    status = 'aktif' if code.is_active else 'pasif'
    return JsonResponse({
        'success': True,
        'message': f'Kod {status} yapildi',
        'is_active': code.is_active
    })


@admin_required
@csrf_exempt
@require_http_methods(["POST"])
def auth_delete_access_code(request, code_id):
    """Erisim kodunu sil"""
    code = get_object_or_404(LawyerAccessCode, id=code_id)
    code.delete()

    return JsonResponse({
        'success': True,
        'message': 'Kod silindi'
    })


@admin_required
@require_http_methods(["GET"])
def auth_users(request):
    """Kullanici listesi (Admin)"""
    q = request.GET.get('q', '').strip()
    role_filter = request.GET.get('role', 'all')

    qs = User.objects.select_related('profile').order_by('-date_joined')

    if q:
        qs = qs.filter(
            Q(username__icontains=q) |
            Q(email__icontains=q) |
            Q(first_name__icontains=q) |
            Q(last_name__icontains=q)
        )

    if role_filter and role_filter != 'all':
        qs = qs.filter(profile__role=role_filter)

    page = Paginator(qs, 20).get_page(request.GET.get('page'))

    return render(request, 'app/auth/users.html', {
        'page': page,
        'q': q,
        'role_filter': role_filter,
        'role_choices': UserProfile.ROLE_CHOICES,
    })


@admin_required
@csrf_exempt
@require_http_methods(["POST"])
def auth_change_user_role(request, user_id):
    """Kullanici rolunu degistir"""
    user = get_object_or_404(User, id=user_id)
    new_role = request.POST.get('role')

    if new_role not in dict(UserProfile.ROLE_CHOICES):
        return JsonResponse({'success': False, 'message': 'Gecersiz rol'}, status=400)

    # Kullanicinin kendi rolunu degistirmesini engelle
    if user.id == request.user.id:
        return JsonResponse({'success': False, 'message': 'Kendi rolunuzu degistiremezsiniz'}, status=400)

    try:
        profile = user.profile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(user=user, role=UserProfile.ROLE_READ_ONLY)

    profile.role = new_role
    profile.save()

    return JsonResponse({
        'success': True,
        'message': f'{user.username} kullanicisinin rolu {profile.get_role_display()} olarak degistirildi',
        'role': new_role,
        'role_display': profile.get_role_display()
    })


@admin_required
@require_http_methods(["GET", "POST"])
def auth_create_user(request):
    """Yeni kullanici olustur (Admin)"""
    if request.method == "POST":
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        password_confirm = request.POST.get('password_confirm', '')
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        role = request.POST.get('role', UserProfile.ROLE_READ_ONLY)

        # Validasyon
        if not username or not password:
            messages.error(request, 'Kullanıcı Adı ve Şifre zorunludur.')
            return redirect('auth_create_user')

        if password != password_confirm:
            messages.error(request, 'Şifreler eslesmiyor.')
            return redirect('auth_create_user')

        if len(password) < 8:
            messages.error(request, 'Şifre en az 8 karakter olmalidir.')
            return redirect('auth_create_user')

        if User.objects.filter(username=username).exists():
            messages.error(request, 'Bu Kullanıcı Adı zaten kullaniliyor.')
            return redirect('auth_create_user')

        # Kullanici olustur
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name
        )

        # Profil rol guncelle (signal otomatik olusturur)
        try:
            profile = user.profile
            profile.role = role
            profile.save()
        except UserProfile.DoesNotExist:
            UserProfile.objects.create(user=user, role=role)

        messages.success(request, f'{username} kullanicisi basariyla olusturuldu.')
        return redirect('auth_users')

    return render(request, 'app/auth/create_user.html', {
        'role_choices': UserProfile.ROLE_CHOICES,
    })
