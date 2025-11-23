# app/management/commands/seed_status.py
from django.core.management.base import BaseCommand
from app.models import StatusOption

DEFAULTS = [
    ("geliyor", "Geliyor", "#22c55e"),
    ("gelmiyor", "Gelmiyor", "#ef4444"),
    ("nötr", "Nötr", "#a3a3a3"),
]

class Command(BaseCommand):
    help = 'Varsayılan cevapDurumu seçeneklerini yükler'

    def handle(self, *args, **options):
        created_any = False
        for key, label, color in DEFAULTS:
            obj, created = StatusOption.objects.get_or_create(
                key=key,
                defaults={"label": label, "color": color}
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'Olusturuldu: {obj.key}'))
                created_any = True
            else:
                self.stdout.write(f'Zaten var: {obj.key}')
        if not created_any:
            self.stdout.write(self.style.WARNING('Yeni kayit yok.'))
        else:
            self.stdout.write(self.style.SUCCESS('Status seçenekleri hazır.'))
