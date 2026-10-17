

## Fase de progresión y administración

Abo Cards ahora incluye `/perfil` y `!perfil`, con nivel, XP, saldo, colección, valor total, sobres abiertos y progreso de pity. Los usuarios ganan XP al abrir sobres, reclamar el diario y completar Tradeos; el nivel se calcula automáticamente por bloques de 1,000 XP.

El sistema pity garantiza una carta Rara o superior después de cinco sobres sin obtener una carta de esa categoría y una carta Épica o Legendaria después de quince sobres sin obtener una carta épica. El contador aparece en el perfil y se reinicia al obtener la rareza correspondiente.

Los mensajes de sobre abierto, subida de nivel, pity y set completado se pueden editar desde el panel Abo Cards del dashboard. Admiten variables como `{cards}`, `{balance}`, `{level}`, `{xp}`, `{set_name}` y `{reward}`.

Los Tradeos se guardan en Neon desde el momento en que se crean. Sus ofertas, confirmaciones, canal y participantes se restauran después de reiniciar Abo; cancelar y completar un Tradeo actualizan su estado persistente.

Las herramientas administrativas disponibles para usuarios con permiso de gestionar el servidor son `/cartas_regalar`, `/cartas_retirar`, `/cartas_saldo` y `/cartas_resetear`. También existe el acceso `!cartas`, con subcomandos `regalar`, `retirar`, `saldo` y `resetear`. Cada acción administrativa se registra en `card_admin_audit`.
