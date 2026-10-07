# API de `platforms` - Fase A

Esta guía permite levantar el proyecto y probar la API de `platforms` sin leer el código.
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

Para trabajar con plataformas deben existir previamente los registros de catálogo que se relacionarán con ellas: instituciones, idiomas, países, tipos de material, programas académicos y sus áreas del conocimiento.

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

La validación actual del esquema quedó en:

```text
Warnings: 0
Errors:   0
```

## 4. Recursos disponibles

| Recurso | Ruta base | Uso / campos principales |
| --- | --- | --- |
| Plataformas | `/api/platforms/` | CRUD administrativo de plataformas |
| Sintaxis válidas | `/api/platforms/valid-sintaxis/` | CRUD de configuraciones de sintaxis de búsqueda |
| Verificaciones de enlace | `/api/platforms/link-check-logs/` | Consulta de solo lectura del historial de verificación |
| Plataformas públicas | `/api/platforms/public/` | Consulta de plataformas en estado `PUBLICADO` |

### 4.1. Campos de escritura de `Platform`

```text
name
base_api_url
api_key
url_image
start_period
finish_period
requires_registration
has_access_text
valid_sintaxis
institutions
languages
countries
material_types
academic_programs
```

Los siguientes campos son de solo lectura o son controlados por el backend:

```text
id
status
validated_by
validated_at
knowledge_areas
created_by
created_at
updated_by
updated_at
deleted_by
deleted_at
delete_explanation
```

`knowledge_areas` **no se selecciona manualmente**. El backend la deriva a partir de `academic_programs` usando la relación `SharedAcademicProgramKnowledgeArea`.

### 4.2. `base_api_url` y `api_key`

Son datos de configuración de cosecha y son independientes de la URL pública.

| `base_api_url` | `api_key` | Resultado |
| --- | --- | --- |
| `null` | `null` | Válido: plataforma de referencia sin API de cosecha |
| URL | `null` | Válido: API sin autenticación |
| URL | valor | Válido: API con credencial |
| `null` | valor | **Inválido: HTTP 400** |

`api_key` es de solo escritura. El backend la almacena cifrada en `encrypted_api_key`, pero ni `api_key` ni `encrypted_api_key` aparecen en las respuestas.

En un `PATCH`:

- si `api_key` no se envía, se conserva la credencial actual;
- `"api_key": null` elimina la credencial existente;
- `"api_key": ""` se trata como ausencia de credencial.

### 4.3. URL pública de la plataforma

La implementación actual **no almacena la URL pública en `Platform`**. Se registra y conserva en el historial `LinkCheckLog.url`.

```text
Platform
    ↓
LinkCheckLog.url   ← URL pública

Platform.base_api_url ← API de cosecha
```

La URL pública se registra mediante:

```text
POST /api/platforms/{id}/check-link/
```

Una plataforma necesita al menos una URL pública registrada en `LinkCheckLog` antes de poder publicarse.

### 4.4. Campos de `ValidSintaxis`

Campos de escritura:

```text
name
booleans
parenthesis
fields
```

`fields_template` es de solo lectura y expone la plantilla canónica:

```json
{
  "title": "",
  "author": "",
  "subject": "",
  "issn": "",
  "language": "",
  "year": ""
}
```

`fields` solo acepta esas claves y valores de tipo string.

## 5. Operaciones generales

### 5.1. Plataformas administrativas

| Método | Ruta | Uso | Respuesta habitual |
| --- | --- | --- | --- |
| GET | `/api/platforms/` | Listar plataformas activas | 200 |
| POST | `/api/platforms/` | Crear plataforma | 201 |
| GET | `/api/platforms/{id}/` | Consultar plataforma | 200 |
| PUT | `/api/platforms/{id}/` | Reemplazar información editable | 200 |
| PATCH | `/api/platforms/{id}/` | Actualizar parcialmente | 200 |
| DELETE | `/api/platforms/{id}/` | Eliminación física o lógica según relaciones | 204/200 |
| GET | `/api/platforms/archived/` | Listar plataformas eliminadas lógicamente | 200 |
| POST | `/api/platforms/{id}/restore/` | Restaurar plataforma eliminada | 200 |
| POST | `/api/platforms/{id}/publish/` | `BORRADOR → PUBLICADO` | 200 |
| POST | `/api/platforms/{id}/mark-obsolete/` | `PUBLICADO → OBSOLETO` | 200 |
| POST | `/api/platforms/{id}/reactivate/` | `OBSOLETO → BORRADOR` | 200 |
| POST | `/api/platforms/{id}/check-link/` | Verificar y registrar URL pública | 200/400 |

`status` no se modifica mediante `POST`, `PUT` o `PATCH`. Las transiciones se realizan únicamente mediante las acciones de ciclo de vida.

Cuando una plataforma eliminada se restaura, vuelve a `BORRADOR` y se limpian `validated_by` y `validated_at`.

### 5.2. Sintaxis válidas

| Método | Ruta | Uso | Respuesta habitual |
| --- | --- | --- | --- |
| GET | `/api/platforms/valid-sintaxis/` | Listar sintaxis activas | 200 |
| POST | `/api/platforms/valid-sintaxis/` | Crear sintaxis | 201 |
| GET | `/api/platforms/valid-sintaxis/{id}/` | Consultar sintaxis | 200 |
| PUT | `/api/platforms/valid-sintaxis/{id}/` | Reemplazar sintaxis | 200 |
| PATCH | `/api/platforms/valid-sintaxis/{id}/` | Actualizar parcialmente | 200 |
| DELETE | `/api/platforms/valid-sintaxis/{id}/` | Eliminar según reglas de `AuditableViewSet` | 204/200 |
| GET | `/api/platforms/valid-sintaxis/archived/` | Listar sintaxis archivadas | 200 |
| POST | `/api/platforms/valid-sintaxis/{id}/restore/` | Restaurar sintaxis archivada | 200 |

### 5.3. Historial de verificación

`LinkCheckLog` es de solo lectura para el cliente.

| Método | Ruta | Uso |
| --- | --- | --- |
| GET | `/api/platforms/link-check-logs/` | Listar verificaciones |
| GET | `/api/platforms/link-check-logs/{id}/` | Consultar una verificación |

No existe `POST`, `PUT`, `PATCH` ni `DELETE` público para fabricar resultados de verificación. Los registros se crean mediante `check-link`.

### 5.4. Consulta pública

| Método | Ruta | Uso |
| --- | --- | --- |
| GET | `/api/platforms/public/` | Listar plataformas publicadas |
| GET | `/api/platforms/public/{id}/` | Consultar ficha pública |

Las plataformas `BORRADOR`, `OBSOLETO` o eliminadas no aparecen en este endpoint.

## 6. Ejemplos con `curl`

### 6.1. Crear una sintaxis válida

```bash
curl -X POST http://localhost:8000/api/platforms/valid-sintaxis/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Sintaxis estándar",
    "booleans": ["AND", "OR", "NOT"],
    "parenthesis": true,
    "fields": {
      "title": "ti",
      "author": "au",
      "subject": "su",
      "issn": "is",
      "language": "la",
      "year": "yr"
    }
  }'
```

La respuesta incluye además `fields_template`.

### 6.2. Crear una plataforma de referencia sin API de cosecha

```bash
curl -X POST http://localhost:8000/api/platforms/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Repositorio institucional",
    "base_api_url": null,
    "api_key": null,
    "start_period": "2020-01-01",
    "requires_registration": false,
    "has_access_text": true,
    "valid_sintaxis": 1,
    "institutions": [1],
    "languages": [1],
    "countries": [1],
    "material_types": [1],
    "academic_programs": [1]
  }'
```

No se envía `knowledge_areas`: el backend las deriva desde los programas académicos.

### 6.3. Crear una plataforma con API y API Key

```bash
curl -X POST http://localhost:8000/api/platforms/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Plataforma con cosecha",
    "base_api_url": "https://api.ejemplo.org",
    "api_key": "clave-secreta",
    "start_period": "2010-01-01",
    "valid_sintaxis": 1,
    "institutions": [1],
    "languages": [1],
    "countries": [1],
    "material_types": [1],
    "academic_programs": [1]
  }'
```

La clave no aparecerá en la respuesta.

### 6.4. Eliminar una API Key mediante `PATCH`

```bash
curl -X PATCH http://localhost:8000/api/platforms/1/ \
  -H "Content-Type: application/json" \
  -d '{"api_key": null}'
```

### 6.5. Registrar y verificar la URL pública

La primera verificación debe enviar la URL:

```bash
curl -X POST http://localhost:8000/api/platforms/1/check-link/ \
  -H "Content-Type: application/json" \
  -d '{"url":"https://www.ejemplo.org"}'
```

Respuesta conceptual:

```json
{
  "id": 1,
  "platform": 1,
  "url": "https://www.ejemplo.org",
  "fail_count": 0,
  "http_status_code": 200,
  "is_active": true,
  "last_check": "2026-10-05T..."
}
```

En verificaciones posteriores puede omitirse la URL y se reutiliza la última registrada:

```bash
curl -X POST http://localhost:8000/api/platforms/1/check-link/ \
  -H "Content-Type: application/json" \
  -d '{}'
```

### 6.6. Publicar una plataforma

```bash
curl -X POST http://localhost:8000/api/platforms/1/publish/
```

Para publicarse debe estar en `BORRADOR` y cumplir las reglas de completitud, incluyendo URL pública registrada, `start_period`, `valid_sintaxis` y las relaciones activas requeridas.

No se exige `base_api_url` ni `api_key` cuando la plataforma no necesita cosecha.

### 6.7. Marcar como obsoleta

```bash
curl -X POST http://localhost:8000/api/platforms/1/mark-obsolete/
```

### 6.8. Reactivar una plataforma obsoleta

```bash
curl -X POST http://localhost:8000/api/platforms/1/reactivate/
```

La plataforma regresa a `BORRADOR` y debe validarse de nuevo antes de publicarse.

### 6.9. Consultar plataformas públicas

```bash
curl http://localhost:8000/api/platforms/public/
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

Para eliminar una plataforma con relaciones de negocio, envía una explicación:

```bash
curl -X DELETE http://localhost:8000/api/platforms/1/ \
  -H "Content-Type: application/json" \
  -d '{"delete_explanation":"Plataforma retirada del repositorio"}'
```

Los registros eliminados lógicamente se consultan con:

```text
GET /api/platforms/archived/
```

Para restaurar:

```bash
curl -X POST http://localhost:8000/api/platforms/1/restore/
```

Una plataforma restaurada regresa siempre a `BORRADOR` y pierde su validación previa.

## 8. Búsqueda, ordenamiento y filtros

### 8.1. Administración

Búsqueda por nombre:

```bash
curl "http://localhost:8000/api/platforms/?search=scopus"
```

Filtros administrativos disponibles:

```text
status
requires_registration
has_access_text
valid_sintaxis
```

Ejemplo:

```bash
curl "http://localhost:8000/api/platforms/?status=publicado"
```

Ordenamiento:

```bash
curl "http://localhost:8000/api/platforms/?ordering=name"
curl "http://localhost:8000/api/platforms/?ordering=-created_at"
```

### 8.2. Consulta pública

Filtros disponibles:

```text
institution
country
language
knowledge_area
material_type
academic_program
requires_registration
has_access_text
```

Ejemplos:

```bash
curl "http://localhost:8000/api/platforms/public/?country=1"
curl "http://localhost:8000/api/platforms/public/?academic_program=1"
curl "http://localhost:8000/api/platforms/public/?knowledge_area=1"
curl "http://localhost:8000/api/platforms/public/?has_access_text=true"
```

También admite búsqueda por nombre y ordenamiento por `name`, `start_period` y `finish_period`.

### 8.3. Historial de enlaces

Filtros:

```text
platform
is_active
```

Ordenamiento:

```text
last_check
fail_count
created_at
```

Ejemplo:

```bash
curl "http://localhost:8000/api/platforms/link-check-logs/?platform=1&is_active=false"
```

## 9. Probar sin modificar la base de datos normal

La suite de Django utiliza una base de datos de pruebas separada. Para ejecutar las pruebas de `platforms`:

```bash
docker compose -f docker/docker-compose.yml exec web python manage.py test apps.platforms --keepdb
```

Estado validado de la Fase A:

```text
30/30 pruebas OK
```

Para validar también el esquema OpenAPI:

```bash
docker compose -f docker/docker-compose.yml exec web python manage.py spectacular --validate --file /tmp/schema.yml
```

Resultado validado:

```text
Warnings: 0
Errors:   0
```

## 10. Errores frecuentes

| Código | Causa típica |
| --- | --- |
| 400 | API Key sin `base_api_url`, datos inválidos, publicación incompleta, URL insegura o acción de ciclo de vida no permitida |
| 404 | ID inexistente o registro eliminado |
| 405 | Método HTTP no permitido para la ruta; por ejemplo intentar escribir directamente en `link-check-logs` o `public` |
| 500 al iniciar | Dependencias, `.env` o migraciones pendientes |

Si la API no inicia, ejecuta:

```bash
docker compose -f docker/docker-compose.yml exec web python manage.py check
```

La autenticación JWT, los permisos y la protección de escritura se implementarán en la Fase B.
