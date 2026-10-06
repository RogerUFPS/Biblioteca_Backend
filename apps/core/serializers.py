from dataclasses import dataclass
from datetime import date, time
from typing import Any

from .models import AuditableModel
from django.utils import timezone


@dataclass(frozen=True)
class RelationConfig:
    """
    Configuración declarativa de una relación mediante tabla intermedia
    con soporte de borrado lógico.

    Una relación puede ser:

    - simple: extra_fields=()
    - enriquecida: extra_fields contiene los campos propios del vínculo
    """

    data_field: str
    through_model: type[AuditableModel]
    relation_field: str
    extra_fields: tuple[str, ...] = ()
    ordering: tuple[str, ...] = ()
    delete_explanation: str | None = None


class SoftDeleteRelationSyncMixin:
    """
    Mixin reutilizable para sincronizar relaciones mediante tablas
    intermedias auditables que implementan Soft Delete.

    Soporta relaciones simples y relaciones enriquecidas utilizando
    un único algoritmo de sincronización.

    Relación simple:

        Journal -> Language

        languages = [1, 2, 3]

    Relación enriquecida:

        Journal -> Platform

        platforms = [
            {
                "platform": 1,
                "start_period": "2026-01-01",
                "finish_period": "2026-12-31",
                "has_full_text": True,
            }
        ]

    La atomicidad de la operación completa debe garantizarla el
    serializer concreto mediante transaction.atomic().
    """

    relation_config: tuple[RelationConfig, ...] = ()
    relation_parent_field: str | None = None

    relation_delete_explanation = (
        "Relación eliminada durante la actualización."
    )

    def _get_parent_lookup(self, parent: Any) -> dict[str, Any]:
        """
        Construye el filtro utilizado para localizar las relaciones
        pertenecientes a la entidad principal.
        """
        if not self.relation_parent_field:
            raise NotImplementedError(
                "relation_parent_field debe estar definido."
            )

        return {
            self.relation_parent_field: parent,
        }

    def _get_relation_user(self, parent: Any) -> Any:
        """
        Obtiene el usuario responsable de la modificación de la relación.

        En una actualización se utiliza updated_by; durante una creación
        se utiliza created_by.
        """
        user = (
            getattr(parent, "updated_by", None)
            or getattr(parent, "created_by", None)
        )

        if user is None:
            raise ValueError(
                "No fue posible determinar el usuario responsable "
                "de la modificación de la relación."
            )

        return user

    def _get_delete_explanation(
        self,
        config: RelationConfig,
    ) -> str:
        """
        Obtiene la explicación específica de eliminación de la relación.
        """
        return (
            config.delete_explanation
            or self.relation_delete_explanation
        )

    def _extract_relation_data(
        self,
        validated_data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Extrae únicamente las relaciones que fueron enviadas
        explícitamente en la petición.

        Esto permite distinguir correctamente entre:

        - campo omitido: no modificar la relación;
        - lista vacía: eliminar todas las relaciones activas.
        """
        relation_data = {}

        for config in self.relation_config:
            if config.data_field in validated_data:
                relation_data[config.data_field] = validated_data.pop(
                    config.data_field
                )

        return relation_data

    def _normalize_relation_data(
        self,
        relation_data: list[Any],
        config: RelationConfig,
    ) -> dict[Any, dict[str, Any]]:
        """
        Normaliza relaciones simples y enriquecidas al mismo formato:

            {
                related_id: data
            }

        Para relaciones simples, data contiene únicamente la entidad
        relacionada.

        Para relaciones enriquecidas, data conserva la entidad relacionada
        y los atributos propios de la relación.
        """
        normalized = {}

        if config.extra_fields:
            for item in relation_data:
                related_object = item[config.relation_field]

                normalized[related_object.pk] = item

            return normalized

        for related_object in relation_data:
            normalized[related_object.pk] = {
                config.relation_field: related_object,
            }

        return normalized

    def _apply_extra_fields(
        self,
        instance: Any,
        data: dict[str, Any],
        extra_fields: tuple[str, ...],
    ) -> list[str]:
        """
        Aplica únicamente los atributos propios que fueron enviados.

        Los campos omitidos no se modifican, lo cual permite realizar
        correctamente actualizaciones parciales sobre relaciones
        enriquecidas.
        """
        update_fields = []

        for field_name in extra_fields:
            if field_name not in data:
                continue

            value = data[field_name]

            if getattr(instance, field_name) != value:
                setattr(instance, field_name, value)
                update_fields.append(field_name)

        return update_fields

    def _save_relation_update(
        self,
        link: Any,
        user: Any,
        update_fields: list[str],
    ) -> None:
        """
        Guarda una relación modificada actualizando su auditoría.
        """
        link.updated_by = user
        link.updated_at = timezone.now()

        link.save(
            update_fields=[
                *update_fields,
                "updated_by",
                "updated_at",
            ]
        )

    def _restore_relation(
        self,
        link: Any,
        data: dict[str, Any],
        config: RelationConfig,
        user: Any,
    ) -> None:
        """
        Restaura una relación archivada y aplica los atributos enviados.
        """
        link.restore()

        update_fields = self._apply_extra_fields(
            instance=link,
            data=data,
            extra_fields=config.extra_fields,
        )

        self._save_relation_update(
            link=link,
            user=user,
            update_fields=update_fields,
        )

    def _create_relation(
        self,
        parent_lookup: dict[str, Any],
        data: dict[str, Any],
        config: RelationConfig,
        user: Any,
    ) -> None:
        """
        Crea una relación nueva utilizando los atributos propios
        proporcionados en la petición.
        """
        related_object = data[config.relation_field]

        create_data = {
            **parent_lookup,
            config.relation_field: related_object,
            "created_by": user,
        }

        for field_name in config.extra_fields:
            if field_name in data:
                create_data[field_name] = data[field_name]

        config.through_model.objects.create(**create_data)

    def _sync_relation(
        self,
        parent: Any,
        relation_data: list[Any],
        config: RelationConfig,
    ) -> None:
        """
        Sincroniza una relación individual, independientemente de que
        sea simple o enriquecida.
        """
        parent_lookup = self._get_parent_lookup(parent)
        user = self._get_relation_user(parent)

        current_links = config.through_model.objects.filter(
            **parent_lookup
        )

        current_links_by_id: dict[Any, AuditableModel] = {
            getattr(
                link,
                f"{config.relation_field}_id",
            ): link
            for link in current_links
        }

        normalized_relation_data = self._normalize_relation_data(
            relation_data=relation_data,
            config=config,
        )

        current_ids = set(current_links_by_id)
        new_ids = set(normalized_relation_data)

        ids_to_remove = current_ids - new_ids
        ids_to_update = current_ids & new_ids
        ids_to_add = new_ids - current_ids

        # Relaciones que dejaron de existir.
        for related_id in ids_to_remove:
            current_links_by_id[related_id].soft_delete(
                user=user,
                explanation=self._get_delete_explanation(config),
            )

        # Relaciones activas que permanecen.
        for related_id in ids_to_update:
            if not config.extra_fields:
                continue

            link = current_links_by_id[related_id]
            data = normalized_relation_data[related_id]

            update_fields = self._apply_extra_fields(
                instance=link,
                data=data,
                extra_fields=config.extra_fields,
            )

            if update_fields:
                self._save_relation_update(
                    link=link,
                    user=user,
                    update_fields=update_fields,
                )

        # Relaciones nuevas o previamente archivadas.
        for related_id in ids_to_add:
            data = normalized_relation_data[related_id]
            related_object = data[config.relation_field]

            lookup = {
                **parent_lookup,
                config.relation_field: related_object,
            }

            archived_link = (
                config.through_model.all_objects
                .filter(
                    deleted_at__isnull=False,
                    **lookup,
                )
                .first()
            )

            if archived_link is not None:
                self._restore_relation(
                    link=archived_link,
                    data=data,
                    config=config,
                    user=user,
                )
            else:
                self._create_relation(
                    parent_lookup=parent_lookup,
                    data=data,
                    config=config,
                    user=user,
                )

    def _sync_relations(
        self,
        parent: Any,
        relation_data: dict[str, Any],
    ) -> None:
        """
        Sincroniza todas las relaciones configuradas que hayan sido
        incluidas explícitamente en la petición.
        """
        for config in self.relation_config:
            if config.data_field not in relation_data:
                continue

            self._sync_relation(
                parent=parent,
                relation_data=relation_data[config.data_field],
                config=config,
            )

    @staticmethod
    def _represent_extra_value(value: Any) -> Any:
        """
        Convierte valores de fecha/hora a una representación JSON
        estándar sin depender de los campos internos del serializer.

        El resto de valores se devuelve sin modificar para que su
        representación siga dependiendo del serializer/renderer que
        consume el resultado.
        """
        if isinstance(value, (date, time)):
            return value.isoformat()

        return value

    def _represent_relations(
        self,
        instance: Any,
        representation: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Representa todas las relaciones activas configuradas.

        Relaciones simples:

            ["id1", "id2", ...]

        Relaciones enriquecidas:

            [
                {
                    "platform": 1,
                    "start_period": "2026-01-01",
                    "finish_period": "2026-12-31",
                    "has_full_text": True,
                }
            ]
        """
        parent_lookup = self._get_parent_lookup(instance)

        for config in self.relation_config:
            queryset = config.through_model.objects.filter(
                **parent_lookup
            )

            if config.ordering:
                queryset = queryset.order_by(*config.ordering)

            if not config.extra_fields:
                representation[config.data_field] = list(
                    queryset.values_list(
                        f"{config.relation_field}_id",
                        flat=True,
                    )
                )
                continue

            representation[config.data_field] = [
                {
                    config.relation_field: getattr(
                        link,
                        f"{config.relation_field}_id",
                    ),
                    **{
                        field_name: self._represent_extra_value(
                            getattr(link, field_name)
                        )
                        for field_name in config.extra_fields
                    },
                }
                for link in queryset
            ]

        return representation
