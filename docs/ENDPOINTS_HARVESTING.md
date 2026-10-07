# API de Cosecha (Harvesting)

Esta guía documenta exhaustivamente todos los endpoints del módulo `apps/harvesting`, sus métodos HTTP, atributos obligatorios y opcionales, opciones permitidas, reglas de negocio e inalterabilidad.

---

## 1. Visión General del Módulo

El módulo de cosecha se compone de dos conceptos fundamentales:

1. **`Schedule` (Programación)**:
   - Representa la planificación periódica de recolección para una plataforma académica (ej. OpenAlex).
   - El usuario solo configura plataforma, frecuencia y límites por ejecución (`max_quantity` / `stop_after_minutes`).
   - `start_date`, `finish_date` y `duration` son de **solo lectura**: los escribe el motor cuando corre una cosecha asociada.
   - No hay flag `is_active`. Para dejar de programar se usa el borrado lógico (`DELETE`); para reactivar, `restore`.
   - **Es editable** en los campos de configuración: CRUD estándar (`GET`, `POST`, `PUT`, `PATCH`, `DELETE` con borrado lógico) y restauración (`restore`).

2. **`Harvest` (Cosecha / Ejecución)**:
   - Representa una ejecución puntual de recolección de revistas (`Journal`) para una plataforma correspondiente a un Schedule (o manual).
   - **Es estrictamente inalterable**: Una vez creada o finalizada, sus datos y resultados no pueden ser modificados por clientes externos (`PUT`, `PATCH` y `DELETE` responden `405 Method Not Allowed`).
   - El avance de los contadores (`records_added`, `records_updated`, `records_failed`) y el cursor de la API (`api_cursor`) es administrado exclusivamente por el motor de recolección.
   - Paginación automática por cursor: Si no se suministra un cursor, se recupera el `api_cursor` más reciente de cosechas previas de esa plataforma para evitar registros duplicados.
   - Deduplicación: Se integra con el servicio `create_journal` de `apps.journal.services`, asegurando deduplicación por ISSN y asociación automática con `SharedJournalPlatform`.

---

## 2. Convenciones de Campos Comunes

### Campos de Auditoría (Solo Lectura)

Todos los modelos heredan de `AuditableModel` y presentan los siguientes campos gestionados automáticamente por el backend:

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `id` | Entero | Identificador único del registro (autoincremental). |
| `created_by` | Entero | ID del usuario que creó el registro. |
| `created_at` | DateTime (ISO-8601) | Fecha y hora de creación del registro. |
| `updated_by` | Entero / null | ID del último usuario que actualizó el registro. |
| `updated_at` | DateTime (ISO-8601) / null | Fecha y hora de la última actualización. |
| `deleted_by` | Entero / null | ID del usuario que aplicó borrado lógico. |
| `deleted_at` | DateTime (ISO-8601) / null | Fecha y hora del borrado lógico (null si está activo). |
| `delete_explanation` | String / null | Justificación obligatoria requerida al eliminar. |

---

## 3. Endpoints de Programaciones (`Schedule`)

Ruta base: `/api/harvesting/schedules/`

| Método | Ruta | Descripción | Código Éxito |
| --- | --- | --- | --- |
| `GET` | `/api/harvesting/schedules/` | Listar programaciones activas (con filtros y paginación) | `200 OK` |
| `POST` | `/api/harvesting/schedules/` | Crear una nueva programación | `201 Created` |
| `GET` | `/api/harvesting/schedules/{id}/` | Consultar detalle de una programación | `200 OK` |
| `PUT` | `/api/harvesting/schedules/{id}/` | Reemplazar completamente una programación | `200 OK` |
| `PATCH` | `/api/harvesting/schedules/{id}/` | Actualizar parcialmente una programación | `200 OK` |
| `DELETE` | `/api/harvesting/schedules/{id}/` | Borrado lógico de una programación | `200 OK` / `204 No Content` |
| `GET` | `/api/harvesting/schedules/archived/` | Listar programaciones archivadas (eliminadas) | `200 OK` |
| `POST` | `/api/harvesting/schedules/{id}/restore/` | Restaurar una programación eliminada | `200 OK` |
| `POST` | `/api/harvesting/schedules/{id}/execute/` | Crear y ejecutar de inmediato una cosecha desde la programación | `201 Created` |

### Parámetros de Consulta (Query Params) en `GET /api/harvesting/schedules/`

- `platform`: Entero. Filtra por ID de la plataforma.
- `frequency`: String. Filtra por frecuencia (`once`, `daily`, `weekly`, `monthly`).
- `start_date_after`: DateTime ISO-8601. Filtra por inicio de la última cosecha asociada, en o después de la fecha.
- `start_date_before`: DateTime ISO-8601. Filtra por inicio de la última cosecha asociada, en o antes de la fecha.
- `ordering`: String. Ordenamiento por campos permitidos (`start_date`, `-start_date`, `finish_date`, `-finish_date`, `created_at`, `-created_at`).
- `page` y `page_size`: Paginación.

---

### Especificación de Atributos del Cuerpo (`Schedule`)

Aplica para `POST`, `PUT` y `PATCH`. El usuario **no** envía fechas ni duración.

| Atributo | Obligatoriedad | Tipo | Opciones / Formato admitido | Descripción y Reglas de Negocio |
| --- | --- | --- | --- | --- |
| `platform` | **Obligatorio** al crear | Entero (ID) | ID existente en `apps.platforms.Platform` | Plataforma académica a cosechar. |
| `frequency` | **Obligatorio** al crear | String | `once`, `daily`, `weekly`, `monthly` | Periodicidad de ejecución programada. Por defecto `once`. |
| `max_quantity` | **Condicional** | Entero / null | Entero positivo `>= 1` | Límite por defecto de revistas a procesar en cada cosecha. Obligatorio si no se define `stop_after_minutes`. |
| `stop_after_minutes` | **Condicional** | Entero / null | Entero positivo `>= 1` | Límite de tiempo en minutos por defecto para cada cosecha. Obligatorio si no se define `max_quantity`. |

Si el cliente envía `start_date`, `finish_date`, `duration` o `is_active`, esos valores se ignoran (no forman parte de la entrada writable).

### Atributos de Solo Lectura de `Schedule`

| Atributo | Tipo | Descripción |
| --- | --- | --- |
| `start_date` | DateTime / null | Momento en que **inició** la última cosecha asociada. Lo setea el motor al arrancar la recolección. |
| `finish_date` | DateTime / null | Momento en que **terminó** esa cosecha (completada, fallida o cancelada tras haber arrancado). |
| `duration` | Intervalo / null | Tiempo real que tardó esa recolección (`finish_date - start_date`). No es un límite que configure el usuario; el tope de tiempo es `stop_after_minutes`. |

#### Ejemplo de Petición (`POST /api/harvesting/schedules/`):
```json
{
  "platform": 1,
  "frequency": "weekly",
  "max_quantity": 500,
  "stop_after_minutes": 120
}
```

#### Ejemplo de Respuesta (`201 Created`):
```json
{
  "id": 1,
  "created_by": 0,
  "created_at": "2026-10-06T20:15:00Z",
  "updated_by": null,
  "updated_at": null,
  "deleted_by": null,
  "deleted_at": null,
  "delete_explanation": null,
  "platform": 1,
  "platform_name": "openalex",
  "frequency": "weekly",
  "max_quantity": 500,
  "stop_after_minutes": 120,
  "start_date": null,
  "finish_date": null,
  "duration": null
}
```

---

## 4. Endpoints de Ejecución de Cosechas (`Harvest`)

Ruta base: `/api/harvesting/harvests/`

> [!IMPORTANT]
> **Principio de Inalterabilidad**: Los resultados de una cosecha son inalterables. Los métodos `PUT`, `PATCH` y `DELETE` están completamente deshabilitados y devuelven `405 Method Not Allowed`. Para reanudar o reintentar una recolección se utilizan las acciones explícitas de control (`execute`, `cancel`, `pause`, `resume`, `retry`).

| Método | Ruta | Descripción | Código Éxito |
| --- | --- | --- | --- |
| `GET` | `/api/harvesting/harvests/` | Listar historial inalterable de cosechas (filtros y paginación) | `200 OK` |
| `POST` | `/api/harvesting/harvests/` | Solicitar una nueva cosecha | `201 Created` |
| `GET` | `/api/harvesting/harvests/{id}/` | Consultar detalle y métricas de una cosecha | `200 OK` |
| `PUT` | `/api/harvesting/harvests/{id}/` | **Bloqueado**. Responde 405 Method Not Allowed | `405` |
| `PATCH` | `/api/harvesting/harvests/{id}/` | **Bloqueado**. Responde 405 Method Not Allowed | `405` |
| `DELETE` | `/api/harvesting/harvests/{id}/` | **Bloqueado**. Responde 405 Method Not Allowed | `405` |
| `POST` | `/api/harvesting/harvests/{id}/execute/` | Ejecutar recolección activa de una cosecha pendiente | `200 OK` |
| `POST` | `/api/harvesting/harvests/{id}/cancel/` | Cancelar una cosecha en estado pendiente o en ejecución | `200 OK` |
| `POST` | `/api/harvesting/harvests/{id}/pause/` | Pausar temporalmente una cosecha en ejecución | `200 OK` |
| `POST` | `/api/harvesting/harvests/{id}/resume/` | Reanudar una cosecha pausada desde su último cursor | `200 OK` |
| `POST` | `/api/harvesting/harvests/{id}/retry/` | Crear una nueva cosecha a partir del cursor de una fallida | `201 Created` |

### Parámetros de Consulta (Query Params) en `GET /api/harvesting/harvests/`

- `platform`: Entero. ID de la plataforma.
- `schedule`: Entero. ID de la programación asociada.
- `state`: String. Estado de la cosecha (`pending`, `running`, `completed`, `failed`, `cancelled`, `paused`).
- `created_at_after`: DateTime ISO-8601. Creada a partir de esta fecha.
- `created_at_before`: DateTime ISO-8601. Creada hasta esta fecha.
- `started_at_after`: DateTime ISO-8601. Iniciada a partir de esta fecha.
- `started_at_before`: DateTime ISO-8601. Iniciada hasta esta fecha.
- `finished_at_after`: DateTime ISO-8601. Finalizada a partir de esta fecha.
- `finished_at_before`: DateTime ISO-8601. Finalizada hasta esta fecha.
- `ordering`: String. Orden (`created_at`, `-created_at`, `started_at`, `records_added`).

---

### Especificación de Atributos del Cuerpo (`Harvest`)

Aplica para `POST /api/harvesting/harvests/`:

| Atributo | Obligatoriedad | Tipo | Opciones / Formato admitido | Descripción y Reglas de Negocio |
| --- | --- | --- | --- | --- |
| `platform` | **Obligatorio** (salvo que se indique `schedule`) | Entero (ID) | ID existente en `Platform` | Plataforma de la que se recolectarán los registros. No puede tener otra cosecha activa (`pending`, `running`, `paused`) en simultáneo. |
| `schedule` | Opcional | Entero (ID) / null | ID existente en `Schedule` | Programación asociada. Si se indica, hereda automáticamente la plataforma y los límites configurados en la programación. |
| `max_quantity` | **Condicional** | Entero / null | Entero positivo `>= 1` | Cantidad máxima de revistas a procesar. Es obligatorio definir al menos `max_quantity` o `stop_after_minutes`. |
| `stop_after_minutes` | **Condicional** | Entero / null | Entero positivo `>= 1` | Tiempo máximo en minutos antes de detener la cosecha. Obligatorio si no se define `max_quantity`. |

> [!NOTE]
> **Gestión Automática del Cursor (`api_cursor`)**:
> El usuario **nunca** debe enviar el `api_cursor`. El sistema lo gestiona de forma 100% autónoma:
> - Al crear la solicitud, el backend recupera automáticamente el cursor más reciente registrado en las cosechas previas de esa plataforma (o `*` si es la primera vez).
> - Si el cliente envía un valor en `api_cursor`, este es completamente ignorado.
> - Durante la ejecución, el motor de recolección actualiza el cursor tras cada lote procesado.

### Atributos de Solo Lectura devueltos por `Harvest`

Estos atributos no pueden enviarse ni modificarse en el cuerpo de las peticiones:

| Atributo | Tipo | Valores posibles | Descripción |
| --- | --- | --- | --- |
| `api_cursor` | String | Token alfanumérico o `*` | Cursor o token de paginación de la API externa recuperado y actualizado automáticamente por el backend. |
| `state` | String | `pending`, `running`, `completed`, `failed`, `cancelled`, `paused` | Estado del ciclo de vida de la cosecha. Inicia en `pending`. |
| `records_added` | Entero | `>= 0` | Cantidad de revistas nuevas registradas en la base de datos. |
| `records_updated` | Entero | `>= 0` | Cantidad de revistas preexistentes (mismo ISSN) actualizadas y vinculadas. |
| `records_failed` | Entero | `>= 0` | Cantidad de entradas que no contenían ISSN válido o fallaron validación. |
| `started_at` | DateTime / null | ISO-8601 | Fecha y hora en la que inició efectivamente el proceso de recolección. |
| `finished_at` | DateTime / null | ISO-8601 | Fecha y hora en la que concluyó, falló o se canceló la recolección. No se setea al pausar. |
| `duration` | Intervalo / null | `HH:MM:SS` | Tiempo real de la recolección (`finished_at - started_at`). Calculado; el usuario no lo envía. |
| `error_message` | String / null | Texto | Detalle del error arrojado si el estado final es `failed`. |

#### Ejemplo de Creación (`POST /api/harvesting/harvests/`):
```json
{
  "platform": 1,
  "max_quantity": 100,
  "stop_after_minutes": 30
}
```

#### Ejemplo de Respuesta (`201 Created`):
```json
{
  "id": 10,
  "created_by": 0,
  "created_at": "2026-10-06T20:20:00Z",
  "updated_by": null,
  "updated_at": null,
  "deleted_by": null,
  "deleted_at": null,
  "delete_explanation": null,
  "platform": 1,
  "platform_name": "openalex",
  "schedule": null,
  "schedule_frequency": null,
  "api_cursor": "Ils5ODg5OTQsICdodHRwczovL29wZW5hbGV4Lm9yZy9TNDMwNjUwMDUwNyddIg==",
  "max_quantity": 100,
  "stop_after_minutes": 30,
  "state": "pending",
  "records_added": 0,
  "records_updated": 0,
  "records_failed": 0,
  "started_at": null,
  "finished_at": null,
  "duration": null,
  "error_message": null
}
```

---

## 5. Acciones Especiales de Control de Cosecha

### 5.1 Ejecutar Cosecha (`POST /api/harvesting/harvests/{id}/execute/`)
Dispara la recolección en OpenAlex para una cosecha en estado `pending`.
- **Cuerpo opcional**:
  ```json
  {
    "batch_size": 50
  }
  ```
  - `batch_size`: Entero entre 1 y 100 (opcional, valor por defecto: 50). Define cuántos registros pide por petición a OpenAlex.
- **Respuesta (`200 OK`)**: Devuelve el objeto de la cosecha con sus contadores actualizados y estado final `completed` (o `failed`).

### 5.2 Cancelar Cosecha (`POST /api/harvesting/harvests/{id}/cancel/`)
Detiene y marca la cosecha con estado `cancelled`.
- No requiere cuerpo.
- **Respuesta (`200 OK`)**: Estado actualizado a `cancelled`.

### 5.3 Pausar Cosecha (`POST /api/harvesting/harvests/{id}/pause/`)
Pausa una cosecha activa en estado `running`.
- No requiere cuerpo.
- **Respuesta (`200 OK`)**: Estado actualizado a `paused`.

### 5.4 Reanudar Cosecha (`POST /api/harvesting/harvests/{id}/resume/`)
Reanuda una cosecha previamente pausada (`paused`) manteniendo el `api_cursor` donde quedó.
- No requiere cuerpo.
- **Respuesta (`200 OK`)**: Retoma la recolección y devuelve el estado actualizado.

### 5.5 Reintentar Cosecha (`POST /api/harvesting/harvests/{id}/retry/`)
Permite reintentar una cosecha que haya quedado en estado `failed` o `cancelled`.
- **Comportamiento**: Para garantizar la inalterabilidad histórica, no sobrescribe el registro anterior; crea una **nueva cosecha** que hereda el último `api_cursor` alcanzado y los parámetros de la original.
- **Respuesta (`201 Created`)**: Nueva cosecha creada en estado `pending`.

---

## 6. Automatización de Programaciones y Cron

Para activar periódicamente las cosechas configuradas en `Schedule`, el módulo incluye el comando de gestión de Django:

```bash
python manage.py run_scheduled_harvests
```

### Comportamiento del Comando:
1. Inspecciona todas las programaciones no eliminadas lógicamente.
2. Valida si la programación ha alcanzado su momento de ejecución según su frecuencia (`once`, `daily`, `weekly`, `monthly`).
3. Comprueba que la plataforma no tenga ya una cosecha activa en curso.
4. Genera automáticamente el registro `Harvest` correspondiente con los límites configurados.
5. Ejecuta la recolección en OpenAlex actualizando el cursor y asociando las revistas.

### Configuración en Crontab del Servidor:
Para ejecutar cada hora (o cada minuto):
```cron
* * * * * docker compose -f docker/docker-compose.yml run --rm web python manage.py run_scheduled_harvests
```
*(o ejecutándolo dentro del contenedor según la orquestación implementada).*
