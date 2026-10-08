# Pruebas de la Aplicación `platforms` (Fase A)

Estas pruebas documentan y validan el comportamiento integral del módulo `platforms` sin autenticación obligatoria del cliente, utilizando el usuario del sistema con `code=0`.

Estado de validación: **30 pruebas ejecutadas y aprobadas al 100%** dentro del contenedor Docker con PostgreSQL.

```text
Found 30 test(s).
System check identified no issues (0 silenced).
[30 pruebas aprobadas]
----------------------------------------------------------------------
Ran 30 tests
OK
```

---

## 1. Reglas funcionales verificadas

Durante la evolución de la Fase A se ajustaron varias reglas de negocio importantes del módulo `platforms`. Las pruebas actuales deben interpretarse bajo estas reglas:

### 1.1. API Key y `base_api_url`

- La `api_key` es **opcional**.
- `base_api_url` es **opcional**.
- Una plataforma puede existir únicamente como referencia pública, sin mecanismos de cosecha.
- Una plataforma puede tener `base_api_url` sin `api_key`, por ejemplo cuando la API no requiere autenticación.
- No se permite configurar una `api_key` cuando no existe `base_api_url`, porque la clave quedaría asociada a una API inexistente.
- `base_api_url` corresponde exclusivamente a la API utilizada para procesos de cosecha; **no representa la URL pública de la plataforma**.

### 1.2. URL pública de la plataforma

La URL pública que permite al usuario acceder a la plataforma **no corresponde a un campo de `Platform`**.

La URL pública se registra mediante:

```text
Platform
    │
    └── LinkCheckLog
            └── url
```

Por tanto:

- `base_api_url` y `LinkCheckLog.url` tienen propósitos diferentes.
- `LinkCheckLog.url` es la URL pública que se presenta/verifica para acceso a la plataforma.
- Una plataforma debe tener una URL pública registrada en `LinkCheckLog` para poder pasar a `PUBLICADO`.
- La verificación de enlaces utiliza la URL pública registrada y no `base_api_url`.
- `fail_count` se controla por URL y se reinicia cuando una verificación resulta exitosa.

### 1.3. Programas académicos y áreas del conocimiento

Las `knowledge_areas` **no deben ser introducidas manualmente por el usuario** como clasificación independiente de la plataforma.

La clasificación se obtiene mediante:

```text
AcademicProgram
        │
        ▼
SharedAcademicProgramKnowledgeArea
        │
        ▼
KnowledgeArea
        │
        ▼
SharedPlatformKnowledgeArea
```

El administrador o usuario autorizado selecciona los `academic_programs` asociados a la plataforma y el sistema deriva automáticamente las `knowledge_areas` correspondientes.

Esto permite:

- Evitar inconsistencias entre programas académicos y áreas del conocimiento.
- Evitar que el usuario asigne manualmente áreas que no correspondan a los programas seleccionados.
- Consolidar áreas repetidas cuando varios programas comparten la misma área.
- Mantener la clasificación de la plataforma sincronizada con la relación académica existente.

### 1.4. Publicación de plataformas

Una plataforma únicamente puede pasar a `PUBLICADO` cuando cumple las condiciones definidas por la lógica de negocio.

Entre ellas:

- Tener una URL pública registrada en `LinkCheckLog`.
- Tener el período de cobertura requerido.
- Tener una `ValidSintaxis` asociada.
- Tener las relaciones de catálogo requeridas activas.
- Si tiene `api_key`, debe tener también `base_api_url`.
- La plataforma debe encontrarse en estado `BORRADOR`.

Una plataforma que no tenga API de cosecha puede publicarse siempre que cumpla las demás condiciones; **la ausencia de `base_api_url` no es por sí sola un impedimento para publicar**.

---

## 2. Casos Cubiertos por Capas

### 2.1. Modelos (`apps/platforms/tests/test_models.py`)

| Prueba | Resultado Esperado |
| --- | --- |
| `test_platform_encryption_and_decryption` | La API Key se almacena cifrada (`encrypted_api_key`) mediante Fernet y se descifra correctamente en memoria. |
| `test_platform_name_normalized_to_lowercase` | El nombre se normaliza a minúsculas y se eliminan espacios redundantes mediante `AuditableModel`. |
| `test_platform_name_case_insensitive_unique_constraint` | La base de datos rechaza nombres duplicados sin importar mayúsculas/minúsculas mediante la restricción de unicidad correspondiente. |
| `test_valid_sintaxis_creation_and_soft_delete` | Se validan los campos JSON de `ValidSintaxis` y su ciclo de Soft Delete, conservando el registro en `all_objects`. |
| `test_link_check_log_fail_count_and_ordering` | `LinkCheckLog` registra las verificaciones y mantiene el ordenamiento esperado por fecha de chequeo y creación. |
| `test_shared_platform_unique_constraint` | Se valida la unicidad compuesta de las relaciones intermedias, evitando asociaciones duplicadas. |

### 2.2. Serializadores (`apps/platforms/tests/test_serializers.py`)

Los tests del serializador verifican, entre otros aspectos:

| Comportamiento | Resultado Esperado |
| --- | --- |
| Creación de plataforma con API Key | La clave se almacena cifrada y nunca se expone como `encrypted_api_key` en la respuesta. |
| API Key nula | Se permite crear una plataforma sin API Key. |
| `base_api_url` nula | Se permite una plataforma sin API para casos de referencia o plataformas que no serán cosechadas. |
| API Key sin `base_api_url` | Se rechaza la configuración porque la API Key no puede quedar asociada a una API inexistente. |
| `base_api_url` sin API Key | Se permite cuando la API es pública o no requiere autenticación. |
| Programas académicos | Se sincronizan mediante IDs proporcionados por el usuario autorizado. |
| Áreas del conocimiento | Se derivan automáticamente de los programas académicos relacionados. |
| Áreas duplicadas | Se consolidan sin generar relaciones duplicadas. |
| `academic_programs` omitido en un `PATCH` | Se conservan las relaciones existentes. |
| `academic_programs: []` | Se eliminan las relaciones de programas y las áreas derivadas correspondientes. |
| `knowledge_areas` | No se utiliza como entrada manual para clasificar la plataforma. |
| Restauración de plataforma archivada | Una plataforma eliminada que se recrea conforme a las reglas del servicio vuelve a `BORRADOR` y limpia la validación previa. |
| Serializer público | No expone información sensible ni campos internos de auditoría. |

### 2.3. Servicios y Lógica de Negocio (`apps/platforms/tests/test_services.py`)

| Prueba | Resultado Esperado |
| --- | --- |
| `test_publish_platform_succeeds_when_complete` | Una plataforma completa, incluida su URL pública en `LinkCheckLog`, pasa a `PUBLICADO` y registra `validated_by` y `validated_at`. |
| `test_publish_platform_fails_when_incomplete` | Lanza `ValidationError` detallando los campos o relaciones obligatorias que faltan. La ausencia de `base_api_url` por sí sola no genera error cuando no existe API Key. |
| `test_lifecycle_transitions_obsolete_and_reactivate` | Transición controlada `BORRADOR` → `PUBLICADO` → `OBSOLETO` → `BORRADOR`, limpiando la validación al reactivar. |
| `test_validate_safe_http_url_blocks_internal_and_private_ips` | Protección preventiva contra SSRF bloqueando `localhost`, `127.0.0.1` y rangos privados. |
| `test_check_platform_link_records_consecutive_fail_count` | Registra la URL pública en `LinkCheckLog`, incrementa `fail_count` ante fallos consecutivos y lo reinicia a `0` ante una respuesta exitosa. |

### 2.4. Endpoints y API (`apps/platforms/tests/test_api.py`)

| Prueba | Resultado Esperado |
| --- | --- |
| `test_create_platform_endpoint` | `POST /api/platforms/` crea la plataforma en estado `BORRADOR`, retorna HTTP 201 y no expone la clave cifrada. |
| `test_publish_action_endpoint` | `POST /api/platforms/{id}/publish/` ejecuta las validaciones de negocio y publica la plataforma cuando la ficha está completa. |
| `test_restore_action_resets_status_to_draft` | `POST /api/platforms/{id}/restore/` restaura una plataforma desde la papelera y fuerza `status = BORRADOR`, limpiando la validación previa. |
| `test_public_endpoint_only_lists_published_platforms` | `GET /api/platforms/public/` solo expone plataformas con `status = PUBLICADO` e incluye el correlativo `item_number`. |
| `test_public_filter_by_catalog_relations` | Se validan los filtros relacionales en singular, por ejemplo `?country=...`, respetando el estado activo de la relación y del catálogo. |

---

## 3. Comportamiento de `LinkCheckLog`

`LinkCheckLog` es el componente encargado de mantener el historial de verificación de las URLs públicas de las plataformas.

Cada verificación registra, entre otros datos:

- Plataforma asociada.
- URL pública verificada.
- Código HTTP obtenido.
- Estado de disponibilidad.
- Cantidad de fallos consecutivos.
- Fecha de la última comprobación.
- Información de auditoría.

La URL registrada en `LinkCheckLog` es independiente de `Platform.base_api_url`.

Esto permite que una plataforma tenga, por ejemplo:

```json
{
    "base_api_url": null,
    "api_key": null
}
```

y aun así pueda tener:

```text
LinkCheckLog.url
    ↓
https://www.plataforma.edu.co
```

y ser publicada como plataforma de referencia.

---

## 4. Ciclo de vida de una plataforma

El ciclo de vida validado durante la Fase A es:

```text
BORRADOR
    │
    │ publicar
    ▼
PUBLICADO
    │
    │ marcar obsoleta
    ▼
OBSOLETO
    │
    │ reactivar
    ▼
BORRADOR
```

Adicionalmente, el sistema maneja eliminación lógica mediante Soft Delete.

Cuando una plataforma es restaurada desde la papelera:

- Se elimina el estado de eliminación.
- Se fuerza el estado `BORRADOR`.
- Se limpia `validated_by`.
- Se limpia `validated_at`.
- Debe pasar nuevamente por el proceso de validación antes de publicarse.

---

## 5. Seguridad

Las pruebas incluyen validaciones relacionadas con:

### API Key

La API Key:

- Se recibe únicamente como campo de escritura.
- Se almacena cifrada.
- No se retorna en texto plano.
- No puede existir lógicamente sin una `base_api_url`.

### Verificación de enlaces

La verificación de URLs incorpora protección contra destinos internos o privados, evitando consultar directamente:

```text
localhost
127.0.0.1
192.168.x.x
```

y otros destinos no públicamente enrutables.

### Información pública

Los serializers públicos no deben exponer:

- API Keys.
- Campos cifrados.
- Información interna de auditoría.
- Datos administrativos que no correspondan al consumidor público.

---

## 6. Estado actual de la Fase A

La suite integral de `platforms` fue ejecutada dentro del contenedor Docker utilizando PostgreSQL y `--keepdb`.

Resultado:

```text
Found 30 test(s).
System check identified no issues (0 silenced).

OK
```

**Estado: APROBADO — 30/30 pruebas.**

No se requirieron modificaciones de modelos ni migraciones como consecuencia de estas correcciones.

---

## 7. Ejecutar Pruebas

Para ejecutar la suite completa de `platforms` dentro del contenedor Docker:

```bash
docker compose -f docker/docker-compose.yml exec web python manage.py test apps.platforms --keepdb
```

Para ejecutar únicamente los tests de servicios:

```bash
docker compose -f docker/docker-compose.yml exec web python manage.py test apps.platforms.tests.test_services --keepdb
```

Para ejecutar únicamente los tests de API:

```bash
docker compose -f docker/docker-compose.yml exec web python manage.py test apps.platforms.tests.test_api --keepdb
```

Para ejecutar únicamente los tests de serializers:

```bash
docker compose -f docker/docker-compose.yml exec web python manage.py test apps.platforms.tests.test_serializers --keepdb
```

La bandera `--keepdb` permite reutilizar la base de datos temporal de pruebas y evitar la recreación completa en cada ejecución, especialmente útil en el entorno PostgreSQL utilizado por el proyecto.

---

## 8. Resultado de la Fase A

La aplicación `platforms` queda validada para continuar con la siguiente fase de desarrollo.

Las reglas principales verificadas son:

- Gestión segura y opcional de API Key.
- Separación entre API de cosecha y URL pública.
- URL pública gestionada mediante `LinkCheckLog`.
- Validación de enlaces.
- Control de fallos consecutivos.
- Clasificación mediante programas académicos.
- Derivación automática de áreas del conocimiento.
- Control del ciclo de vida de plataformas.
- Publicación condicionada al cumplimiento de los requisitos.
- Restauración mediante Soft Delete.
- Protección de información sensible.
- Filtros y endpoints públicos.
- Documentación de la API mediante Swagger/OpenAPI.

**Resultado final: Fase A de `platforms` aprobada con 30/30 pruebas.**
