# Abo

Bot de Discord organizado por áreas funcionales, con comandos slash, tickets y mensajes configurables.

## Estructura

- `bot.py`: arranque, conexión a Neon, eventos y carga/sincronización de cogs.
- `core.py`: permisos, memoria de IA y funciones compartidas.
- `database.py`: esquema PostgreSQL, pool de conexiones y migración única desde SQLite.
- `cogs/`: comandos de colores, moderación, purga, warns, tickets, bienvenidas/despedidas, reset y ayuda.

## Configuración y ejecución

Configura estas variables en el entorno donde alojes el bot:

- `TOKEN`: token del bot de Discord.
- `GROQ_API_KEY`: clave de Groq.
- `DATABASE_URL`: cadena PostgreSQL del proyecto Neon. Usa la cadena de conexión de Neon y mantenla como secreto; no la publiques ni la subas al repositorio.

Para desarrollo local, copia `.env.example` a `.env` y completa las variables; `python-dotenv` las cargará al arrancar. En producción, configura los secretos directamente en el proveedor de alojamiento. Instala `requirements.txt` y ejecuta `python bot.py`. Al iniciar, Abo crea las tablas en Neon y verifica la conexión cifrada. Si el archivo antiguo `abo_memoria.db` está presente junto a `bot.py`, importa una sola vez memoria, warns, roles de color y excepciones AFK; conserva el archivo original y no lo borra. Si el bot está alojado en otra plataforma, copia allí ese archivo antes del primer inicio con Neon para migrar sus datos locales.

`DATABASE_URL` no se incluye en este paquete. Añádela en la sección de variables/secrets del proveedor donde ejecutes el bot. `.env.example` es una plantilla y no contiene credenciales reales.

## Sistema de tickets

1. Usa `/ticket_config` para elegir la categoría de tickets, el rol de staff y el canal privado de registros.
2. Usa `/ticket_panel` para publicar el panel. Los miembros completan un formulario y Abo crea un canal privado.
3. El staff puede reclamar cada ticket. La persona que lo abrió o el staff pueden cerrarlo.
4. Al cerrar, Abo genera una transcripción HTML, la conserva dentro de Neon y la envía al canal de registros. Usa `/ticket_transcript` para descargarla más tarde. Los datos y el estado del ticket quedan en Neon; el canal no se elimina automáticamente.

Las vistas y botones son persistentes, así que continúan funcionando después de reiniciar el bot. También se guarda en Neon la lista de candidatos del último `/scan` AFK.

## Bienvenidas y despedidas

- `/welcome_config` y `/leave_config` configuran canal, texto e imagen opcional mediante una URL pública `http://` o `https://`.
- Variables: `{user}`, `{username}`, `{server}` y `{member_count}`.
- `/welcome_off` y `/leave_off` desactivan cada evento sin borrar su configuración guardada.

Quien configure estos comandos debe tener el permiso **Gestionar servidor**. El bot necesita el intent **Server Members** habilitado en el Developer Portal de Discord para recibir eventos de entrada y salida.
