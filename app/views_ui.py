from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator
from django.db.models import Q
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, JsonResponse
from django.db import transaction
import csv
from io import BytesIO

from .models import Lawyer, Person, StatusOption, LawyerPerson, UploadBatch, Election
from .services.importer import parse_and_stage
from .services.diff_service import compute_diff
from .services.apply_service import apply_diff
from .services.reports import report_overview
from .services.unique_people_service import UniquePeopleService
from .services.person_analytics_service import PersonAnalyticsService

from django.shortcuts import get_object_or_404

@require_http_methods(["GET"])
def ui_dashboard(request):
    data = report_overview()
    return render(request, 'app/dashboard.html', {'data': data})


@csrf_exempt
@require_http_methods(["GET", "POST"])
def ui_lawyers(request):
    if request.method == "POST":
        sicil = (request.POST.get('sicil') or '').strip()
        ad = (request.POST.get('ad') or '').strip()
        soyad = (request.POST.get('soyad') or '').strip()

        if not sicil or not ad or not soyad:
            messages.error(request, "Sicil No, Ad ve Soyad zorunludur.")
            return redirect('ui_lawyers')

        lawyer, created = Lawyer.objects.get_or_create(
            sicil_no=sicil,
            defaults={'ad': ad, 'soyad': soyad}
        )
        if created:
            messages.success(request, f"Avukat eklendi: {sicil} — {ad} {soyad}")
        else:
            if lawyer.ad != ad or lawyer.soyad != soyad:
                messages.info(request, f"Bu sicil zaten kayıtlı: {lawyer.sicil_no} — {lawyer.ad} {lawyer.soyad}. "
                                       f"Girdiğiniz isim uygulanmadı.")
            else:
                messages.info(request, "Bu sicil no zaten mevcut; yeni bir kayıt oluşturulmadı.")
        return redirect('ui_lawyers')

    q = (request.GET.get('q') or '').strip()
    qs = Lawyer.objects.all().order_by('-id')
    if q:
        qs = qs.filter(Q(sicil_no__icontains=q) | Q(ad__icontains=q) | Q(soyad__icontains=q))
    page = Paginator(qs, 20).get_page(request.GET.get('page'))
    return render(request, 'app/lawyers_list.html', {'page': page, 'q': q})


@require_http_methods(["GET"])
def ui_people(request):
    q = (request.GET.get('q') or '').strip()
    status_key = request.GET.get('status')
    lawyer_id = request.GET.get('lawyer')
    selected_ilce = request.GET.get('ilce')

    # Gelişmiş arama parametreleri
    adv_sicil = (request.GET.get('sicil') or '').strip()
    adv_ad = (request.GET.get('ad') or '').strip()
    adv_soyad = (request.GET.get('soyad') or '').strip()
    adv_mail = (request.GET.get('mail') or '').strip()
    adv_telno = (request.GET.get('telno') or '').strip()
    adv_ilce = (request.GET.get('ilce_search') or '').strip()
    adv_adres = (request.GET.get('adres') or '').strip()
    adv_notlar = (request.GET.get('notlar') or '').strip()

    # LawyerPerson ilişkilerini getir - her ilişki ayrı satır olacak
    # KRITIK: Artık tüm veriler LawyerPerson'da, Person'a bakmıyoruz
    qs = LawyerPerson.objects.select_related(
        'cevap_status',
        'lawyer'
    ).filter(active=True).order_by('-id', 'lawyer__ad', 'lawyer__soyad')

    # Genel arama (tüm alanlarda) - artık LawyerPerson alanlarında ara
    if q:
        qs = qs.filter(
            Q(kisi_sicilno__icontains=q) |
            Q(ad__icontains=q) |
            Q(soyad__icontains=q) |
            Q(mail__icontains=q) |
            Q(ilce__icontains=q) |
            Q(telno__icontains=q) |
            Q(adres_aciklama__icontains=q) |
            Q(notlar__icontains=q)
        )

    # Alan bazında gelişmiş aramalar - LawyerPerson alanları
    if adv_sicil:
        qs = qs.filter(kisi_sicilno__icontains=adv_sicil)
    if adv_ad:
        qs = qs.filter(ad__icontains=adv_ad)
    if adv_soyad:
        qs = qs.filter(soyad__icontains=adv_soyad)
    if adv_mail:
        qs = qs.filter(mail__icontains=adv_mail)
    if adv_telno:
        qs = qs.filter(telno__icontains=adv_telno)
    if adv_ilce:
        qs = qs.filter(ilce__icontains=adv_ilce)
    if adv_adres:
        qs = qs.filter(adres_aciklama__icontains=adv_adres)
    if adv_notlar:
        qs = qs.filter(notlar__icontains=adv_notlar)

    # İlçe dropdown filtresi
    if selected_ilce and selected_ilce != 'None':
        qs = qs.filter(ilce=selected_ilce)

    # Durum filtresi
    if status_key and status_key != 'None':
        qs = qs.filter(cevap_status__key=status_key)

    # Avukat filtresi
    if lawyer_id and lawyer_id != 'None':
        qs = qs.filter(lawyer_id=lawyer_id)

    # İlçe listesi (dropdown için) - LawyerPerson'dan al
    districts = LawyerPerson.objects.filter(active=True).exclude(ilce__isnull=True).exclude(ilce='').values_list('ilce', flat=True).distinct().order_by('ilce')

    page = Paginator(qs, 25).get_page(request.GET.get('page'))
    statuses = StatusOption.objects.all().order_by('key')
    lawyers = Lawyer.objects.all().order_by('ad', 'soyad')

    return render(request, 'app/people_list.html', {
        'page': page,
        'q': q,
        'status_key': status_key,
        'lawyer_id': lawyer_id,
        'selected_ilce': selected_ilce,
        'districts': districts,
        'statuses': statuses,
        'lawyers': lawyers,
    })


@csrf_exempt
@require_http_methods(["GET", "POST"])
def ui_upload(request):
    # Aktif seçim kontrolü
    active_election = Election.objects.filter(is_active=True).first()
    if active_election:
        messages.error(request, f'Aktif seçim devam ediyor ({active_election.name}). Seçim bitene kadar yükleme yapamazsınız.')
        return redirect('ui_dashboard')

    if request.method == 'GET':
        # Tüm avukatları alfabetik sırala
        lawyers = Lawyer.objects.all().order_by('ad', 'soyad')
        return render(request, 'app/upload_wizard.html', {'lawyers': lawyers})

    # POST
    file = request.FILES.get('file')
    if not file:
        messages.error(request, 'Dosya zorunludur.')
        return redirect('ui_upload')

    # Avukat seçimi: Mevcut mi yoksa yeni mi?
    existing_lawyer_id = request.POST.get('existing_lawyer_id')

    if existing_lawyer_id:
        # Mevcut avukat seçildi
        try:
            lawyer = Lawyer.objects.get(id=existing_lawyer_id)
            messages.info(request, f'Seçilen avukat: {lawyer.ad} {lawyer.soyad} ({lawyer.sicil_no})')
        except Lawyer.DoesNotExist:
            messages.error(request, 'Seçilen avukat bulunamadı.')
            return redirect('ui_upload')
    else:
        # Yeni avukat ekleniyor
        sicil_no = (request.POST.get('lawyer_sicil') or '').strip()
        ad = (request.POST.get('lawyer_ad') or '').strip()
        soyad = (request.POST.get('lawyer_soyad') or '').strip()

        if not sicil_no or not ad or not soyad:
            messages.error(request, 'Yeni avukat için Sicil No, Ad ve Soyad zorunludur.')
            return redirect('ui_upload')

        lawyer, created = Lawyer.objects.get_or_create(
            sicil_no=sicil_no,
            defaults={'ad': ad, 'soyad': soyad}
        )
        if created:
            messages.success(request, f'✓ Yeni avukat oluşturuldu: {sicil_no} — {ad} {soyad}')
        else:
            if (lawyer.ad != ad) or (lawyer.soyad != soyad):
                messages.info(
                    request,
                    f"Bu sicil no zaten kayıtlı: {sicil_no} — {lawyer.ad} {lawyer.soyad}. "
                    f"Gönderdiğiniz isim ({ad} {soyad}) kayda uygulanmadı."
                )
            else:
                messages.info(request, f'Mevcut avukat kullanılıyor: {lawyer.ad} {lawyer.soyad}')

    try:
        # 1) Dosyayı staging'e yükle
        from app.utils.file_validators import ValidationError

        try:
            batch_id, row_count = parse_and_stage(
                file, lawyer.id,
                created_by=str(request.user) if request.user.is_authenticated else None
            )
        except ValidationError as ve:
            # Detaylı validasyon hatası
            error_msg = f'❌ Dosya Validasyon Hatası: {ve.message}'
            messages.error(request, error_msg)

            # Detayları ayrı mesajlar olarak ekle
            if ve.details:
                for detail in ve.details[:10]:  # Max 10 detay göster
                    messages.warning(request, f'  • {detail}')

            return redirect('ui_upload')

        # 2) Otomatik olarak uygula
        actor = str(request.user) if request.user.is_authenticated else None
        result = apply_diff(batch_id, actor=actor)

        if result.get('ok'):
            counts = result.get('counts', {})
            added = counts.get('added', 0)
            changed = counts.get('changed', 0)
            messages.success(
                request,
                f'✓ Yükleme başarılı! {row_count} satır işlendi. '
                f'{added} yeni kayıt eklendi, {changed} kayıt güncellendi.'
            )
        else:
            messages.warning(request, f'Yükleme tamamlandı ancak uygulama sırasında sorun oluştu: {result.get("message")}')

        return redirect('ui_dashboard')
    except Exception as e:
        messages.error(request, f'Beklenmeyen hata: {e}')
        return redirect('ui_upload')


@require_http_methods(["GET"])
def ui_diff_preview(request, batch_id: int):
    diff = compute_diff(batch_id)
    return render(request, 'app/diff_preview.html', {'diff': diff})


@csrf_exempt
@require_http_methods(["POST"])
def ui_approve_batch(request, batch_id: int):
    res = apply_diff(batch_id, actor=str(request.user) if request.user.is_authenticated else None)
    if res.get('ok'):
        messages.success(request, 'Değişiklikler uygulandı.')
        return redirect('ui_dashboard')
    messages.error(request, res.get('message', 'Uygulama başarısız.'))
    return redirect('ui_diff_preview', batch_id=batch_id)


@require_http_methods(["GET"])
def ui_people_export_preview(request):
    """Export önizlemesi için ilk 10 satırı ve kullanılabilir sütunları döndürür."""
    q = (request.GET.get('q') or '').strip()
    status_key = request.GET.get('status')
    lawyer_id = request.GET.get('lawyer')

    # LawyerPerson kayıtlarını çek - her kayıt ayrı satır
    qs = LawyerPerson.objects.select_related('cevap_status', 'lawyer').filter(active=True)

    if q:
        qs = qs.filter(
            Q(kisi_sicilno__icontains=q) |
            Q(ad__icontains=q) |
            Q(soyad__icontains=q) |
            Q(mail__icontains=q) |
            Q(ilce__icontains=q) |
            Q(telno__icontains=q) |
            Q(adres_aciklama__icontains=q) |
            Q(notlar__icontains=q)
        )
    if status_key and status_key not in ('None', '', 'null'):
        qs = qs.filter(cevap_status__key=status_key)
    if lawyer_id and lawyer_id not in ('None', '', 'null'):
        try:
            qs = qs.filter(lawyer_id=int(lawyer_id))
        except (ValueError, TypeError):
            pass

    # İlçe filtresi ekle
    ilce_filter = request.GET.get('ilce')
    if ilce_filter and ilce_filter not in ('None', '', 'null'):
        qs = qs.filter(ilce=ilce_filter)

    # Kullanılabilir sütunlar
    available_columns = [
        {'key': 'kisi_sicilno', 'label': 'Sicil No', 'default': True},
        {'key': 'ad', 'label': 'Ad', 'default': True},
        {'key': 'soyad', 'label': 'Soyad', 'default': True},
        {'key': 'mail', 'label': 'E-posta', 'default': True},
        {'key': 'telno', 'label': 'Telefon', 'default': False},
        {'key': 'ilce', 'label': 'İlçe', 'default': True},
        {'key': 'adres_aciklama', 'label': 'Adres Açıklama', 'default': False},
        {'key': 'notlar', 'label': 'Notlar', 'default': False},
        {'key': 'cevap_status', 'label': 'Cevap Durumu', 'default': True},
        {'key': 'avukat', 'label': 'Avukat', 'default': True},
    ]

    # İlk 10 satır önizleme
    preview_data = []
    for lp in qs[:10]:
        preview_data.append({
            'kisi_sicilno': lp.kisi_sicilno,
            'ad': lp.ad,
            'soyad': lp.soyad,
            'mail': lp.mail or '',
            'telno': lp.telno or '',
            'ilce': lp.ilce or '',
            'adres_aciklama': lp.adres_aciklama or '',
            'notlar': lp.notlar or '',
            'cevap_status': lp.cevap_status.label if lp.cevap_status else '',
            'avukat': f"{lp.lawyer.ad} {lp.lawyer.soyad}" if lp.lawyer else '',
        })

    # Filtre seçenekleri için listeler
    districts = list(LawyerPerson.objects.filter(active=True).exclude(ilce__isnull=True).exclude(ilce='').values_list('ilce', flat=True).distinct().order_by('ilce'))
    statuses = list(StatusOption.objects.all().values('key', 'label'))
    lawyers = list(Lawyer.objects.all().values('id', 'ad', 'soyad').order_by('ad', 'soyad'))

    return JsonResponse({
        'columns': available_columns,
        'preview': preview_data,
        'total_count': qs.count(),
        'districts': districts,
        'statuses': statuses,
        'lawyers': lawyers,
    })


@csrf_exempt
@require_http_methods(["POST"])
def ui_people_export_download(request):
    """
    Seçilen sütunlarla filtrelenmiş kişileri istenen formatta (CSV/Excel/PDF) indirir.
    """
    from .services.export_service import ExportService

    q = (request.POST.get('q') or '').strip()
    status_key = request.POST.get('status')
    lawyer_id = request.POST.get('lawyer')
    selected_ilce = request.POST.get('ilce')
    selected_columns = request.POST.getlist('columns[]')
    export_format = request.POST.get('format', 'csv')  # csv, excel, pdf
    include_stats = request.POST.get('include_stats', 'true') == 'true'

    if not selected_columns:
        return JsonResponse({'error': 'Lütfen en az bir sütun seçin'}, status=400)

    # LawyerPerson kayıtlarını çek - her kayıt ayrı satır
    qs = LawyerPerson.objects.select_related('cevap_status', 'lawyer').filter(active=True).order_by('id')

    # Filtreler
    if q:
        qs = qs.filter(
            Q(kisi_sicilno__icontains=q) |
            Q(ad__icontains=q) |
            Q(soyad__icontains=q) |
            Q(mail__icontains=q) |
            Q(ilce__icontains=q) |
            Q(telno__icontains=q) |
            Q(adres_aciklama__icontains=q) |
            Q(notlar__icontains=q)
        )
    if status_key and status_key not in ('None', '', 'null'):
        qs = qs.filter(cevap_status__key=status_key)
    if lawyer_id and lawyer_id not in ('None', '', 'null'):
        try:
            qs = qs.filter(lawyer_id=int(lawyer_id))
        except (ValueError, TypeError):
            pass
    if selected_ilce and selected_ilce not in ('None', '', 'null'):
        qs = qs.filter(ilce=selected_ilce)

    # Filtre bilgileri (Excel/PDF için)
    filter_info = {}
    if q:
        filter_info['q'] = q
    if status_key and status_key not in ('None', '', 'null'):
        status = StatusOption.objects.filter(key=status_key).first()
        if status:
            filter_info['status_label'] = status.label
    if lawyer_id and lawyer_id not in ('None', '', 'null'):
        try:
            lawyer = Lawyer.objects.filter(id=int(lawyer_id)).first()
            if lawyer:
                filter_info['lawyer_name'] = f"{lawyer.ad} {lawyer.soyad}"
        except (ValueError, TypeError):
            pass
    if selected_ilce and selected_ilce not in ('None', '', 'null'):
        filter_info['ilce'] = selected_ilce

    # Format'a göre export
    if export_format == 'excel':
        return ExportService.export_to_excel(
            queryset=qs,
            selected_columns=selected_columns,
            include_stats=include_stats,
            include_filters=filter_info
        )
    elif export_format == 'pdf':
        return ExportService.export_to_pdf(
            queryset=qs,
            selected_columns=selected_columns,
            include_stats=include_stats,
            include_filters=filter_info
        )
    else:  # csv (default)
        return ExportService.export_to_csv(
            queryset=qs,
            selected_columns=selected_columns
        )


@require_http_methods(["GET"])
def ui_people_export(request):
    """Filtrelenmiş kişileri CSV olarak indirir (eski yöntem - geriye dönük uyumluluk)."""
    q = (request.GET.get('q') or '').strip()
    status_key = request.GET.get('status')
    lawyer_id = request.GET.get('lawyer')

    qs = Person.objects.select_related('cevap_status').prefetch_related(
        'lawyerperson_set__lawyer'
    ).all()

    if q:
        qs = qs.filter(
            Q(kisi_sicilno__icontains=q) |
            Q(ad__icontains=q) |
            Q(soyad__icontains=q) |
            Q(mail__icontains=q) |
            Q(ilce__icontains=q) |
            Q(telno__icontains=q) |
            Q(adres_aciklama__icontains=q) |
            Q(notlar__icontains=q)
        )
    if status_key and status_key != 'None':
        qs = qs.filter(cevap_status__key=status_key)
    if lawyer_id and lawyer_id != 'None':
        qs = qs.filter(lawyerperson__lawyer_id=lawyer_id)

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="kisiler.csv"'

    writer = csv.writer(response)
    writer.writerow(['kisi_sicilno', 'ad', 'soyad', 'mail', 'ilce', 'cevap_status', 'avukatlar'])
    for p in qs:
        # Get all lawyers for this person
        lawyers_str = ', '.join([f"{lp.lawyer.ad} {lp.lawyer.soyad} ({lp.lawyer.sicil_no})"
                                 for lp in p.lawyerperson_set.all()])
        writer.writerow([
            p.kisi_sicilno,
            p.ad,
            p.soyad,
            p.mail or '',
            p.ilce or '',
            p.cevap_status.key if p.cevap_status else '',
            lawyers_str
        ])

    return response


# ⬇️ Şablon indirme — CSV
@require_http_methods(["GET"])
def ui_download_template_csv(request):
    """
    Excel/CSV şablonu (kolon başlıkları):
    sicilno,ad,soyad,cevapDurumu,telno,mail,ilce,adres_aciklama,notlar
    """
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="liste_sablon.csv"'
    writer = csv.writer(response)
    writer.writerow(['sicilno', 'ad', 'soyad', 'cevapDurumu', 'telno', 'mail', 'ilce', 'adres_aciklama', 'notlar'])
    return response


# ⬇️ Şablon indirme — XLSX (openpyxl ile)
@require_http_methods(["GET"])
def ui_download_template_xlsx(request):
    """
    Aynı kolonları xlsx olarak üretir.
    """
    try:
        from openpyxl import Workbook
    except Exception:
        # openpyxl yoksa içeriden uyarı verelim
        return ui_download_template_csv(request)

    wb = Workbook()
    ws = wb.active
    ws.title = "Sablon"
    headers = ['sicilno', 'ad', 'soyad', 'cevapDurumu', 'telno', 'mail', 'ilce', 'adres_aciklama', 'notlar']
    ws.append(headers)

    # İsteğe bağlı: ilk satıra örnek satır (yorum satırı gibi)
    # ws.append(['123', 'Ali', 'Kaya', 'geliyor', '535...', 'ali@example.com', 'Çankaya', 'Adres açıklaması', 'Not...'])

    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)

    resp = HttpResponse(
        bio.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    resp['Content-Disposition'] = 'attachment; filename="liste_sablon.xlsx"'
    return resp
# ========== YENİ: Seçili satırları uygula ==========
@csrf_exempt
@require_http_methods(["POST"])
def ui_approve_selected(request, batch_id: int):
    """
    Diff'ten sadece seçilen satırları uygular.
    Form inputları:
      - added:   çoklu checkbox (value=kisi_sicilno)
      - removed: çoklu checkbox (value=kisi_sicilno)
      - changed: çoklu checkbox (value=kisi_sicilno) -> tüm değişen alanlar uygulanır
    """
    diff = compute_diff(batch_id)
    sel_added = set(request.POST.getlist('added'))
    sel_removed = set(request.POST.getlist('removed'))
    sel_changed = set(request.POST.getlist('changed'))

    # diff.lawyer.* bilgileri diff objesinde mevcut
    lawyer_id = diff['lawyer']['id'] if isinstance(diff.get('lawyer'), dict) and diff['lawyer'].get('id') else None
    if not lawyer_id:
        messages.error(request, 'Avukat bilgisi bulunamadı.')
        return redirect('ui_diff_preview', batch_id=batch_id)

    try:
        lawyer = Lawyer.objects.get(id=lawyer_id)
    except Lawyer.DoesNotExist:
        messages.error(request, 'Avukat kaydı bulunamadı.')
        return redirect('ui_diff_preview', batch_id=batch_id)

    # Yardımcı: status key -> instance
    def get_status(key):
        if not key:
            return None
        try:
            return StatusOption.objects.get(key=key)
        except StatusOption.DoesNotExist:
            return None

    applied_add, applied_remove, applied_change = 0, 0, 0

    with transaction.atomic():
        # ADDED - Yeni kayıtlar
        for row in diff.get('added', []):
            ks = str(row.get('kisi_sicilno') or '')
            if ks not in sel_added:
                continue

            # Person global kaydı (referans için) - sadece sicilno saklanır
            person, _ = Person.objects.get_or_create(
                kisi_sicilno=ks,
                defaults={
                    'ad': row.get('ad') or '',
                    'soyad': row.get('soyad') or '',
                }
            )

            # KRITIK: Gerçek veriler LawyerPerson'da saklanır
            # Her avukat için bağımsız kopya
            LawyerPerson.objects.update_or_create(
                lawyer=lawyer,
                kisi_sicilno=ks,
                defaults={
                    'person': person,
                    'ad': row.get('ad') or '',
                    'soyad': row.get('soyad') or '',
                    'mail': row.get('mail') or '',
                    'telno': row.get('telno') or '',
                    'ilce': row.get('ilce') or '',
                    'adres_aciklama': row.get('adres_aciklama') or '',
                    'notlar': row.get('notlar') or '',
                    'cevap_status': get_status(row.get('cevap_status_key')),
                    'active': True
                }
            )
            applied_add += 1

        # REMOVED - Kayıt silme (soft delete)
        for row in diff.get('removed', []):
            ks = str(row.get('kisi_sicilno') or '')
            if ks not in sel_removed:
                continue

            # Bu avukattan kaldır (hard delete veya soft delete)
            deleted_count = LawyerPerson.objects.filter(
                lawyer=lawyer,
                kisi_sicilno=ks
            ).delete()[0]

            if deleted_count > 0:
                applied_remove += 1

        # CHANGED - Mevcut kayıtları güncelle
        for row in diff.get('changed', []):
            ks = str(row.get('kisi_sicilno') or '')
            if ks not in sel_changed:
                continue

            after = row.get('after') or {}

            # Person referansını al/oluştur
            person, _ = Person.objects.get_or_create(
                kisi_sicilno=ks,
                defaults={
                    'ad': after.get('ad') or '',
                    'soyad': after.get('soyad') or '',
                }
            )

            # KRITIK: LawyerPerson'ı güncelle - sadece bu avukatın verisi
            LawyerPerson.objects.update_or_create(
                lawyer=lawyer,
                kisi_sicilno=ks,
                defaults={
                    'person': person,
                    'ad': after.get('ad') or '',
                    'soyad': after.get('soyad') or '',
                    'mail': after.get('mail') or '',
                    'telno': after.get('telno') or '',
                    'ilce': after.get('ilce') or '',
                    'adres_aciklama': after.get('adres_aciklama') or '',
                    'notlar': after.get('notlar') or '',
                    'cevap_status': get_status(after.get('cevap_status_key')),
                    'active': True
                }
            )
            applied_change += 1

    messages.success(
        request,
        f"Seçili değişiklikler uygulandı. (+{applied_add} / -{applied_remove} / Δ{applied_change})"
    )
    return redirect('ui_dashboard')


@require_http_methods(["GET"])
def ui_lawyer_people(request, lawyer_id: int):
    lawyer = get_object_or_404(Lawyer, id=lawyer_id)
    q = (request.GET.get('q') or '').strip()
    status_key = request.GET.get('status')

    qs = Person.objects.filter(
        lawyerperson__lawyer=lawyer
    ).select_related('cevap_status').order_by('soyad', 'ad')

    if q:
        qs = qs.filter(
            Q(kisi_sicilno__icontains=q) |
            Q(ad__icontains=q) |
            Q(soyad__icontains=q) |
            Q(mail__icontains=q) |
            Q(ilce__icontains=q) |
            Q(telno__icontains=q) |
            Q(adres_aciklama__icontains=q) |
            Q(notlar__icontains=q)
        )
    if status_key:
        qs = qs.filter(cevap_status__key=status_key)

    page = Paginator(qs, 25).get_page(request.GET.get('page'))
    statuses = StatusOption.objects.all().order_by('key')

    return render(request, 'app/lawyer_people.html', {
        'lawyer': lawyer,
        'page': page,
        'q': q,
        'status_key': status_key,
        'statuses': statuses,
    })


@require_http_methods(["GET", "POST"])
def ui_person_edit(request, person_id):
    """
    LawyerPerson kaydını düzenle.
    ÖNEMLI: person_id aslında LawyerPerson ID'sidir.
    Her avukatın kendi verisi var, Person tablosu sadece referans.
    """
    lp = get_object_or_404(LawyerPerson, id=person_id)

    if request.method == "GET":
        # LawyerPerson bilgilerini JSON olarak döndür
        statuses = StatusOption.objects.all().order_by('key')
        return JsonResponse({
            'id': lp.id,
            'kisi_sicilno': lp.kisi_sicilno,
            'ad': lp.ad,
            'soyad': lp.soyad,
            'mail': lp.mail or '',
            'telno': lp.telno or '',
            'ilce': lp.ilce or '',
            'adres_aciklama': lp.adres_aciklama or '',
            'notlar': lp.notlar or '',
            'cevap_status_key': lp.cevap_status.key if lp.cevap_status else '',
            'available_statuses': [{'key': s.key, 'label': s.label} for s in statuses]
        })

    if request.method == "POST":
        # LawyerPerson bilgilerini güncelle - sadece bu avukat için
        import json
        data = json.loads(request.body)

        lp.ad = data.get('ad', lp.ad)
        lp.soyad = data.get('soyad', lp.soyad)
        lp.mail = data.get('mail') or None
        lp.telno = data.get('telno') or None
        lp.ilce = data.get('ilce') or None
        lp.adres_aciklama = data.get('adres_aciklama') or None
        lp.notlar = data.get('notlar') or None

        status_key = data.get('cevap_status_key')
        if status_key:
            lp.cevap_status = StatusOption.objects.filter(key=status_key).first()
        else:
            lp.cevap_status = None

        lp.save()
        return JsonResponse({'success': True})


@csrf_exempt
@require_http_methods(["POST"])
def ui_person_relation_delete(request, lawyerperson_id):
    """LawyerPerson ilişkisini sil (soft delete - active=False)"""
    # Aktif seçim kontrolü
    active_election = Election.objects.filter(is_active=True).first()
    if active_election:
        return JsonResponse({'success': False, 'error': f'Aktif seçim devam ediyor ({active_election.name}). Seçim bitene kadar silme işlemi yapamazsınız.'})

    lp = get_object_or_404(LawyerPerson, id=lawyerperson_id)
    lp.active = False
    lp.save()
    return JsonResponse({'success': True})


@csrf_exempt
@require_http_methods(["POST"])
def ui_lawyer_delete(request, lawyer_id):
    """Avukatı ve ona ait tüm ilişkileri sil"""
    # Aktif seçim kontrolü
    active_election = Election.objects.filter(is_active=True).first()
    if active_election:
        messages.error(request, f'Aktif seçim devam ediyor ({active_election.name}). Seçim bitene kadar silme işlemi yapamazsınız.')
        return redirect('ui_lawyers')

    lawyer = get_object_or_404(Lawyer, id=lawyer_id)

    # Avukata ait kişi sayısını al
    person_count = LawyerPerson.objects.filter(lawyer=lawyer, active=True).count()

    with transaction.atomic():
        # Tüm ilişkileri sil
        LawyerPerson.objects.filter(lawyer=lawyer).delete()

        # Yükleme kayıtlarını sil
        UploadBatch.objects.filter(lawyer=lawyer).delete()

        # Avukatı sil
        lawyer.delete()

    return JsonResponse({
        'success': True,
        'deleted_relations': person_count
    })


@require_http_methods(["GET"])
def ui_unique_people(request):
    """
    Benzersiz kişiler sayfası - Tekrarlı kayıtlar birleştirilmiş
    Her sicil no için tek kayıt, ama tüm avukat ve bilgiler birleştirilmiş
    """
    q = (request.GET.get('q') or '').strip()
    status_key = request.GET.get('status')
    lawyer_id = request.GET.get('lawyer')
    selected_ilce = request.GET.get('ilce')
    min_records = request.GET.get('min_records')  # Tekrarlı kayıtları filtreleme

    # Min records filtresi
    min_records_int = None
    if min_records and min_records.isdigit():
        min_records_int = int(min_records)

    # Benzersiz kişileri getir
    unique_people = UniquePeopleService.get_unique_people(
        search_query=q,
        status_key=status_key if status_key and status_key != 'None' else None,
        lawyer_id=int(lawyer_id) if lawyer_id and lawyer_id != 'None' else None,
        district=selected_ilce if selected_ilce and selected_ilce != 'None' else None,
        min_records=min_records_int
    )

    # İstatistikler
    stats = UniquePeopleService.get_statistics()

    # Pagination
    from django.core.paginator import Paginator
    page = Paginator(unique_people, 25).get_page(request.GET.get('page'))

    # Filtre seçenekleri
    statuses = StatusOption.objects.all().order_by('key')
    lawyers = Lawyer.objects.all().order_by('ad', 'soyad')
    districts = LawyerPerson.objects.filter(active=True).exclude(ilce__isnull=True).exclude(ilce='').values_list('ilce', flat=True).distinct().order_by('ilce')

    return render(request, 'app/unique_people.html', {
        'page': page,
        'q': q,
        'status_key': status_key,
        'lawyer_id': lawyer_id,
        'selected_ilce': selected_ilce,
        'min_records': min_records,
        'districts': districts,
        'statuses': statuses,
        'lawyers': lawyers,
        'stats': stats,
    })


@require_http_methods(["GET"])
def ui_unique_person_detail(request, kisi_sicilno: str):
    """Belirli bir sicil no için detay modal verisi"""
    person = UniquePeopleService.get_person_details(kisi_sicilno)

    if not person:
        return JsonResponse({'error': 'Kişi bulunamadı'}, status=404)

    return JsonResponse(person)


@require_http_methods(["GET"])
def ui_person_analytics(request, kisi_sicilno: str):
    """
    Kişi bazlı analiz verisi
    Avukat ve durum istatistikleri, grafik verileri
    """
    analytics = PersonAnalyticsService.get_person_analytics(kisi_sicilno)

    if not analytics:
        return JsonResponse({'error': 'Kişi bulunamadı veya veri yok'}, status=404)

    # Karşılaştırmalı istatistikler
    comparison = PersonAnalyticsService.get_comparison_stats(kisi_sicilno)
    analytics['comparison'] = comparison

    return JsonResponse(analytics)
