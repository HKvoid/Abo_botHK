# Enlace con Abo Dashboard

Este proyecto es el bot de Discord. El dashboard es un proyecto separado y se enlaza sin importar código del bot:

- Ambos usan exactamente el mismo `DATABASE_URL` de Neon.
- El dashboard usa `dashboard_schema.sql`, que replica el esquema de `database.py`.
- Configura `DASHBOARD_SECRET` solamente en el proyecto del dashboard.
- El dashboard lee y escribe `guild_settings`, `warns`, `tickets`, `purge_exceptions`, `color_roles` y `memory`, las mismas tablas que usa este bot.

Despliega este proyecto como worker ejecutando `python bot.py` y el dashboard como servicio web separado.

## Múltiples paneles

Crea y guarda los diseños desde el dashboard. En Discord ejecuta `/ticket_panel`, elige el canal y selecciona el panel por nombre en el campo opcional `panel`. Cada panel usa botones persistentes diferentes y continúa funcionando después de reiniciar el bot.

## Estilos, imagen y privacidad

Cada botón admite estilo oscuro, verde vivo, rojo vivo o azul, y cada panel puede llevar una imagen pública en su embed. Al reclamar un ticket, el bot oculta el canal al rol general de staff y lo deja visible para el creador y el responsable. Al cerrarlo, guarda primero la transcripción y después elimina el canal automáticamente; si Discord no permite borrarlo, conserva el canal y registra el error.
