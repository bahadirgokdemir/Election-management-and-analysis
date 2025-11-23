from django.urls import path
from .views_ui import (
    ui_dashboard, ui_lawyers, ui_people, ui_upload,
    ui_diff_preview, ui_approve_batch, ui_people_export,
    ui_download_template_csv, ui_download_template_xlsx,
    ui_approve_selected, ui_lawyer_people,
    ui_people_export_preview, ui_people_export_download,
    ui_person_edit, ui_person_relation_delete, ui_lawyer_delete,
    ui_unique_people, ui_unique_person_detail,
    ui_person_analytics,
)
from .views_election import (
    ui_elections, ui_election_create, ui_election_activate,
    ui_election_toggle_registration, ui_election_voting,
    ui_election_mark_vote, ui_election_stats,
    ui_election_voting_data, ui_election_delete,
    ui_election_check, ui_election_dashboard, ui_election_list,
    ui_election_quick_mark,
)

urlpatterns = [
    path('', ui_dashboard, name='ui_dashboard'),
    path('lawyers/', ui_lawyers, name='ui_lawyers'),
    path('people/', ui_people, name='ui_people'),
    path('people/export/', ui_people_export, name='ui_people_export'),
    path('people/export/preview/', ui_people_export_preview, name='ui_people_export_preview'),
    path('people/export/download/', ui_people_export_download, name='ui_people_export_download'),
    path('upload/', ui_upload, name='ui_upload'),
    path('upload/<int:batch_id>/diff/', ui_diff_preview, name='ui_diff_preview'),
    path('upload/<int:batch_id>/approve/', ui_approve_batch, name='ui_approve_batch'),
    path('lawyers/<int:lawyer_id>/', ui_lawyer_people, name='ui_lawyer_people'),

    # Şablon indirme
    path('download/template/csv/', ui_download_template_csv, name='ui_download_template_csv'),
    path('download/template/xlsx/', ui_download_template_xlsx, name='ui_download_template_xlsx'),

    # Seçili satırları uygula
    path('upload/<int:batch_id>/approve-selected/', ui_approve_selected, name='ui_approve_selected'),

    # Kişi düzenle, sil ve analiz
    path('people/<int:person_id>/edit/', ui_person_edit, name='ui_person_edit'),
    path('people/relation/<int:lawyerperson_id>/delete/', ui_person_relation_delete, name='ui_person_relation_delete'),
    path('people/<str:kisi_sicilno>/analytics/', ui_person_analytics, name='ui_person_analytics'),

    # Avukat sil
    path('lawyers/<int:lawyer_id>/delete/', ui_lawyer_delete, name='ui_lawyer_delete'),

    # Benzersiz kişiler
    path('unique-people/', ui_unique_people, name='ui_unique_people'),
    path('unique-people/<str:kisi_sicilno>/detail/', ui_unique_person_detail, name='ui_unique_person_detail'),

    # Seçim günü yönetimi
    path('elections/', ui_elections, name='ui_elections'),
    path('elections/create/', ui_election_create, name='ui_election_create'),
    path('elections/<int:election_id>/activate/', ui_election_activate, name='ui_election_activate'),
    path('elections/<int:election_id>/toggle-registration/', ui_election_toggle_registration, name='ui_election_toggle_registration'),
    path('elections/<int:election_id>/delete/', ui_election_delete, name='ui_election_delete'),
    path('elections/<int:election_id>/voting/', ui_election_voting, name='ui_election_voting'),
    path('elections/<int:election_id>/mark-vote/', ui_election_mark_vote, name='ui_election_mark_vote'),
    path('elections/<int:election_id>/stats/', ui_election_stats, name='ui_election_stats'),

    # Seçim günü sayfaları
    path('elections/<int:election_id>/dashboard/', ui_election_dashboard, name='ui_election_dashboard'),
    path('elections/<int:election_id>/list/', ui_election_list, name='ui_election_list'),
    path('elections/<int:election_id>/quick-mark/', ui_election_quick_mark, name='ui_election_quick_mark'),
    path('elections/<int:election_id>/check/', ui_election_check, name='ui_election_check'),
    path('elections/<int:election_id>/voting-data/', ui_election_voting_data, name='ui_election_voting_data'),
]
