from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import LawyerViewSet, StatusOptionViewSet, PersonViewSet


router = DefaultRouter()
router.register(r'lawyers', LawyerViewSet, basename='lawyers')
router.register(r'status-options', StatusOptionViewSet, basename='status-options')
router.register(r'people', PersonViewSet, basename='people')


urlpatterns = [ path('', include(router.urls)) ]
from .views import UploadViewSet
router.register(r'uploads', UploadViewSet, basename='uploads')

from .views import ReportsViewSet
router.register(r'reports', ReportsViewSet, basename='reports')