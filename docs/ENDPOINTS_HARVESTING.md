# API de Harvesting

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

```json
{
  "platforms": [1, 2],
  "frequency": "weekly",
  "start_date": "2026-10-15T02:00:00Z",
  "max_quantity": 500,
  "stop_after_minutes": 120
}
```

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

## Trigger de ejecución

Un proceso externo debe invocar periódicamente el comando de Django:

```sh
python manage.py run_scheduled_harvests
```

El comando detecta ocurrencias vencidas, crea un evento idempotente y ejecuta
un Harvest por plataforma asociada. La periodicidad efectiva de detección
depende de cada cuánto se invoque el comando. Los eventos conservan la fecha
programada y los resultados de cada Harvest.

## Cosecha OpenAlex y cursor

El servicio consulta el endpoint `/sources` de OpenAlex con `type:journal`,
normaliza los datos y llama a `apps.journal.services.create_journal`. La
deduplicación y la asociación con la plataforma se realizan mediante ese
servicio.

Harvesting usa los datos disponibles de OpenAlex para completar título, ISSN,
editorial (`host_organization_name`/`publisher`), imagen (`image_url` o
`image_thumbnail_url`), vigencia (`is_active` o `is_deprecated`), APC
(`apc_usd`/`apc_prices`), país (`country_code`) y acceso abierto (`is_oa`).
Licencia solo se usa si el payload trae explícitamente ese campo. Cuando
OpenAlex no proporciona un atributo, Harvesting lo deja sin alterar en una
revista existente; no infiere fechas de cobertura, idiomas, áreas de
conocimiento, tipos de material ni programas académicos. `homepage_url` no es
una imagen y no se guarda en `url_image`.

Al crear cada Harvest, se recupera el cursor no inicial más reciente usado para
esa plataforma. Si no existe, se inicia con `*`. Después de cada página se
persiste el `next_cursor` devuelto por OpenAlex para continuar en la siguiente
cosecha. Los resultados de una cosecha se identifican mediante
`records_added`, `records_updated` y `records_failed`; `elapsed_seconds` cuenta
la ejecución efectiva, excluyendo pausas.
