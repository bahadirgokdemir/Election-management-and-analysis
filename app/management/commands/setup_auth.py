"""
Yetkilendirme sistemi ilk kurulum komutu
Mevcut kullanicilara profil olusturur ve admin kullanici ekler.
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from app.models import UserProfile


class Command(BaseCommand):
    help = 'Yetkilendirme sistemi ilk kurulumu - mevcut kullanicilara profil olusturur'

    def add_arguments(self, parser):
        parser.add_argument(
            '--admin-username',
            type=str,
            default='admin',
            help='Olusturulacak admin kullanicinin adi (default: admin)'
        )
        parser.add_argument(
            '--admin-password',
            type=str,
            help='Admin sifresi (belirtilmezse olusturulmaz)'
        )
        parser.add_argument(
            '--admin-email',
            type=str,
            default='admin@example.com',
            help='Admin e-posta adresi'
        )

    def handle(self, *args, **options):
        self.stdout.write('Yetkilendirme sistemi kuruluyor...\n')

        # Mevcut kullanicilara profil olustur
        users_without_profile = User.objects.filter(profile__isnull=True)
        created_count = 0

        for user in users_without_profile:
            role = UserProfile.ROLE_ADMIN if user.is_superuser else UserProfile.ROLE_READ_ONLY
            UserProfile.objects.create(user=user, role=role)
            created_count += 1
            self.stdout.write(f'  Profil olusturuldu: {user.username} ({role})')

        if created_count > 0:
            self.stdout.write(self.style.SUCCESS(f'\n{created_count} kullanici icin profil olusturuldu.'))
        else:
            self.stdout.write('Tum kullanicilarin zaten profili var.\n')

        # Admin kullanici olustur (sifre verilmisse)
        admin_username = options['admin_username']
        admin_password = options['admin_password']
        admin_email = options['admin_email']

        if admin_password:
            if User.objects.filter(username=admin_username).exists():
                self.stdout.write(self.style.WARNING(f'\n"{admin_username}" kullanicisi zaten mevcut.'))
            else:
                user = User.objects.create_superuser(
                    username=admin_username,
                    email=admin_email,
                    password=admin_password
                )
                self.stdout.write(self.style.SUCCESS(f'\nAdmin kullanici olusturuldu: {admin_username}'))

        # Profil istatistikleri
        self.stdout.write('\n--- Profil Istatistikleri ---')
        for role_key, role_name in UserProfile.ROLE_CHOICES:
            count = UserProfile.objects.filter(role=role_key).count()
            self.stdout.write(f'  {role_name}: {count} kullanici')

        total_users = User.objects.count()
        total_profiles = UserProfile.objects.count()
        self.stdout.write(f'\n  Toplam kullanici: {total_users}')
        self.stdout.write(f'  Toplam profil: {total_profiles}')

        if total_users != total_profiles:
            self.stdout.write(self.style.WARNING(
                f'\n  UYARI: {total_users - total_profiles} kullanicinin profili eksik!'
            ))

        self.stdout.write(self.style.SUCCESS('\nKurulum tamamlandi!'))
