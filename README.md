# Abo

Bot de Discord organizado por áreas funcionales y comandos slash.

## Estructura

- `bot.py`: arranque, eventos y carga/sincronización de cogs.
- `core.py`: configuración, SQLite, memoria de IA, comprobaciones y utilidades compartidas.
- `cogs/`: comandos divididos por colores, moderación, purga, warns, reset y ayuda.

## Ejecución

Configura las variables `TOKEN` y `GROQ_API_KEY`, instala `requirements.txt` y ejecuta `python bot.py`.
