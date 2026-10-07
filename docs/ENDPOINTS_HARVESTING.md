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

