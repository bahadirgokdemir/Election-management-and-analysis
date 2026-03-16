from django.utils import timezone

from django.db import models
from django.contrib.auth.models import User
import secrets


class Lawyer(models.Model):
    sicil_no = models.CharField(max_length=64, unique=True)
    ad = models.CharField(max_length=128)
    soyad = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self): return f"{self.sicil_no} - {self.ad} {self.soyad}"


class StatusOption(models.Model):
    key = models.CharField(max_length=64, unique=True)
    label = models.CharField(max_length=64)
    color = models.CharField(max_length=16, blank=True, null=True)

    def __str__(self): return self.label


class Person(models.Model):
    kisi_sicilno = models.CharField(max_length=64)
    ad = models.CharField(max_length=128)
    soyad = models.CharField(max_length=128)
    telno = models.CharField(max_length=64, blank=True, null=True)
    mail = models.EmailField(max_length=256, blank=True, null=True)
    ilce = models.CharField(max_length=128, blank=True, null=True)
    adres_aciklama = models.TextField(blank=True, null=True)
    notlar = models.TextField(blank=True, null=True)
    cevap_status = models.ForeignKey(StatusOption, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['kisi_sicilno']),
            models.Index(fields=['ad', 'soyad']),
        ]

    def __str__(self): return f"{self.kisi_sicilno} - {self.ad} {self.soyad}"


class LawyerPerson(models.Model):
    """
    Her avukatın kişi listesinin bağımsız kopyası.
    Person tablosu sadece referans amaçlı kullanılır.
    Tüm gerçek veriler burada saklanır.
    """
    lawyer = models.ForeignKey(Lawyer, on_delete=models.CASCADE)
    person = models.ForeignKey(Person, on_delete=models.CASCADE)

    # Kişi sicil no (unique key)
    kisi_sicilno = models.CharField(max_length=64, default='')

    # Kişi bilgileri (her avukat için bağımsız)
    ad = models.CharField(max_length=128, default='', blank=True)
    soyad = models.CharField(max_length=128, default='', blank=True)
    telno = models.CharField(max_length=64, blank=True, null=True)
    mail = models.EmailField(max_length=256, blank=True, null=True)
    ilce = models.CharField(max_length=128, blank=True, null=True)
    adres_aciklama = models.TextField(blank=True, null=True)
    notlar = models.TextField(blank=True, null=True)
    cevap_status = models.ForeignKey(StatusOption, on_delete=models.SET_NULL, null=True, blank=True)

    # Metadata
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('lawyer', 'kisi_sicilno')
        indexes = [
            models.Index(fields=['lawyer', 'active']),
            models.Index(fields=['kisi_sicilno']),
        ]

    def __str__(self):
        return f"{self.lawyer.sicil_no} - {self.kisi_sicilno} - {self.ad} {self.soyad}"


class UploadBatch(models.Model):
    STAGED = 'STAGED'
    APPLIED = 'APPLIED'
    REJECTED = 'REJECTED'
    STATUS_CHOICES = [(STAGED, STAGED), (APPLIED, APPLIED), (REJECTED, REJECTED)]

    lawyer = models.ForeignKey(Lawyer, on_delete=models.CASCADE)
    original_filename = models.CharField(max_length=512)
    file_path = models.CharField(max_length=1024, blank=True, null=True)
    row_count = models.IntegerField(default=0)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STAGED)
    created_by = models.CharField(max_length=128, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)  # Baro uyarıları ve diğer notlar için


class UploadRow(models.Model):
    """
    Yüklenen dosyadaki her bir satırın staging karşılığı.
    Diff, bu tablo ile mevcut sistem Person/LawyerPerson kayıtlarını karşılaştırır.
    """
    batch = models.ForeignKey(UploadBatch, on_delete=models.CASCADE, related_name='rows')

    # Excel/CSV kolonları (normalize edilmiş)
    kisi_sicilno = models.CharField(max_length=64)
    ad = models.CharField(max_length=128, blank=True, default='')
    soyad = models.CharField(max_length=128, blank=True, default='')
    telno = models.CharField(max_length=64, blank=True, default='')
    mail = models.EmailField(blank=True, default='')
    ilce = models.CharField(max_length=128, blank=True, default='')
    adres_aciklama = models.TextField(blank=True, default='')
    notlar = models.TextField(blank=True, default='')

    # status değerini string key olarak tutuyoruz (örn: geliyor/gelmiyor/nötr)
    cevap_status_key = models.CharField(max_length=64, blank=True, default='')

    row_index = models.PositiveIntegerField(default=0)  # opsiyonel: dosyadaki satır numarası
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=['batch', 'kisi_sicilno']),
        ]

    def __str__(self):
        return f"Batch {self.batch_id}  Row {self.row_index}  {self.kisi_sicilno}"


class UploadRowStaging(models.Model):
    batch = models.ForeignKey(UploadBatch, on_delete=models.CASCADE)
    kisi_sicilno = models.CharField(max_length=64)
    ad = models.CharField(max_length=128)
    soyad = models.CharField(max_length=128)
    telno = models.CharField(max_length=64, blank=True, null=True)
    mail = models.CharField(max_length=256, blank=True, null=True)
    ilce = models.CharField(max_length=128, blank=True, null=True)
    adres_aciklama = models.TextField(blank=True, null=True)
    notlar = models.TextField(blank=True, null=True)
    cevap_status_key = models.CharField(max_length=64, blank=True, null=True)


class BatchDiff(models.Model):
    batch = models.ForeignKey(UploadBatch, on_delete=models.CASCADE)
    added_count = models.IntegerField(default=0)
    removed_count = models.IntegerField(default=0)
    changed_count = models.IntegerField(default=0)
    diff_json = models.JSONField()


class AuditLog(models.Model):
    entity = models.CharField(max_length=64)
    entity_id = models.BigIntegerField()
    action = models.CharField(max_length=32)
    before_json = models.JSONField(null=True, blank=True)
    after_json = models.JSONField(null=True, blank=True)
    actor = models.CharField(max_length=128, null=True, blank=True)
    at = models.DateTimeField(auto_now_add=True)


class Election(models.Model):
    """
    Seçim tanımı - Birden fazla seçim oluşturulabilir (ön seçim, ana seçim vb.)
    """
    name = models.CharField(max_length=256, help_text="Seçim adı (örn: Ön Seçim 2025, Ana Seçim 2025)")
    election_date = models.DateField(help_text="Seçim tarihi")
    is_active = models.BooleanField(default=False, help_text="Aktif seçim günü (sadece bir seçim aktif olabilir)")
    allow_external_registration = models.BooleanField(default=True, help_text="Dışarıdan kayıt kabul edilsin mi?")
    description = models.TextField(blank=True, null=True, help_text="Seçim açıklaması")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-election_date']
        indexes = [
            models.Index(fields=['is_active']),
            models.Index(fields=['election_date']),
        ]

    def __str__(self):
        return f"{self.name} ({self.election_date})"

    def save(self, *args, **kwargs):
        # Bir seçim aktif yapılırsa diğerlerini pasif yap
        if self.is_active:
            Election.objects.exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)


class ElectionVote(models.Model):
    """
    Seçim günü oy kayıtları - Kişilerin oy verip vermediğini takip eder
    """
    election = models.ForeignKey(Election, on_delete=models.CASCADE, related_name='votes')
    lawyerperson = models.ForeignKey(LawyerPerson, on_delete=models.CASCADE, help_text="Oy veren kişi")

    # Oy verme durumu
    has_voted = models.BooleanField(default=False, help_text="Oy verdi mi?")
    voted_at = models.DateTimeField(null=True, blank=True, help_text="Oy verme zamanı")

    # Sandık görevlisi bilgisi
    recorded_by = models.CharField(max_length=256, blank=True, null=True, help_text="Kaydı yapan görevli")
    notes = models.TextField(blank=True, null=True, help_text="Notlar")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('election', 'lawyerperson')
        indexes = [
            models.Index(fields=['election', 'has_voted']),
            models.Index(fields=['election', 'lawyerperson']),
        ]

    def __str__(self):
        status = "Oy Verdi" if self.has_voted else "Oy Vermedi"
        return f"{self.election.name} - {self.lawyerperson.kisi_sicilno} - {status}"


class BaroLawyer(models.Model):
    """
    Tüm baro kayıtları - Aktif.xlsx dosyasından yüklenen avukat bilgileri
    """
    sicil_no = models.CharField(max_length=64, unique=True, db_index=True, help_text="Avukat sicil numarası")
    ad = models.CharField(max_length=128, help_text="Avukat adı")
    soyad = models.CharField(max_length=128, help_text="Avukat soyadı")
    tel = models.CharField(max_length=64, blank=True, default='', help_text="Telefon numarası")
    mail = models.EmailField(max_length=256, blank=True, default='', help_text="E-posta adresi")
    adres = models.TextField(blank=True, default='', help_text="Adres bilgisi")
    uye = models.CharField(max_length=64, blank=True, default='', help_text="Üyelik durumu (Aktif/Pasif)")
    cinsiyet = models.CharField(max_length=8, blank=True, default='', help_text="Cinsiyeti (E/K)")
    mesleğe_baslama = models.CharField(max_length=64, blank=True, default='', help_text="Mesleğe başlama tarihi")
    ilce = models.CharField(max_length=128, blank=True, default='', help_text="İlçe")
    dogum_yeri = models.CharField(max_length=128, blank=True, default='', help_text="Doğum yeri")
    dogum_tarihi = models.CharField(max_length=64, blank=True, default='', help_text="Doğum tarihi")
    mahalle_koy = models.CharField(max_length=128, blank=True, default='', help_text="Mahalle/Köy")
    nufus_ilce = models.CharField(max_length=128, blank=True, default='', help_text="Nüfus ilçe")
    nufus_il = models.CharField(max_length=128, blank=True, default='', help_text="Nüfus il")

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sicil_no']
        indexes = [
            models.Index(fields=['sicil_no']),
            models.Index(fields=['ad', 'soyad']),
            models.Index(fields=['mail']),
        ]
        verbose_name = 'Baro Avukatı'
        verbose_name_plural = 'Baro Avukatları'

    def __str__(self):
        return f"{self.sicil_no} - {self.ad} {self.soyad}"

    @property
    def full_name(self):
        return f"{self.ad} {self.soyad}"


class BaroLawyerTag(models.Model):
    """
    Baro avukatlarına etiket - Kara liste veya 'Beyaz Liste' işaretlemesi
    """
    BLACKLIST = 'blacklist'
    WHITELIST = 'whitelist'
    TAG_CHOICES = [
        (BLACKLIST, 'Kara Liste'),
        (WHITELIST, 'Beyaz Liste'),
    ]

    baro_lawyer = models.OneToOneField(BaroLawyer, on_delete=models.CASCADE, related_name='tag')
    tag_type = models.CharField(max_length=16, choices=TAG_CHOICES)
    note = models.TextField(blank=True, null=True, help_text="Etiketleme nedeni / not")
    created_by = models.CharField(max_length=128, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['tag_type']),
        ]
        verbose_name = 'Baro Avukat Etiketi'
        verbose_name_plural = 'Baro Avukat Etiketleri'

    def __str__(self):
        return f"{self.baro_lawyer.sicil_no} - {self.get_tag_type_display()}"


class CommitteeMembership(models.Model):
    """
    Kurul üyelikleri - Baro_Merkezler_vs.xlsx dosyasından yüklenir
    Bir avukat birden fazla kurulda üye olabilir
    """
    gorev = models.CharField(max_length=256, help_text="Görev/Kurul adı")
    sicil_no = models.CharField(max_length=64, db_index=True, help_text="Avukat sicil numarası")
    ad_soyad = models.CharField(max_length=256, help_text="Ad Soyad")
    baro_lawyer = models.ForeignKey(
        BaroLawyer, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='memberships', help_text="Baro kaydı (varsa)"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['ad_soyad', 'gorev']
        indexes = [
            models.Index(fields=['sicil_no']),
            models.Index(fields=['gorev']),
        ]
        verbose_name = 'Kurul Üyeliği'
        verbose_name_plural = 'Kurul Üyelikleri'

    def __str__(self):
        return f"{self.sicil_no} - {self.ad_soyad} - {self.gorev}"


class UserProfile(models.Model):
    """
    Kullanici profili - Rol tabanli yetkilendirme icin
    """
    ROLE_ADMIN = 'admin'
    ROLE_DATA_UPLOADER = 'data_uploader'
    ROLE_READ_ONLY = 'read_only'

    ROLE_CHOICES = [
        (ROLE_ADMIN, 'Admin'),
        (ROLE_DATA_UPLOADER, 'Veri Yukleyici'),
        (ROLE_READ_ONLY, 'Sadece Okuma'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_READ_ONLY)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Kullanici Profili'
        verbose_name_plural = 'Kullanici Profilleri'

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"

    def is_admin(self):
        return self.role == self.ROLE_ADMIN or self.user.is_superuser

    def is_uploader(self):
        return self.role in [self.ROLE_ADMIN, self.ROLE_DATA_UPLOADER] or self.user.is_superuser

    def can_read(self):
        return True  # Tum roller okuyabilir


class LawyerAccessCode(models.Model):
    """
    Avukat erisim kodu - Avukatlarin kendi kisi listelerinin oy durumlarini gormesi icin
    """
    code = models.CharField(max_length=32, unique=True, db_index=True)
    lawyer = models.ForeignKey(Lawyer, on_delete=models.CASCADE, related_name='access_codes')
    election = models.ForeignKey(Election, on_delete=models.CASCADE, related_name='access_codes')

    expires_at = models.DateTimeField(help_text="Kodun gecerlilik suresi")
    is_active = models.BooleanField(default=True, help_text="Kod aktif mi?")
    use_count = models.IntegerField(default=0, help_text="Kod kac kez kullanildi")

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_access_codes')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Avukat Erisim Kodu'
        verbose_name_plural = 'Avukat Erisim Kodlari'
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['lawyer', 'election']),
            models.Index(fields=['is_active', 'expires_at']),
        ]

    def __str__(self):
        return f"{self.lawyer.sicil_no} - {self.election.name} - {self.code[:8]}..."

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = secrets.token_urlsafe(16)
        super().save(*args, **kwargs)

    def is_valid(self):
        """Kodun gecerli olup olmadigini kontrol et"""
        if not self.is_active:
            return False
        if timezone.now() > self.expires_at:
            return False
        return True

    def increment_use_count(self):
        """Kullanim sayisini artir"""
        self.use_count += 1
        self.save(update_fields=['use_count', 'updated_at'])
