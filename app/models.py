from django.utils import timezone

from django.db import models


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
