from django.utils import timezone
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.account.models import User

SYSTEM_USER_CODE = 0


def get_acting_user(request):
    if request.user and request.user.is_authenticated:
        return request.user
    return User.all_objects.get(code=SYSTEM_USER_CODE)


class DeleteSerializer(serializers.Serializer):
    delete_explanation = serializers.CharField(max_length=500, allow_blank=False)


class ArchivedNameMixin:
    archived_unique_fields = ()

    def validate(self, attrs):
        for field in self.archived_unique_fields:
            if field == "name" and field in attrs and isinstance(attrs[field], str):
                attrs[field] = attrs[field].strip().lower()
        attrs = super().validate(attrs)
        self._archived_instance = None
        filters = {
            field: attrs[field]
            for field in self.archived_unique_fields
            if field in attrs
        }
        if filters:
            self._archived_instance = self.Meta.model.all_objects.filter(
                deleted_at__isnull=False,
                **filters,
            ).first()
        return attrs

    def create(self, validated_data):
        archived = getattr(self, "_archived_instance", None)
        if archived is None:
            return super().create(validated_data)

        acting_user = validated_data.pop("created_by", None)
        for field, value in validated_data.items():
            setattr(archived, field, value)
        archived.restore()
        archived.updated_by = acting_user
        archived.updated_at = timezone.now()
        archived.save(update_fields=[
            *validated_data.keys(),
            "deleted_by",
            "deleted_at",
            "delete_explanation",
            "updated_by",
            "updated_at",
        ])
        return archived


class AuditableViewSet(viewsets.ModelViewSet):
    def perform_create(self, serializer):
        serializer.save(created_by=get_acting_user(self.request))

    def perform_update(self, serializer):
        serializer.save(
            updated_by=get_acting_user(self.request),
            updated_at=timezone.now(),
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        body = DeleteSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            instance.soft_delete(
                user=get_acting_user(request),
                explanation=body.validated_data["delete_explanation"],
            )
        except ValueError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="restore")
    def restore(self, request, pk=None):
        model = self.queryset.model
        try:
            instance = model.all_objects.get(pk=pk, deleted_at__isnull=False)
        except (model.DoesNotExist, ValueError):
            return Response(
                {"detail": "No existe un registro eliminado con ese id."},
                status=status.HTTP_404_NOT_FOUND,
            )
        instance.restore()
        instance.updated_by = get_acting_user(request)
        instance.updated_at = timezone.now()
        instance.save(update_fields=["updated_by", "updated_at"])
        return Response(self.get_serializer(instance).data)
