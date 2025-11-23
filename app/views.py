from rest_framework import viewsets, mixins
from django_filters.rest_framework import DjangoFilterBackend
from .models import Lawyer, StatusOption, Person
from .serializers import LawyerSerializer, StatusOptionSerializer, PersonListSerializer

from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework import status
from rest_framework.response import Response

from .models import UploadBatch
from .serializers import UploadBatchSerializer, DiffResponseSerializer
from .services.importer import parse_and_stage
from .services.diff_service import compute_diff
from .services.apply_service import apply_diff


class LawyerViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    queryset = Lawyer.objects.all().order_by('-id')
    serializer_class = LawyerSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["sicil_no", "ad", "soyad"]


class StatusOptionViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = StatusOption.objects.all().order_by('id')
    serializer_class = StatusOptionSerializer


class PersonViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = Person.objects.select_related('cevap_status').all().order_by('-id')
    serializer_class = PersonListSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["kisi_sicilno", "ad", "soyad", "ilce", "cevap_status__key"]


class UploadViewSet(viewsets.GenericViewSet):
    queryset = UploadBatch.objects.all().order_by('-id')
    serializer_class = UploadBatchSerializer
    parser_classes = [MultiPartParser, FormParser]

    # POST /api/uploads/ (form-data: file, lawyerId)
    def create(self, request, *args, **kwargs):
        file = request.FILES.get('file')
        lawyer_id = int(request.data.get('lawyerId'))
        if not file or not lawyer_id:
            return Response({"detail": "file ve lawyerId zorunlu"}, status=400)

        # 1) Dosyayı staging'e yükle
        batch_id, row_count = parse_and_stage(file, lawyer_id,
                                              created_by=str(request.user) if request.user.is_authenticated else None)

        # 2) Otomatik olarak uygula (approve et)
        actor = str(request.user) if request.user.is_authenticated else None
        result = apply_diff(batch_id, actor=actor)

        # 3) Sonucu döndür
        obj = UploadBatch.objects.get(id=batch_id)
        response_data = UploadBatchSerializer(obj).data
        response_data['apply_result'] = result  # Ekleme/güncelleme sayılarını da göster

        return Response(response_data, status=status.HTTP_201_CREATED)

    # GET /api/uploads/{id}/diff/
    @action(detail=True, methods=['get'])
    def diff(self, request, pk=None):
        diff = compute_diff(int(pk))

        return Response(diff)

    # POST /api/uploads/{id}/approve/
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        result = apply_diff(int(pk), actor=str(request.user) if request.user.is_authenticated else None)

        code = status.HTTP_200_OK if result.get('ok') else status.HTTP_400_BAD_REQUEST
        return Response(result, status=code)


class ReportsViewSet(viewsets.ViewSet):
    @action(detail=False, methods=['get'])
    def overview(self, request):
        from .services.reports import report_overview
        return Response(report_overview())

    @action(detail=False, methods=['get'])
    def by_lawyer(self, request):
        from .services.reports import report_by_lawyer
        lawyer_id = int(request.query_params.get('lawyerId'))
        return Response(report_by_lawyer(lawyer_id))

    @action(detail=False, methods=['get'])
    def status_breakdown(self, request):
        from .services.reports import report_status_breakdown
        key = request.query_params.get('status')
        return Response(report_status_breakdown(key))
