# API de `journal` - Fase A

Esta guía permite levantar el proyecto y probar la API de `journal` sin leer el código.
Durante la Fase A no se exige autenticación del cliente: las operaciones utilizan el usuario del sistema con `code=0`.
La autenticación JWT y los permisos pertenecen a la Fase B.

## 1. Requisitos

- Docker Desktop iniciado.
- Git.
- Un archivo `.env` en la raíz del proyecto.

Debes crear un archivo `.env` en la raíz del proyecto y completar los datos de la base de datos. El archivo `.env` real no debe subirse a Git porque contiene credenciales.

## 2. Preparar y levantar el proyecto

Ejecuta los comandos desde la raíz del repositorio:

```powershell
docker compose -f docker/docker-compose.yml build
docker compose -f docker/docker-compose.yml run --rm web python manage.py migrate
docker compose -f docker/docker-compose.yml run --rm web python manage.py create_system_user
docker compose -f docker/docker-compose.yml run --rm web python manage.py seed_catalog
docker compose -f docker/docker-compose.yml up
```

La API quedará disponible en:

```text
http://localhost:8000
```

Para asociar una revista a una plataforma, la plataforma debe existir y no
estar eliminada lógicamente. Puede encontrarse en `BORRADOR`, `PUBLICADO` u
`OBSOLETO`; la asociación no modifica su estado ni la publica.

## 3. Swagger y esquema OpenAPI

Abre esta URL en el navegador:

```text
http://localhost:8000/api/docs/
```

Para el esquema OpenAPI sin interfaz:

```text
http://localhost:8000/api/schema/
```

En Swagger, selecciona un endpoint, pulsa **Try it out**, completa el cuerpo JSON y pulsa **Execute**.

La validación general del esquema quedó en:

```text
Warnings: 0
Errors:   0
```

## 4. Recursos disponibles

| Recurso | Ruta base | Uso / campos principales |
| --- | --- | --- |
| Revistas | `/api/journals/` | CRUD administrativo y ciclo de publicación |
| Revistas públicas | `/api/journals/public/` | Consulta de revistas activas y validadas |

Las tablas intermedias `SharedJournal*` no tienen endpoints CRUD independientes. Se administran desde el serializer de `Journal` y desde servicios internos.

### 4.1. Campos de escritura de `Journal`

```text
issn
title
editorial
publication_date
licenses
url_image
has_apc
languages
countries
material_types
academic_programs
platforms
```

Los siguientes campos son de solo lectura o son controlados por el backend:

```text
id
active
validated_by
validated_at
fetched_at
knowledge_areas
created_by
created_at
updated_by
updated_at
deleted_by
deleted_at
delete_explanation
```

### 4.2. ISSN

El ISSN es el identificador principal para deduplicación.

Se normaliza al formato:

```text
XXXX-XXXX
```

Por ejemplo:

```text
1476 4687  →  1476-4687
14764687   →  1476-4687
```

La base de datos mantiene una restricción de unicidad insensible a mayúsculas/minúsculas.

### 4.3. Programas académicos y áreas del conocimiento

El cliente selecciona únicamente:

```text
academic_programs
```

`knowledge_areas` es de solo lectura y se deriva automáticamente mediante:

```text
AcademicProgram
    ↓
SharedAcademicProgramKnowledgeArea
    ↓
KnowledgeArea
    ↓
SharedJournalKnowledgeArea
```

Por tanto, no se debe enviar `knowledge_areas` como clasificación manual.

Reglas de actualización:

- si `academic_programs` no viene en un `PATCH`, se conservan programas y áreas;
- si llega una lista nueva, se sincronizan los programas y se recalculan las áreas;
- si llega `"academic_programs": []`, se eliminan lógicamente los programas y las áreas derivadas.

### 4.4. Relación con plataformas

El campo `platforms` recibe una lista con objetos de esta forma:

```json
[
  {
    "platform": 1,
    "journal_url": "https://revista.ejemplo.org",
    "has_full_text": true
  }
]
```

En las respuestas, cada relación incluye además:

- `public_url`: URL general navegable de la plataforma, tomada del último `LinkCheckLog` no eliminado cuyo `journal_platform` es nulo.
- `journal_url`: campo virtual obligatorio para relaciones nuevas y opcional al actualizar una relación existente. La URL se toma del último `LinkCheckLog` no eliminado asociado al `SharedJournalPlatform` correspondiente.
- `start_period`: fecha de vinculación con la plataforma, asignada por el backend.
- `finish_period`: fecha de finalización por Soft Delete, o `null` mientras la vinculación siga vigente.

`start_period` y `finish_period` son de solo lectura. Si el cliente intenta
enviarlos en `POST`, `PUT` o `PATCH`, la API responde HTTP 400. El Frontend no
debe mostrar inputs editables para estas fechas.

Una revista puede tener un `journal_url` distinto por plataforma. Ninguno de estos valores se obtiene de `base_api_url`, que está reservado para harvesting, ni se persiste en `Journal`, `Platform` o `SharedJournalPlatform`.

Omitir `journal_url` en un `PATCH` conserva el historial. Repetir la URL vigente no crea otro log; una URL diferente genera un nuevo registro. La URL puede pertenecer a un dominio distinto al de `public_url`: se valida seguridad SSRF, no igualdad de hostname.

Regla de asociación:

```text
Platform no eliminada → permitir asociación en BORRADOR, PUBLICADO u OBSOLETO
Platform eliminada    → HTTP 400
```

La asociación es administrativa: no cambia `status`, `validated_by` ni
`validated_at`. Una Platform en BORRADOR permanece en BORRADOR hasta ejecutar
explícitamente `POST /api/platforms/{id}/publish/`. En las respuestas públicas
de Journal solo se muestran relaciones cuya Platform está PUBLICADA.

También se valida que `finish_period` no sea anterior a `start_period`.

### 4.5. Servicio interno `create_journal()`

Además del endpoint administrativo existe un servicio Python reutilizable para cosecha y procesos backend.

No tiene una ruta HTTP propia.

Su interfaz actual recibe, entre otros:

```text
issn
title
editorial_id
language_ids
country_ids
material_type_ids
academic_program_ids
platform_id
journal_url
has_full_text
```

`create_journal()` **no recibe `knowledge_area_ids`**. Las áreas se derivan exclusivamente desde `academic_program_ids`.

Si recibe `platform_id`, la plataforma debe existir y no estar eliminada
lógicamente. No se exige que esté `PUBLICADO`.

## 5. Operaciones generales

### 5.1. Administración

| Método | Ruta | Uso | Respuesta habitual |
| --- | --- | --- | --- |
| GET | `/api/journals/` | Listar revistas no eliminadas | 200 |
| POST | `/api/journals/` | Crear revista manualmente | 201 |
| GET | `/api/journals/{id}/` | Consultar revista | 200 |
| PUT | `/api/journals/{id}/` | Reemplazar información editable | 200 |
| PATCH | `/api/journals/{id}/` | Actualizar parcialmente | 200 |
| DELETE | `/api/journals/{id}/` | Eliminación física o lógica según relaciones | 204/200 |
| GET | `/api/journals/archived/` | Listar revistas eliminadas lógicamente | 200 |
| POST | `/api/journals/{id}/restore/` | Restaurar revista eliminada | 200 |
| POST | `/api/journals/{id}/publish/` | Activar y validar revista | 200 |
| POST | `/api/journals/{id}/deactivate/` | Marcar revista como inactiva | 200 |

`active`, `validated_by` y `validated_at` son campos de solo lectura en el
serializer administrativo. El cliente puede consultarlos, pero no controlarlos
mediante `POST`, `PUT` o `PATCH`.

Crear una revista, manualmente o mediante harvesting, siempre la deja pendiente
de publicación: `active=false`, `validated_by=null` y `validated_at=null`. La
única operación que la publica es `POST /api/journals/{id}/publish/`.

Una actualización de la ficha limpia la validación previa. Por tanto, una revista modificada debe publicarse nuevamente antes de regresar a la consulta pública.

### 5.2. Consulta pública

| Método | Ruta | Uso |
| --- | --- | --- |
| GET | `/api/journals/public/` | Listar revistas públicas |
| GET | `/api/journals/public/{id}/` | Consultar ficha pública |

Para aparecer en la consulta pública una revista debe cumplir simultáneamente:

```text
active = True
validated_at != null
deleted_at = null
```

Las revistas eliminadas lógicamente tampoco aparecen.

## 6. Ejemplos con `curl`

### 6.1. Crear una revista

```bash
curl -X POST http://localhost:8000/api/journals/ \
  -H "Content-Type: application/json" \
  -d '{
    "issn": "1476 4687",
    "title": "Nature",
    "editorial": 1,
    "publication_date": "1869-11-04",
    "has_apc": false,
    "languages": [1],
    "countries": [1],
    "material_types": [1],
    "academic_programs": [1],
    "platforms": [{
      "platform": 1,
      "journal_url": "https://example.org/nature"
    }]
  }'
```

El ISSN se almacena normalizado como `1476-4687`. La revista se crea pendiente:
`active=false`, `validated_by=null` y `validated_at=null`, aunque el cliente
intente enviar valores diferentes para esos campos de solo lectura.

La respuesta incluye las `knowledge_areas` derivadas automáticamente de `academic_programs`.

### 6.2. Crear una revista asociada a una plataforma

```bash
curl -X POST http://localhost:8000/api/journals/ \
  -H "Content-Type: application/json" \
  -d '{
    "issn": "1234-5678",
    "title": "Revista de ejemplo",
    "academic_programs": [1],
    "platforms": [
      {
        "platform": 1,
        "journal_url": "https://revista.ejemplo.org/",
        "has_full_text": true
      }
    ]
  }'
```

La plataforma con ID `1` puede estar en `BORRADOR`, `PUBLICADO` u `OBSOLETO`,
siempre que no esté eliminada lógicamente. La operación no cambia `status`,
`validated_by` ni `validated_at` de la Platform.

### 6.3. Cambiar programas académicos

```bash
curl -X PATCH http://localhost:8000/api/journals/1/ \
  -H "Content-Type: application/json" \
  -d '{"academic_programs":[2,3]}'
```

El backend sincroniza los programas y recalcula las áreas derivadas.

### 6.4. Eliminar todos los programas y áreas derivadas

```bash
curl -X PATCH http://localhost:8000/api/journals/1/ \
  -H "Content-Type: application/json" \
  -d '{"academic_programs":[]}'
```

### 6.5. Actualizar un campo sin modificar la clasificación

```bash
curl -X PATCH http://localhost:8000/api/journals/1/ \
  -H "Content-Type: application/json" \
  -d '{"publication_date":"1869-11-04"}'
```

Al no enviar `academic_programs`, las relaciones existentes permanecen iguales.

Como la ficha fue modificada, su validación previa se limpia y debe publicarse de nuevo.

### 6.6. Publicar una revista

```bash
curl -X POST http://localhost:8000/api/journals/1/publish/
```

La acción establece:

```text
active = True
validated_by = usuario del sistema/usuario actuante
validated_at = fecha actual
```

### 6.7. Desactivar una revista

```bash
curl -X POST http://localhost:8000/api/journals/1/deactivate/
```

La revista queda con `active=false` y deja de aparecer en la consulta pública.
La acción conserva `validated_by` y `validated_at` como historial de su última
validación. Una llamada posterior a `/publish/` actualiza nuevamente esos datos
y puede volver a publicarla.

### 6.8. Listar revistas públicas

```bash
curl http://localhost:8000/api/journals/public/
```

La respuesta utiliza la paginación global del proyecto:

```json
{
  "current_page": 1,
  "total_pages": 1,
  "page_size": 10,
  "total_items": 1,
  "next": null,
  "previous": null,
  "results": []
}
```

Cada elemento del listado incluye `item_number`.

## 7. Borrado lógico y restauración

Para eliminar una revista con relaciones de negocio, envía una explicación:

```bash
curl -X DELETE http://localhost:8000/api/journals/1/ \
  -H "Content-Type: application/json" \
  -d '{"delete_explanation":"Revista retirada del repositorio"}'
```

Los registros archivados se consultan con:

```text
GET /api/journals/archived/
```

Para restaurar:

```bash
curl -X POST http://localhost:8000/api/journals/1/restore/
```

La restauración limpia `validated_by` y `validated_at`. Aunque la revista hubiera estado activa anteriormente, no vuelve al módulo público hasta ser publicada de nuevo.

## 8. Búsqueda, ordenamiento y filtros

### 8.1. Administración

Búsqueda por título o ISSN:

```bash
curl "http://localhost:8000/api/journals/?search=nature"
curl "http://localhost:8000/api/journals/?search=1476-4687"
```

Filtros administrativos:

```text
editorial
has_apc
active
```

Ejemplos:

```bash
curl "http://localhost:8000/api/journals/?editorial=1"
curl "http://localhost:8000/api/journals/?active=true"
```

Ordenamiento disponible por:

```text
title
issn
publication_date
created_at
updated_at
fetched_at
```

Ejemplo:

```bash
curl "http://localhost:8000/api/journals/?ordering=-updated_at"
```

### 8.2. Consulta pública

Filtros disponibles:

```text
issn
title
editorial
language
country
knowledge_area
material_type
academic_program
platform
has_apc
publication_date_from
publication_date_to
```

Ejemplos:

```bash
curl "http://localhost:8000/api/journals/public/?issn=14764687"
curl "http://localhost:8000/api/journals/public/?title=biology"
curl "http://localhost:8000/api/journals/public/?country=1"
curl "http://localhost:8000/api/journals/public/?knowledge_area=1"
curl "http://localhost:8000/api/journals/public/?academic_program=1"
curl "http://localhost:8000/api/journals/public/?platform=1"
curl "http://localhost:8000/api/journals/public/?has_apc=false"
curl "http://localhost:8000/api/journals/public/?publication_date_from=2020-01-01"
```

El filtro `platform` únicamente considera relaciones con plataformas que continúan en estado `PUBLICADO`.

También admite `search` por título/ISSN y ordenamiento por `title`, `issn`
y `publication_date`.

## 9. Probar sin modificar la base de datos normal

La suite de Django utiliza una base de datos de pruebas separada. Para ejecutar las pruebas de `journal`:

```bash
docker compose -f docker/docker-compose.yml run --rm -e DJANGO_TESTING=true web python manage.py test apps.journal --keepdb
```

Inventario actual de la suite:

```text
85 pruebas
```

Distribución actual:

```text
Modelos:          11
Serializadores:   28
Clasificación:     3
Servicios:        24
API:              19
```

Para validar también el esquema OpenAPI:

```bash
docker compose -f docker/docker-compose.yml run --rm web python manage.py spectacular --validate --file /tmp/schema.yml
```

Resultado validado:

```text
Warnings: 0
Errors:   0
```

## 10. Errores frecuentes

| Código | Causa típica |
| --- | --- |
| 400 | ISSN inválido, período incoherente, relación duplicada, plataforma eliminada, URL insegura o identificador de catálogo inválido |
| 404 | ID inexistente o revista eliminada |
| 405 | Método HTTP no permitido, por ejemplo intentar escribir sobre `/public/` |
| 500 al iniciar | Dependencias, `.env` o migraciones pendientes |

Si la API no inicia, ejecuta:

```bash
docker compose -f docker/docker-compose.yml exec web python manage.py check
```

La autenticación JWT, los permisos y la protección de escritura se implementarán en la Fase B.
# Clasificación académica vigente

El Frontend administra `academic_programs`. `knowledge_areas` es read-only y
se calcula como la unión sin duplicados de las áreas activas de los programas
activos asociados. Por ejemplo:

```json
{
  "issn": "1234-5678",
  "title": "Revista de ejemplo",
  "academic_programs": [1, 4]
}
```

No se debe enviar `knowledge_areas`. Un `PATCH` que omite
`academic_programs` conserva la clasificación; una lista vacía elimina
lógicamente los vínculos fuente y las áreas derivadas.

Toda edición que requiere revisión deja la Journal con `active=false`,
`validated_by=null` y `validated_at=null`. Esto la excluye inmediatamente de
la clasificación de sus Platforms. La acción `publish` vuelve a validarla y
recalcula dichas Platforms. El borrado y la restauración son lógicos; una
Journal restaurada permanece inactiva y sin validar hasta una publicación
explícita.

La arquitectura actual no realiza cascada lógica automática sobre
`SharedJournalPlatform` al eliminar una Journal; conserva esos vínculos
históricos activos, pero dejan de aportar clasificación porque la Journal está
eliminada. Al restaurarla siguen sin aportar hasta que sea republicada.

Una Journal aporta a Platform solo cuando ella y el vínculo Journal–Platform
no están eliminados, `active=true` y `validated_at` no es nulo. Los vínculos
nuevos o restaurados admiten Platforms en cualquier estado, siempre que no
estén eliminadas. Asociar una Platform no cambia su estado ni sus datos de
validación.
## Contrato estructural vigente

- `publication_date` es la fecha propia de publicación/origen de la revista.
- `SharedJournalPlatform.start_period` es la fecha automática de vinculación y
  `finish_period` es la fecha automática de Soft Delete. Ambas son de solo
  lectura y se conservan en las respuestas por compatibilidad.
- Toda relación nueva requiere `journal_url`; se registra en `LinkCheckLog` y no
  como columna de Journal o `SharedJournalPlatform`.
- Una Journal nueva requiere al menos una Platform.
- `licenses` expone las licencias asociadas. Las licencias se administran en
  `/api/journals/licenses/`.
- `POST /api/journals/{id}/publish/` acepta opcionalmente
  `{"licenses": [1, 2]}`. Omitir el campo conserva las relaciones y enviar una
  lista vacía las elimina lógicamente. Todavía se permite publicar sin licencia.
- El servicio `create_journal()` exige `platform_id` y `journal_url`, no recibe
  licencias y registra la URL contextual de forma atómica.

Pendiente: evaluar que una licencia sea obligatoria para publicar.

Pendiente: evaluar eliminar `SharedJournalPlatform.start_period` y
`SharedJournalPlatform.finish_period` si la auditoría (`created_at` y
`deleted_at`) resulta suficiente como fuente temporal.
