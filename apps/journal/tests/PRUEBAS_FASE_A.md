# Pruebas de la Aplicación `journal` (Fase A)

Estas pruebas documentan y validan el comportamiento integral del módulo `journal` sin autenticación obligatoria del cliente, utilizando el usuario del sistema con `code=0`.

**Estado de validación: 60 pruebas ejecutadas y aprobadas al 100%** dentro del contenedor Docker con PostgreSQL.

---

## Casos Cubiertos por Capas

### 1. Modelos (`apps/journal/tests/test_models.py`)

| Prueba | Resultado Esperado |
| --- | --- |
| `test_journal_creation` | Crea correctamente una revista con ISSN y título, verificando además que el registro quede activo. |
| `test_journal_issn_case_insensitive_unique_constraint` | La base de datos rechaza ISSN duplicados sin importar diferencias entre mayúsculas y minúsculas. |
| `test_journal_soft_delete_and_restore` | Verifica el ciclo de eliminación lógica y restauración de una revista, conservando el registro en `all_objects`. |
| `test_journal_str_representation` | La representación `__str__` de la revista contiene el título y el ISSN. |
| `test_shared_journal_language_unique_constraint` | La base de datos impide duplicar una relación entre revista e idioma. |
| `test_shared_journal_country_unique_constraint` | La base de datos impide duplicar una relación entre revista y país. |
| `test_shared_journal_knowledge_area_unique_constraint` | La base de datos impide duplicar una relación entre revista y área del conocimiento. |
| `test_shared_journal_material_type_unique_constraint` | La base de datos impide duplicar una relación entre revista y tipo de material. |
| `test_shared_journal_academic_program_unique_constraint` | La base de datos impide duplicar una relación entre revista y programa académico. |
| `test_shared_journal_platform_unique_constraint` | La base de datos impide duplicar una relación entre revista y plataforma. |
| `test_shared_journal_platform_fields` | Verifica los atributos propios de `SharedJournalPlatform`: período de inicio, período de finalización y disponibilidad de texto completo. |

---

### 2. Serializadores (`apps/journal/tests/test_serializers.py`)

| Prueba | Resultado Esperado |
| --- | --- |
| `test_journal_serializer_create_with_all_relations` | El serializador administrativo crea la revista y sincroniza correctamente las relaciones de idioma, país, área del conocimiento, tipo de material, programa académico y plataforma. |
| `test_journal_serializer_normalizes_issn` | Normaliza correctamente el ISSN al formato `XXXX-XXXX`, incluyendo espacios, guiones y mayúsculas. |
| `test_journal_serializer_rejects_invalid_issn` | Rechaza un ISSN con formato inválido mediante error de validación. |
| `test_sync_relations_deduplicates_repeated_ids` | IDs repetidos en las relaciones no generan registros duplicados en las tablas intermedias. |
| `test_removed_relations_are_soft_deleted_and_hidden` | Las relaciones retiradas mediante una lista vacía se eliminan lógicamente y dejan de aparecer en la representación activa. |
| `test_archived_relation_is_restored` | Una relación previamente eliminada mediante Soft Delete se restaura al volver a incluirla en el payload. |
| `test_platform_relation_updates_extra_fields` | Actualiza correctamente los atributos propios de `SharedJournalPlatform`, incluyendo períodos y disponibilidad de texto completo. |
| `test_platform_relation_rejects_invalid_period` | Rechaza una relación con plataforma cuando el período final es anterior al período inicial. |
| `test_archived_platform_relation_is_restored_and_updated` | Restaura y actualiza correctamente una relación `Journal - Platform` previamente eliminada. |
| `test_duplicate_platforms_are_rejected` | Rechaza plataformas duplicadas dentro del mismo payload. |
| `test_archived_journal_restored_via_serializer` | Una revista eliminada que se recrea con el mismo ISSN es restaurada en lugar de generar un registro duplicado. |
| `test_partial_update_without_relations_keeps_existing_relations` | Una actualización parcial que no incluye relaciones conserva las relaciones existentes. |
| `test_public_serializer_excludes_audit_fields_and_includes_public_platform` | `JournalPublicSerializer` no expone campos internos de auditoría y representa las plataformas publicadas con sus atributos de relación. |

---

### 3. Servicios y Lógica de Negocio (`apps/journal/tests/test_services.py`)

| Prueba | Resultado Esperado |
| --- | --- |
| `test_create_journal_success` | Crea correctamente una revista mediante el servicio, incluyendo sus campos principales y relaciones. |
| `test_create_journal_normalizes_issn` | Normaliza el ISSN antes de almacenarlo. |
| `test_create_journal_rejects_invalid_issn` | Lanza `ValidationError` cuando el ISSN no cumple el formato establecido. |
| `test_create_journal_requires_issn` | Valida que el ISSN sea obligatorio para la creación de una revista. |
| `test_create_journal_updates_existing_issn` | Cuando ya existe una revista con el mismo ISSN, actualiza el registro existente en lugar de crear un duplicado. |
| `test_create_journal_restores_archived_journal` | Cuando existe una revista eliminada con el mismo ISSN, la restaura y actualiza sus datos. |
| `test_restore_clears_validation` | Una revista restaurada pierde la validación previa y debe ser validada nuevamente. |
| `test_create_journal_syncs_all_relations` | Sincroniza correctamente las cinco relaciones simples de la revista. |
| `test_create_journal_deduplicates_relation_ids` | Deduplica IDs repetidos antes de sincronizar las relaciones. |
| `test_empty_relation_list_removes_existing_relations` | Una lista vacía elimina lógicamente las relaciones existentes del tipo indicado. |
| `test_none_relation_does_not_modify_existing_relations` | Una relación recibida como `None` no modifica las relaciones existentes. |
| `test_create_journal_rejects_nonexistent_relation_id` | Rechaza identificadores de relaciones que no existen. |
| `test_create_journal_rejects_invalid_editorial` | Rechaza una editorial inexistente. |
| `test_create_journal_rejects_invalid_period` | Rechaza períodos generales de la revista cuando la fecha final es anterior a la inicial. |
| `test_create_journal_syncs_source_platform` | Crea correctamente la relación de procedencia con una plataforma y sus atributos propios. |
| `test_source_platform_updates_existing_relation` | Actualiza los atributos de una relación `Journal - Platform` existente. |
| `test_source_platform_restores_archived_relation` | Restaura una relación `Journal - Platform` previamente eliminada mediante Soft Delete. |
| `test_source_platform_rejects_invalid_period` | Rechaza un período inválido en la relación con la plataforma. |
| `test_source_platform_rejects_invalid_platform` | Rechaza una plataforma inexistente. |

---

### 4. Endpoints y API (`apps/journal/tests/test_api.py`)

| Prueba | Resultado Esperado |
| --- | --- |
| `test_create_journal_endpoint` | `POST /api/journals/` crea una revista correctamente mediante la API y retorna HTTP 201. |
| `test_list_journals_returns_active_journals` | `GET /api/journals/` lista las revistas disponibles en el endpoint administrativo y excluye registros eliminados mediante Soft Delete. |
| `test_publish_action_endpoint` | `POST /api/journals/{id}/publish/` activa y valida una revista, registrando el usuario y la fecha de validación. |
| `test_deactivate_action_endpoint` | `POST /api/journals/{id}/deactivate/` desactiva una revista. |
| `test_destroy_with_business_relation_soft_deletes_journal` | `DELETE /api/journals/{id}/` realiza eliminación lógica cuando la revista posee relaciones de negocio y conserva el registro en `all_objects`. |
| `test_archived_endpoint_returns_deleted_journals` | `GET /api/journals/archived/` lista las revistas eliminadas mediante Soft Delete. |
| `test_restore_action_endpoint` | `POST /api/journals/{id}/restore/` restaura una revista eliminada y limpia su validación previa. |
| `test_restore_nonexistent_archived_journal_returns_404` | Intentar restaurar una revista inexistente retorna HTTP 404. |
| `test_public_endpoint_lists_only_active_validated_journals` | `GET /api/journals/public/` únicamente expone revistas activas y previamente validadas. |
| `test_public_endpoint_excludes_soft_deleted_journals` | Las revistas eliminadas mediante Soft Delete no aparecen en el endpoint público. |
| `test_public_filter_by_knowledge_area` | `GET /api/journals/public/?knowledge_area={id}` filtra correctamente las revistas vinculadas con el área del conocimiento indicada. |
| `test_public_filter_by_country` | `GET /api/journals/public/?country={id}` filtra correctamente por país. |
| `test_public_filter_by_language` | `GET /api/journals/public/?language={id}` filtra correctamente por idioma. |
| `test_public_filter_by_platform` | `GET /api/journals/public/?platform={id}` filtra correctamente por plataforma. |
| `test_public_filter_by_title` | El filtro público por título permite encontrar revistas mediante coincidencia parcial. |
| `test_public_filter_by_issn_without_hyphen` | El filtro público por ISSN acepta el valor sin guion. |
| `test_public_filter_with_nonexistent_knowledge_area_returns_empty` | Un ID inexistente en el filtro de área del conocimiento retorna cero resultados sin generar error. |

---

## Resultado de la Suite

Las pruebas fueron ejecutadas de forma independiente por cada capa y posteriormente mediante la suite integral de la aplicación.

```text
Modelos:          11/11 OK
Serializadores:   13/13 OK
Servicios:        19/19 OK
API:              17/17 OK
--------------------------------
TOTAL:            60/60 OK
```

La suite integral de `journal` también fue ejecutada satisfactoriamente:

```bash
docker compose -f docker/docker-compose.yml exec web python manage.py test apps.journal --keepdb
```

Resultado:

```text
OK
```

---

## Ejecutar Pruebas

Para ejecutar la suite completa de `journal` dentro del contenedor Docker:

```bash
docker compose -f docker/docker-compose.yml exec web python manage.py test apps.journal --keepdb
```

Para ejecutar cada capa individualmente:

### Modelos

```bash
docker compose -f docker/docker-compose.yml exec web python manage.py test apps.journal.tests.test_models --keepdb
```

### Serializadores

```bash
docker compose -f docker/docker-compose.yml exec web python manage.py test apps.journal.tests.test_serializers --keepdb
```

### Servicios

```bash
docker compose -f docker/docker-compose.yml exec web python manage.py test apps.journal.tests.test_services --keepdb
```

### API

```bash
docker compose -f docker/docker-compose.yml exec web python manage.py test apps.journal.tests.test_api --keepdb
```

La bandera `--keepdb` es recomendada al utilizar PostgreSQL / Neon DB para conservar la base de datos temporal de pruebas, evitando la recreación de la base en cada ejecución y reduciendo problemas asociados al cierre de conexiones.

---