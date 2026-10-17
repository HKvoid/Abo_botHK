

## Mejoras de la colección y el mercado

La colección ahora puede consultarse con `/coleccion` o `!coleccion`, tiene paginación con botones y acepta los filtros `faltantes`, `repetidas`, `Común`, `Rara`, `Épica` y `Legendaria`. Los botones solo pueden ser utilizados por la persona que abrió esa vista.

Los sets se guardan en Neon mediante `card_sets`. Se pueden consultar con `/sets`, `!sets`, `/set <nombre>` o `!set <nombre>`. Cada set muestra las cartas obtenidas y faltantes, junto con el progreso del usuario. Las cartas creadas desde el dashboard pueden asignarse a un set mediante el campo `Set / colección`; si el set no existía, el dashboard lo crea automáticamente.

El mercado muestra ahora el vendedor, incluye botones para comprar una copia y para consultar al vendedor. La compra por botón usa la misma operación centralizada y transacción atómica que las operaciones de mercado, por lo que valida saldo, disponibilidad y que no se compre la propia publicación.
