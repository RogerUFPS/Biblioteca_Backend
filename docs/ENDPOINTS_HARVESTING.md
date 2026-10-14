# API de Harvesting

<<<<<<< HEAD
Harvesting mantiene la configuración de cosechas y expone el historial de sus
ejecuciones. Cada cosecha programada genera un `ScheduleEvent`; cada evento crea
un `Harvest` por cada plataforma vinculada al Schedule. Harvest y ScheduleEvent
son registros de seguimiento administrados por el sistema, no solicitudes
editables por clientes.

## Programaciones

Ruta base: `/api/harvesting/schedules/`

| Método | Ruta | Descripción |
| --- | --- | --- |
| `GET` | `/` | Listar programaciones activas |
| `POST` | `/` | Crear una programación |
| `GET` | `/{id}/` | Consultar una programación |
| `PUT` / `PATCH` | `/{id}/` | Actualizar configuración |
| `DELETE` | `/{id}/` | Eliminar o desactivar la programación |
| `GET` | `/archived/` | Consultar programaciones archivadas |
| `POST` | `/{id}/restore/` | Restaurar una programación |

Ejemplo de creación:
=======
Harvesting administra las programaciones de cosecha y expone los eventos y
ejecuciones generados por el sistema. Cada evento programado crea un Harvest por
cada plataforma asociada al Schedule. Los clientes pueden administrar
programaciones y consultar eventos/Harvest; los registros de ejecución no se
crean ni actualizan directamente.

Todas las rutas tienen el prefijo `/api/harvesting`.

## Convenciones de consulta

Los listados paginados aceptan `page` y `page_size` (`page_size` máximo: 100) y
responden con `current_page`, `total_pages`, `page_size`, `total_items`,
`next`, `previous` y `results`. Cada elemento de `results` incluye
`item_number`.

Los listados admiten los parámetros de filtro indicados en cada sección.
También admiten `search` cuando se documenta como búsqueda, y `ordering` para
los campos de ordenamiento disponibles.

## Programaciones (`/schedules/`)

| Método | Ruta | Request body | Respuesta |
| --- | --- | --- | --- |
| `GET` | `/` | Ninguno. Acepta filtros y paginación. | `200`: lista paginada de programaciones activas. |
| `POST` | `/` | Requerido: objeto `Schedule`. | `201`: programación creada. |
| `GET` | `/{id}/` | Ninguno. | `200`: detalle de la programación. |
| `PUT` | `/{id}/` | Requerido: objeto `Schedule` completo. | `200`: programación actualizada. |
| `PATCH` | `/{id}/` | Opcional: objeto con los campos a actualizar. | `200`: programación actualizada. |
| `DELETE` | `/{id}/` | Normalmente ninguno. Si hay registros dependientes, enviar `delete_explanation`. | `204` si se elimina físicamente; `200` si se archiva lógicamente. |
| `GET` | `/archived/` | Ninguno. Acepta filtros y paginación. | `200`: lista paginada de programaciones archivadas. |
| `POST` | `/{id}/restore/` | Ninguno. | `200`: programación restaurada; `404` si no existe archivada. |
| `POST` | `/run-due/` | Ninguno. | `200`: arreglo de Harvest procesados. |

### Crear o actualizar un Schedule

El body admite estos campos:

| Campo | Tipo | Requerido | Descripción |
| --- | --- | --- | --- |
| `platforms` | `integer[]` | Sí al crear; opcional en `PATCH` | IDs de plataformas cosechables. Lista no vacía. |
| `frequency` | `string` | No | `once`, `daily`, `weekly` o `monthly`. |
| `start_date` | `datetime` | Sí al crear | Fecha y hora ISO-8601 de la primera ejecución. |
| `max_quantity` | `integer` | Debe enviarse este o `stop_after_minutes` | Límite de registros por Harvest; debe ser mayor que cero. |
| `stop_after_minutes` | `integer` | Debe enviarse este o `max_quantity` | Límite de duración por Harvest; debe ser mayor que cero. |

Si se envían ambos límites, la cosecha se detiene al alcanzar primero cualquiera
de ellos. Solo se aceptan plataformas con `is_harvestable=true`; si una
plataforma asociada se deshabilita posteriormente, su Harvest se registra como
fallido y no inicia la cosecha.

Ejemplo de `POST /schedules/`:
>>>>>>> production

```json
{
  "platforms": [1, 2],
  "frequency": "weekly",
  "start_date": "2026-10-15T02:00:00Z",
  "max_quantity": 500,
  "stop_after_minutes": 120
}
```

<<<<<<< HEAD
- `platforms`: lista no vacía de IDs de plataformas.
- `frequency`: `once`, `daily`, `weekly` o `monthly`.
- `start_date`: fecha y hora de la primera ejecución; las siguientes se calculan
  desde esa ocurrencia.
- Debe configurarse `max_quantity`, `stop_after_minutes` o ambos. Al definir
  ambos, la ejecución finaliza al alcanzar primero cualquiera de los límites.
- Los límites son por Harvest/plataforma.

## Eventos programados

Ruta base: `/api/harvesting/events/`

| Método | Ruta | Descripción |
| --- | --- | --- |
| `GET` | `/` | Listar eventos |
| `GET` | `/{id}/` | Consultar un evento y los IDs de sus Harvest |

El evento registra la ocurrencia programada, estado (`pending`, `running`,
`completed`, `failed`), fechas de ejecución, errores y cosechas asociadas.
Admite filtros `schedule` y `state`.

## Historial de cosechas

Ruta base: `/api/harvesting/harvests/`

| Método | Ruta | Descripción |
| --- | --- | --- |
| `GET` | `/` | Listar Harvest |
| `GET` | `/{id}/` | Consultar el resultado de un Harvest |
| `POST` | `/{id}/pause/` | Solicitar la pausa de una cosecha |
| `POST` | `/{id}/resume/` | Reanudar una cosecha pausada |

Los Harvest no se pueden crear ni editar directamente. El sistema gestiona su
cursor, estado, contadores, tiempos y mensajes de error. La pausa de una
cosecha en ejecución es cooperativa: responde `202 Accepted` con estado
`pausing` y termina de procesar la página OpenAlex en curso antes de guardar el
cursor y pasar a `paused`. Las cosechas `pending` se pausan inmediatamente con
`200 OK`. Reanudar solo es posible desde `paused`; el servicio continúa desde
el cursor guardado. El límite de tiempo acumula solo el tiempo de ejecución
activa y no cuenta el tiempo que la cosecha estuvo pausada.

=======
La respuesta incluye los campos enviados, auditoría y `platform_names`:

```json
{
  "id": 12,
  "platforms": [1, 2],
  "platform_names": ["Plataforma A", "Plataforma B"],
  "frequency": "weekly",
  "start_date": "2026-10-15T02:00:00Z",
  "max_quantity": 500,
  "stop_after_minutes": 120
}
```

### Filtrar y ordenar programaciones

`GET /schedules/` y `GET /schedules/archived/` aceptan:

| Parámetro | Descripción |
| --- | --- |
| `platform` | ID de una plataforma asociada. |
| `frequency` | Frecuencia (`once`, `daily`, `weekly`, `monthly`). |
| `start_date_after` | `start_date` mayor o igual a la fecha ISO-8601 indicada. |
| `start_date_before` | `start_date` menor o igual a la fecha ISO-8601 indicada. |
| `search` | Busca por nombre de plataforma. |
| `ordering` | `created_at` o `start_date`; prefijo `-` para descendente. |
| `page`, `page_size` | Paginación. |

### Eliminación de una programación

Si la programación tiene registros dependientes, enviar un body como:

```json
{
  "delete_explanation": "Motivo de la desactivación"
}
```

La explicación debe ser una cadena no vacía de hasta 500 caracteres. Cuando no
hay dependencias, no se requiere body y el registro se elimina físicamente.

### Ejecutar programaciones vencidas (`run-due`)

`POST /schedules/run-due/` evalúa las programaciones activas vencidas e inicia
las ejecuciones correspondientes. No requiere body ni parámetros. Se puede
invocar manualmente; responde con un arreglo de objetos `Harvest` (puede ser
`[]` cuando no había cosechas por ejecutar).

Cada elemento usa la representación de Harvest descrita en la sección
[Ejecuciones](#ejecuciones-harvests). Una ejecución individual fallida se
devuelve dentro del arreglo con `state: "failed"` y su `error_message`; el
resultado del endpoint no implica que todas las ejecuciones hayan sido exitosas.

## Eventos (`/events/`)

Los eventos son registros generados por el sistema y son de solo lectura.

| Método | Ruta | Request body | Respuesta |
| --- | --- | --- | --- |
| `GET` | `/` | Ninguno. Acepta filtros y paginación. | `200`: lista paginada de eventos. |
| `GET` | `/{id}/` | Ninguno. | `200`: detalle del evento y los IDs de sus Harvest. |

Filtros para `GET /events/`:

| Parámetro | Descripción |
| --- | --- |
| `schedule` | ID de la programación asociada. |
| `state` | Estado: `pending`, `running`, `completed` o `failed`. |
| `ordering` | `scheduled_for`, `started_at` o `finished_at`; prefijo `-` para descendente. |
| `page`, `page_size` | Paginación. |

El detalle contiene `schedule`, `scheduled_for`, `state`, `started_at`,
`finished_at`, `error_message` y `harvests`.

## Ejecuciones (`/harvests/`)

Los Harvest son registros administrados por el sistema: no se pueden crear,
editar ni eliminar directamente.

Al cosechar desde OpenAlex, cada Source se envía a `create_journal()` con el ID
de la plataforma del Harvest como `platform_id` y `homepage_url` como
`journal_url`. La URL es obligatoria en Journal; si OpenAlex no la entrega o no
pasa su validación, el Source se contabiliza en `records_failed`. No se envían
los campos `active` ni `license`: el estado de publicación/validación se
gestiona desde Journal y las licencias no se importan en este flujo; sus
asociaciones se administran mediante el catálogo de licencias.

| Método | Ruta | Request body | Respuesta |
| --- | --- | --- | --- |
| `GET` | `/` | Ninguno. Acepta filtros, búsqueda y paginación. | `200`: lista paginada de Harvest. |
| `GET` | `/{id}/` | Ninguno. | `200`: detalle del Harvest. |
| `POST` | `/{id}/pause/` | Ninguno. | `200`: pausado; `202`: pausa solicitada mientras termina la página actual; `400`: estado incompatible. |
| `POST` | `/{id}/resume/` | Ninguno. | `200`: Harvest reanudado; `400`: no estaba pausado; `500`: error al reanudar. |

Filtros para `GET /harvests/`:

| Parámetro | Descripción |
| --- | --- |
| `platform` | ID de la plataforma cosechada. |
| `schedule` | ID de la programación asociada. |
| `state` | `pending`, `running`, `pausing`, `completed`, `failed`, `cancelled` o `paused`. |
| `created_at_after`, `created_at_before` | Rango de creación (ISO-8601). |
| `started_at_after`, `started_at_before` | Rango de inicio (ISO-8601). |
| `finished_at_after`, `finished_at_before` | Rango de finalización (ISO-8601). |
| `search` | Busca por nombre de plataforma. |
| `ordering` | `created_at`, `started_at`, `finished_at` o `records_added`; prefijo `-` para descendente. |
| `page`, `page_size` | Paginación. |

El serializer de Harvest incluye `platform`, `platform_name`, `schedule`,
`event`, `schedule_frequency`, límites, `api_cursor`, estado, contadores,
tiempos, `duration` y `error_message`. Todos sus campos son de solo lectura.

La pausa de una cosecha en ejecución es cooperativa: responde `202 Accepted`
con estado `pausing` y termina de procesar la página OpenAlex en curso antes de
guardar el cursor y pasar a `paused`. Las cosechas `pending` se pausan
inmediatamente con `200 OK`. Reanudar solo es posible desde `paused` y continúa
desde el cursor guardado. El límite de tiempo acumula el tiempo de ejecución
activa, excluyendo los periodos pausados.
>>>>>>> production
