# Abo Cards

## Fase 1: colección

- `/sobre`: compra un sobre de 3 cartas por 100 Abo Coins.
- `/coleccion [usuario]`: muestra el álbum y su valor base.
- `/carta <nombre>`: muestra rareza, valor, copias e imagen de la carta.
- `/diario_cartas`: reclama monedas diarias con racha.
- `/saldo_cartas`: consulta el saldo.

Cada usuario empieza con 500 Abo Coins al usar el sistema por primera vez. Las cartas se guardan por servidor, así que cada comunidad tiene su propia colección.

## Fase 2: economía social

- `/intercambiar_carta`: intercambio directo de dos cartas entre dos miembros.
- `/mercado_publicar`: publica copias a un precio por unidad.
- `/mercado`: consulta publicaciones activas.
- `/mercado_comprar`: compra una publicación.
- `/mercado_cancelar`: retira una publicación propia y recupera las copias restantes.
- `/ranking_cartas`: ranking por valor base de colección.

## Catálogo inicial

El catálogo inicial usa las imágenes proporcionadas en `assets/cards/`, con 17 cartas entre comunes, raras, épicas y legendarias. El catálogo se sincroniza automáticamente en Neon cada vez que inicia Abo.

## Economía y seguridad

- Las operaciones de sobres, intercambio y mercado usan transacciones PostgreSQL.
- Las cantidades se bloquean antes de transferirse para evitar duplicaciones por acciones simultáneas.
- Las publicaciones del mercado retiran las copias del inventario hasta que se venden o cancelan.
- Las cartas y monedas están separadas por `guild_id`.
- El sistema todavía no incluye batallas, efectos competitivos ni cartas de usuarios reales; eso queda para una fase posterior.
