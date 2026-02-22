"""
Public view'lar - Giris gerektirmeyen avukat oy durumu kontrolu
"""
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from django.utils import timezone
from django.db.models import Q

from .models import LawyerAccessCode, LawyerPerson, ElectionVote


@require_http_methods(["GET", "POST"])
def lawyer_voting_check(request):
    """
    Avukat oy durumu kontrol sayfasi.
    Public erisilebilir - erisim kodu ile giris yapilir.
    """
    context = {
        'code_entered': False,
        'valid_code': False,
        'error': None,
    }

    # POST - Kod kontrolu
    if request.method == "POST":
        code = request.POST.get('code', '').strip()

        if not code:
            context['error'] = 'Erisim kodu giriniz.'
            return render(request, 'app/public/lawyer_voting_check.html', context)

        # Kodu bul
        try:
            access_code = LawyerAccessCode.objects.select_related('lawyer', 'election').get(code=code)
        except LawyerAccessCode.DoesNotExist:
            context['error'] = 'Gecersiz erisim kodu.'
            return render(request, 'app/public/lawyer_voting_check.html', context)

        # Kod gecerli mi?
        if not access_code.is_valid():
            if not access_code.is_active:
                context['error'] = 'Bu erisim kodu iptal edilmis.'
            elif timezone.now() > access_code.expires_at:
                context['error'] = 'Bu erisim kodunun suresi dolmus.'
            return render(request, 'app/public/lawyer_voting_check.html', context)

        # Kullanim sayisini artir
        access_code.increment_use_count()

        # Avukata ait kisilerin oy durumlarini getir
        lawyer = access_code.lawyer
        election = access_code.election

        # Bu avukata ait aktif kisiler
        people = LawyerPerson.objects.filter(
            lawyer=lawyer,
            active=True
        ).order_by('soyad', 'ad')

        # Oy durumlarini getir
        votes = {
            vote.lawyerperson_id: vote
            for vote in ElectionVote.objects.filter(
                election=election,
                lawyerperson__in=people
            )
        }

        # Kisileri oy durumlariyla birlikte hazirla
        people_with_votes = []
        voted_count = 0
        not_voted_count = 0

        for person in people:
            vote = votes.get(person.id)
            has_voted = vote.has_voted if vote else False

            if has_voted:
                voted_count += 1
            else:
                not_voted_count += 1

            people_with_votes.append({
                'person': person,
                'has_voted': has_voted,
                'voted_at': vote.voted_at if vote and vote.voted_at else None,
            })

        total = len(people_with_votes)
        participation_rate = round((voted_count / total * 100) if total > 0 else 0, 1)

        context.update({
            'code_entered': True,
            'valid_code': True,
            'lawyer': lawyer,
            'election': election,
            'people': people_with_votes,
            'stats': {
                'total': total,
                'voted': voted_count,
                'not_voted': not_voted_count,
                'participation_rate': participation_rate,
            }
        })

    return render(request, 'app/public/lawyer_voting_check.html', context)


@require_http_methods(["POST"])
def lawyer_voting_check_api(request):
    """
    Avukat oy durumu kontrol API'si.
    JSON olarak oy durumlarini dondurur.
    """
    code = request.POST.get('code', '').strip()

    if not code:
        return JsonResponse({'success': False, 'error': 'Erisim kodu giriniz.'}, status=400)

    # Kodu bul
    try:
        access_code = LawyerAccessCode.objects.select_related('lawyer', 'election').get(code=code)
    except LawyerAccessCode.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Gecersiz erisim kodu.'}, status=404)

    # Kod gecerli mi?
    if not access_code.is_valid():
        if not access_code.is_active:
            return JsonResponse({'success': False, 'error': 'Bu erisim kodu iptal edilmis.'}, status=403)
        elif timezone.now() > access_code.expires_at:
            return JsonResponse({'success': False, 'error': 'Bu erisim kodunun suresi dolmus.'}, status=403)

    # Kullanim sayisini artir
    access_code.increment_use_count()

    # Avukata ait kisilerin oy durumlarini getir
    lawyer = access_code.lawyer
    election = access_code.election

    # Bu avukata ait aktif kisiler
    people = LawyerPerson.objects.filter(
        lawyer=lawyer,
        active=True
    ).order_by('soyad', 'ad')

    # Oy durumlarini getir
    votes = {
        vote.lawyerperson_id: vote
        for vote in ElectionVote.objects.filter(
            election=election,
            lawyerperson__in=people
        )
    }

    # Kisileri oy durumlariyla birlikte hazirla
    people_data = []
    voted_count = 0
    not_voted_count = 0

    for person in people:
        vote = votes.get(person.id)
        has_voted = vote.has_voted if vote else False

        if has_voted:
            voted_count += 1
        else:
            not_voted_count += 1

        people_data.append({
            'id': person.id,
            'kisi_sicilno': person.kisi_sicilno,
            'ad': person.ad,
            'soyad': person.soyad,
            'has_voted': has_voted,
            'voted_at': vote.voted_at.strftime('%H:%M') if vote and vote.voted_at else None,
        })

    total = len(people_data)
    participation_rate = round((voted_count / total * 100) if total > 0 else 0, 1)

    return JsonResponse({
        'success': True,
        'lawyer': {
            'sicil_no': lawyer.sicil_no,
            'ad': lawyer.ad,
            'soyad': lawyer.soyad,
        },
        'election': {
            'name': election.name,
            'date': election.election_date.strftime('%d.%m.%Y'),
        },
        'people': people_data,
        'stats': {
            'total': total,
            'voted': voted_count,
            'not_voted': not_voted_count,
            'participation_rate': participation_rate,
        }
    })
