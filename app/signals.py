"""
Django sinyalleri - Otomatik islemler icin
"""
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User

from .models import UserProfile


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """
    Yeni kullanici olusturulunca otomatik profil olustur.
    Superuser ise admin rolu ver, degilse read_only.
    """
    if created:
        role = UserProfile.ROLE_ADMIN if instance.is_superuser else UserProfile.ROLE_READ_ONLY
        UserProfile.objects.create(user=instance, role=role)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """
    Kullanici kaydedilince profili de kaydet.
    Profil yoksa olustur.
    """
    try:
        instance.profile.save()
    except UserProfile.DoesNotExist:
        role = UserProfile.ROLE_ADMIN if instance.is_superuser else UserProfile.ROLE_READ_ONLY
        UserProfile.objects.create(user=instance, role=role)
