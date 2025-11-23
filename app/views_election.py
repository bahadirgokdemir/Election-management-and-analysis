"""
Seçim günü yönetimi view'ları
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.db.models import Q, Count
from django.utils import timezone
from django.core.paginator import Paginator
from django.contrib import messages
import json

from .models import Election, ElectionVote, LawyerPerson, Lawyer, StatusOption


@require_http_methods(["GET"])
def ui_elections(request):
    """Seçim listesi ve yönetimi"""
    elections = Election.objects.all().order_by('-election_date')

    # Her seçim için istatistikler
    election_stats = []
    for election in elections:
        total_people = LawyerPerson.objects.filter(active=True).count()
        votes = ElectionVote.objects.filter(election=election)
        voted_count = votes.filter(has_voted=True).count()
        not_voted_count = total_people - voted_count

        election_stats.append({
            'election': election,
            'total_people': total_people,
            'voted_count': voted_count,
            'not_voted_count': not_voted_count,
            'participation_rate': round((voted_count / total_people * 100) if total_people > 0 else 0, 1)
        })

    return render(request, 'app/elections.html', {
        'election_stats': election_stats,
    })


@csrf_exempt
@require_http_methods(["POST"])
def ui_election_create(request):
    """Yeni seçim oluştur"""
    name = request.POST.get('name')
    election_date = request.POST.get('election_date')
    description = request.POST.get('description', '')

    if not name or not election_date:
        messages.error(request, 'Seçim adı ve tarihi zorunludur')
        return redirect('ui_elections')

    Election.objects.create(
        name=name,
        election_date=election_date,
        description=description,
        is_active=False,
        allow_external_registration=True
    )

    messages.success(request, f'{name} seçimi başarıyla oluşturuldu')
    return redirect('ui_elections')


@csrf_exempt
@require_http_methods(["POST"])
def ui_election_activate(request, election_id):
    """Seçimi aktif/pasif toggle et"""
    election = get_object_or_404(Election, id=election_id)

    if election.is_active:
        # Zaten aktif ise pasif yap
        election.is_active = False
        election.save()
        messages.success(request, f'{election.name} seçimi pasif edildi')
    else:
        # Pasif ise aktif yap
        election.is_active = True
        election.save()  # save metodu otomatik olarak diğerlerini pasif yapar
        messages.success(request, f'{election.name} seçimi aktif edildi')

    return redirect('ui_elections')


@csrf_exempt
@require_http_methods(["POST"])
def ui_election_toggle_registration(request, election_id):
    """Dışarıdan kayıt kabulünü aç/kapat"""
    election = get_object_or_404(Election, id=election_id)
    election.allow_external_registration = not election.allow_external_registration
    election.save()

    status = "açıldı" if election.allow_external_registration else "kapatıldı"
    messages.success(request, f'{election.name} için dışardan kayıt {status}')
    return redirect('ui_elections')


@csrf_exempt
@require_http_methods(["POST"])
def ui_election_delete(request, election_id):
    """Seçimi sil"""
    election = get_object_or_404(Election, id=election_id)

    # Aktif seçim silinmek isteniyorsa uyarı ver
    if election.is_active:
        messages.error(request, 'Aktif seçim silinemez! Önce başka bir seçimi aktif yapın veya tüm seçimleri pasif yapın.')
        return redirect('ui_elections')

    election_name = election.name
    election.delete()

    messages.success(request, f'{election_name} seçimi silindi')
    return redirect('ui_elections')


@require_http_methods(["GET"])
def ui_election_voting(request, election_id):
    """Seçim ekranı - Kapsamlı, modern tasarım"""
    election = get_object_or_404(Election, id=election_id)

    # İstatistikler
    total_people = LawyerPerson.objects.filter(active=True).count()
    voted_count = ElectionVote.objects.filter(election=election, has_voted=True).count()
    not_voted_count = total_people - voted_count

    return render(request, 'app/election_screen.html', {
        'election': election,
        'total_people': total_people,
        'voted_count': voted_count,
        'not_voted_count': not_voted_count,
        'participation_rate': round((voted_count / total_people * 100) if total_people > 0 else 0, 1),
    })


@csrf_exempt
@require_http_methods(["POST"])
def ui_election_mark_vote(request, election_id):
    """Kişiyi oy verdi/vermedi olarak işaretle"""
    try:
        election = get_object_or_404(Election, id=election_id)

        # Sicil no veya ID ile kişi bulma
        sicil_no = request.POST.get('sicil_no')
        lawyerperson_id = request.POST.get('lawyerperson_id')
        has_voted_param = request.POST.get('has_voted')

        # has_voted parametresini boolean'a çevir
        has_voted = has_voted_param in ['true', 'True', '1', 1, True]
        recorded_by = request.POST.get('recorded_by', 'Sistem')

        # Sicil no ile veya ID ile kişiyi bul
        if sicil_no:
            try:
                # Önce aktif olanı bul, yoksa en son oluşturulanı al
                lawyerperson = LawyerPerson.objects.filter(
                    kisi_sicilno=sicil_no,
                    active=True
                ).first()

                if not lawyerperson:
                    # Aktif yoksa en son oluşturulanı al
                    lawyerperson = LawyerPerson.objects.filter(
                        kisi_sicilno=sicil_no
                    ).order_by('-created_at').first()

                if not lawyerperson:
                    return JsonResponse({
                        'success': False,
                        'message': f'Sicil no {sicil_no} bulunamadı'
                    }, status=404)
            except Exception as e:
                return JsonResponse({
                    'success': False,
                    'message': f'Kişi arama hatası: {str(e)}'
                }, status=500)
        elif lawyerperson_id:
            lawyerperson = get_object_or_404(LawyerPerson, id=lawyerperson_id)
        else:
            return JsonResponse({
                'success': False,
                'message': 'Sicil no veya kişi ID gerekli'
            }, status=400)

        # Oy kaydını oluştur veya güncelle
        vote, created = ElectionVote.objects.get_or_create(
            election=election,
            lawyerperson=lawyerperson,
            defaults={
                'has_voted': has_voted,
                'voted_at': timezone.now() if has_voted else None,
                'recorded_by': recorded_by,
            }
        )

        if not created:
            vote.has_voted = has_voted
            vote.voted_at = timezone.now() if has_voted else None
            vote.recorded_by = recorded_by
            vote.save()

        return JsonResponse({
            'success': True,
            'message': f'{"Oy verdi" if has_voted else "Oy vermedi"} olarak işaretlendi',
            'has_voted': has_voted,
            'voted_at': vote.voted_at.strftime('%H:%M') if vote.voted_at else None,
        })
    except Exception as e:
        import traceback
        print(f"[ERROR] Mark vote error: {str(e)}")
        print(traceback.format_exc())
        return JsonResponse({
            'success': False,
            'message': f'Hata: {str(e)}'
        }, status=500)


@require_http_methods(["GET"])
def ui_election_stats(request, election_id):
    """Seçim istatistikleri"""
    election = get_object_or_404(Election, id=election_id)

    # Genel istatistikler
    total_people = LawyerPerson.objects.filter(active=True).count()
    total_votes = ElectionVote.objects.filter(election=election)
    voted_count = total_votes.filter(has_voted=True).count()
    not_voted_count = total_people - voted_count

    # Avukat bazında istatistikler
    lawyer_stats = []
    for lawyer in Lawyer.objects.all():
        lawyer_people = LawyerPerson.objects.filter(lawyer=lawyer, active=True)
        lawyer_total = lawyer_people.count()

        lawyer_voted = ElectionVote.objects.filter(
            election=election,
            lawyerperson__in=lawyer_people,
            has_voted=True
        ).count()

        lawyer_stats.append({
            'lawyer': lawyer,
            'total': lawyer_total,
            'voted': lawyer_voted,
            'not_voted': lawyer_total - lawyer_voted,
            'rate': round((lawyer_voted / lawyer_total * 100) if lawyer_total > 0 else 0, 1)
        })

    # Durum bazında istatistikler
    status_stats = []
    for status in StatusOption.objects.all():
        status_people = LawyerPerson.objects.filter(cevap_status=status, active=True)
        status_total = status_people.count()

        status_voted = ElectionVote.objects.filter(
            election=election,
            lawyerperson__in=status_people,
            has_voted=True
        ).count()

        status_stats.append({
            'status': status,
            'total': status_total,
            'voted': status_voted,
            'not_voted': status_total - status_voted,
            'rate': round((status_voted / status_total * 100) if status_total > 0 else 0, 1)
        })

    # Saatlik dağılım (son 24 saat)
    hourly_votes = []
    for hour in range(24):
        count = ElectionVote.objects.filter(
            election=election,
            has_voted=True,
            voted_at__hour=hour
        ).count()
        hourly_votes.append({'hour': hour, 'count': count})

    return render(request, 'app/election_stats.html', {
        'election': election,
        'total_people': total_people,
        'voted_count': voted_count,
        'not_voted_count': not_voted_count,
        'participation_rate': round((voted_count / total_people * 100) if total_people > 0 else 0, 1),
        'lawyer_stats': lawyer_stats,
        'status_stats': status_stats,
        'hourly_votes': json.dumps(hourly_votes),
    })


@require_http_methods(["GET"])
def ui_election_check(request, election_id):
    """Hızlı işaretleme modu - Sicil no ile tek tek işaretleme"""
    election = get_object_or_404(Election, id=election_id)

    # İstatistikler
    total_people = LawyerPerson.objects.filter(active=True).count()
    voted_count = ElectionVote.objects.filter(election=election, has_voted=True).count()
    not_voted_count = total_people - voted_count

    return render(request, 'app/election_check.html', {
        'election': election,
        'total_people': total_people,
        'voted_count': voted_count,
        'not_voted_count': not_voted_count,
        'participation_rate': round((voted_count / total_people * 100) if total_people > 0 else 0, 1),
    })


@require_http_methods(["GET"])
def ui_election_voting_data(request, election_id):
    """Seçim modu için kişi verilerini JSON olarak döndür"""
    election = get_object_or_404(Election, id=election_id)

    # Tüm aktif kişileri getir (sadece gerekli alanlar)
    people = LawyerPerson.objects.filter(active=True).select_related('lawyer')

    # Oy durumlarını getir
    votes = {
        vote.lawyerperson_id: vote
        for vote in ElectionVote.objects.filter(election=election).select_related('lawyerperson')
    }

    # JSON formatında veri hazırla
    people_data = []
    for person in people:
        vote = votes.get(person.id)
        people_data.append({
            'id': person.id,
            'kisi_sicilno': person.kisi_sicilno,
            'ad': person.ad,
            'soyad': person.soyad,
            'lawyer_name': f"{person.lawyer.ad} {person.lawyer.soyad}" if person.lawyer else '-',
            'lawyer_sicil': person.lawyer.sicil_no if person.lawyer else '-',
            'has_voted': vote.has_voted if vote else False,
            'voted_at': vote.voted_at.strftime('%H:%M') if vote and vote.voted_at else None,
        })

    return JsonResponse({
        'success': True,
        'people': people_data,
        'stats': {
            'total_people': len(people_data),
            'voted_count': sum(1 for p in people_data if p['has_voted']),
            'not_voted_count': sum(1 for p in people_data if not p['has_voted']),
            'participation_rate': round((sum(1 for p in people_data if p['has_voted']) / len(people_data) * 100) if people_data else 0, 1),
        }
    })


@require_http_methods(["GET"])
def ui_election_dashboard(request, election_id):
    """Seçim günü anasayfa - İstatistikler ve genel bakış"""
    election = get_object_or_404(Election, id=election_id)

    # Genel istatistikler
    total_people = LawyerPerson.objects.filter(active=True).count()
    total_votes = ElectionVote.objects.filter(election=election)
    voted_count = total_votes.filter(has_voted=True).count()
    not_voted_count = total_people - voted_count

    # Avukat bazında istatistikler
    lawyer_stats = []
    for lawyer in Lawyer.objects.all():
        lawyer_people = LawyerPerson.objects.filter(lawyer=lawyer, active=True)
        lawyer_total = lawyer_people.count()

        lawyer_voted = ElectionVote.objects.filter(
            election=election,
            lawyerperson__in=lawyer_people,
            has_voted=True
        ).count()

        lawyer_stats.append({
            'lawyer': lawyer,
            'total': lawyer_total,
            'voted': lawyer_voted,
            'not_voted': lawyer_total - lawyer_voted,
            'rate': round((lawyer_voted / lawyer_total * 100) if lawyer_total > 0 else 0, 1)
        })

    return render(request, 'app/election_dashboard.html', {
        'election': election,
        'total_people': total_people,
        'voted_count': voted_count,
        'not_voted_count': not_voted_count,
        'participation_rate': round((voted_count / total_people * 100) if total_people > 0 else 0, 1),
        'lawyer_stats': lawyer_stats,
    })


@require_http_methods(["GET"])
def ui_election_list(request, election_id):
    """Seçim günü listeleme - Basit oy durumu listesi"""
    election = get_object_or_404(Election, id=election_id)

    # Filtreleme parametreleri
    search = request.GET.get('q', '').strip()
    vote_filter = request.GET.get('vote_status', 'all')  # all, voted, not_voted

    # Tüm aktif kişileri getir
    people = LawyerPerson.objects.filter(active=True).select_related('lawyer')

    # Arama
    if search:
        people = people.filter(
            Q(kisi_sicilno__icontains=search) |
            Q(ad__icontains=search) |
            Q(soyad__icontains=search)
        )

    # Oy durumlarını getir
    votes = {
        vote.lawyerperson_id: vote
        for vote in ElectionVote.objects.filter(election=election).select_related('lawyerperson')
    }

    # Kişilere oy durumlarını ekle
    people_list = []
    for person in people:
        vote = votes.get(person.id)
        has_voted = vote.has_voted if vote else False

        # Oy durumuna göre filtrele
        if vote_filter == 'voted' and not has_voted:
            continue
        elif vote_filter == 'not_voted' and has_voted:
            continue

        people_list.append({
            'person': person,
            'has_voted': has_voted,
            'voted_at': vote.voted_at if vote else None,
        })

    # Sayfalama
    paginator = Paginator(people_list, 50)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # İstatistikler
    total_people = LawyerPerson.objects.filter(active=True).count()
    voted_count = ElectionVote.objects.filter(election=election, has_voted=True).count()
    not_voted_count = total_people - voted_count

    return render(request, 'app/election_list.html', {
        'election': election,
        'page_obj': page_obj,
        'search': search,
        'vote_filter': vote_filter,
        'total_people': total_people,
        'voted_count': voted_count,
        'not_voted_count': not_voted_count,
        'participation_rate': round((voted_count / total_people * 100) if total_people > 0 else 0, 1),
    })


@require_http_methods(["GET"])
def ui_election_quick_mark(request, election_id):
    """Hızlı işaretleme sayfası - Tek tek oy işaretleme"""
    election = get_object_or_404(Election, id=election_id)

    # İstatistikler
    total_people = LawyerPerson.objects.filter(active=True).count()
    voted_count = ElectionVote.objects.filter(election=election, has_voted=True).count()
    not_voted_count = total_people - voted_count

    return render(request, 'app/election_quick_mark.html', {
        'election': election,
        'total_people': total_people,
        'voted_count': voted_count,
        'not_voted_count': not_voted_count,
        'participation_rate': round((voted_count / total_people * 100) if total_people > 0 else 0, 1),
    })
