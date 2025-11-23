from django.contrib import admin
from .models import Lawyer, StatusOption, Person, LawyerPerson, UploadBatch, UploadRowStaging, BatchDiff, AuditLog, Election, ElectionVote


@admin.register(Lawyer)
class LawyerAdmin(admin.ModelAdmin):
    list_display = ("sicil_no", "ad", "soyad", "created_at")
    search_fields = ("sicil_no", "ad", "soyad")


@admin.register(StatusOption)
class StatusOptionAdmin(admin.ModelAdmin):
    list_display = ("key", "label", "color")
    search_fields = ("key", "label")


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ("kisi_sicilno", "ad", "soyad", "mail", "ilce", "cevap_status")
    search_fields = ("kisi_sicilno", "ad", "soyad", "mail")
    list_filter = ("cevap_status", "ilce")


@admin.register(LawyerPerson)
class LawyerPersonAdmin(admin.ModelAdmin):
    list_display = ("lawyer", "kisi_sicilno", "ad", "soyad", "active", "updated_at")
    list_filter = ("lawyer", "active", "cevap_status")
    search_fields = ("kisi_sicilno", "ad", "soyad", "mail")


admin.site.register(UploadBatch)
admin.site.register(UploadRowStaging)
admin.site.register(BatchDiff)
admin.site.register(AuditLog)


@admin.register(Election)
class ElectionAdmin(admin.ModelAdmin):
    list_display = ("name", "election_date", "is_active", "allow_external_registration", "created_at")
    list_filter = ("is_active", "election_date")
    search_fields = ("name", "description")
    ordering = ("-election_date",)


@admin.register(ElectionVote)
class ElectionVoteAdmin(admin.ModelAdmin):
    list_display = ("election", "get_kisi_sicilno", "get_kisi_name", "has_voted", "voted_at", "recorded_by")
    list_filter = ("election", "has_voted")
    search_fields = ("lawyerperson__kisi_sicilno", "lawyerperson__ad", "lawyerperson__soyad", "recorded_by")
    readonly_fields = ("created_at", "updated_at")

    def get_kisi_sicilno(self, obj):
        return obj.lawyerperson.kisi_sicilno
    get_kisi_sicilno.short_description = "Sicil No"

    def get_kisi_name(self, obj):
        return f"{obj.lawyerperson.ad} {obj.lawyerperson.soyad}"
    get_kisi_name.short_description = "Ad Soyad"
