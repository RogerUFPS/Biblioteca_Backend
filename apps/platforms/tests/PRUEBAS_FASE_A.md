# Pruebas de la Aplicación `platforms` (Fase A)

Estas pruebas documentan y validan el comportamiento integral del módulo `platforms` sin autenticación obligatoria del cliente, utilizando el usuario del sistema con `code=0`.

Estado de validación: **20 pruebas ejecutadas y aprobadas al 100%** dentro del contenedor Docker con PostgreSQL.

```text
Found 20 test(s).
System check identified no issues (0 silenced).
....................
----------------------------------------------------------------------
Ran 20 tests in 41.055s

OK
```

---

## Casos Cubiertos por Capas

### 1. Modelos (`apps/platforms/tests/test_models.py`)

| Prueba | Resultado Esperado |
| --- | --- |
| `test_platform_encryption_and_decryption` | La API Key se almacena cifrada (`encrypted_api_key`) mediante Fernet y se descifra intacta en memoria. |
| `test_platform_name_normalized_to_lowercase` | El nombre se normaliza a minúsculas y se eliminan espacios redundantes (`AuditableModel`). |
| `test_platform_name_case_insensitive_unique_constraint` | La base de datos rechaza nombres duplicados mediante `UniqueConstraint(Lower('name'))` (IntegrityError). |
| `test_valid_sintaxis_creation_and_soft_delete` | Manejo de campos JSON y Soft Delete en `ValidSintaxis` (conserva registro en `all_objects`). |
| `test_link_check_log_fail_count_and_ordering` | `LinkCheckLog` ordena descendentemente por fecha de chequeo y creación. |
| `test_shared_platform_unique_constraint` | Restricción de unicidad compuesta en relaciones intermedias (`SharedPlatformCountry`). |

### 2. Serializadores (`apps/platforms/tests/test_serializers.py`)

| Prueba | Resultado Esperado |
| --- | --- |
| `test_platform_serializer_create_with_api_key_and_relations` | Serializador administrativo persiste la clave cifrada y sincroniza las 6 relaciones M2M. |
| `test_sync_relations_deduplicates_repeated_ids` | Deduplica IDs repetidos en el payload evitando intentos de inserción múltiple. |
| `test_archived_platform_restored_via_serializer_resets_to_draft` | Una plataforma eliminada que se recrea por nombre vuelve en estado `BORRADOR` y limpia validación previa. |
| `test_public_serializer_excludes_sensitive_and_audit_fields` | `PlatformPublicSerializer` no expone `api_key`, `created_by`, `validated_by` ni auditoría interna; maneja `link_status`. |

### 3. Servicios y Lógica de Negocio (`apps/platforms/tests/test_services.py`)

| Prueba | Resultado Esperado |
| --- | --- |
| `test_publish_platform_succeeds_when_complete` | Pasa a estado `PUBLICADO` y registra `validated_by` y `validated_at` cuando la ficha está completa (6 relaciones activas). |
| `test_publish_platform_fails_when_incomplete` | Lanza `ValidationError` detallando los campos o relaciones faltantes. |
| `test_lifecycle_transitions_obsolete_and_reactivate` | Transición controlada `BORRADOR` $\rightarrow$ `PUBLICADO` $\rightarrow$ `OBSOLETO` $\rightarrow$ `BORRADOR` con limpieza de validación. |
| `test_validate_safe_http_url_blocks_internal_and_private_ips` | Protección preventiva contra SSRF bloqueando `localhost`, `127.0.0.1` y rangos privados (`192.168.x.x`). |
| `test_check_platform_link_records_consecutive_fail_count` | Incrementa `fail_count` ante fallos consecutivos y lo reinicia a `0` ante una respuesta exitosa. |

### 4. Endpoints y API (`apps/platforms/tests/test_api.py`)

| Prueba | Resultado Esperado |
| --- | --- |
| `test_create_platform_endpoint` | `POST /api/platforms/` crea la plataforma en borrador retornando HTTP 201 sin exponer la clave cifrada. |
| `test_publish_action_endpoint` | `POST /api/platforms/{id}/publish/` ejecuta la validación y publica la plataforma (HTTP 200). |
| `test_restore_action_resets_status_to_draft` | `POST /api/platforms/{id}/restore/` restaura desde papelera forzando `status = BORRADOR` y limpiando validación previa. |
| `test_public_endpoint_only_lists_published_platforms` | `GET /api/platforms/public/` solo expone plataformas con `status = PUBLICADO` e incluye correlativo `item_number`. |
| `test_public_filter_by_catalog_relations` | Filtrado relacional en singular (`?country=...`) validando que la relación y el catálogo permanezcan activos. |

---

## Ejecutar Pruebas

Para ejecutar la suite completa de `platforms` dentro del contenedor Docker:

```bash
docker compose -f docker/docker-compose.yml exec web python manage.py test apps.platforms --keepdb
```

*(La bandera `--keepdb` es recomendada al usar PostgreSQL / Neon DB para conservar la base de datos temporal de pruebas, evitando demoras de migración y bloqueos por pool de conexiones).*
