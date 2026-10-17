

## Sistema de personajes pixel art

El catálogo ya no usa plantillas visuales de cartas. Cada entrada representa un personaje y se muestra con su imagen pixel art como archivo adjunto de Discord, acompañada por un embed configurable.

El embed incluye:

- Nombre del personaje.
- Rareza.
- Valor en Abo Coins.
- Cantidad que posee el usuario.
- Descripción o historia personalizada.
- Stats y características personalizadas.
- Color de embed configurable.

Los assets iniciales fueron reemplazados por los 17 personajes del paquete `abo.zip`. Al primer arranque después de esta actualización, Abo limpia una sola vez las imágenes antiguas almacenadas en Neon. En los siguientes arranques no borra imágenes nuevas que se suban desde el dashboard.

### Editor flexible del dashboard

El editor de personajes permite cambiar:

- Slug y nombre visible.
- Imagen del personaje.
- Rareza.
- Color decimal del embed.
- Peso de aparición en sobres.
- Valor base.
- Set o colección.
- Descripción de hasta 4,000 caracteres.
- Hasta 30 stats con formato JSON libre.
- Etiquetas separadas por comas.

Ejemplo de stats:

```json
{
  "Vida": "100",
  "Ataque": "25",
  "Clase": "Mago",
  "Habilidad": "Lluvia de miel"
}
```

El inventario, mercado, economía, Tradeos, sets, niveles, pity y recompensas se conservan; únicamente cambia la presentación visual y la forma de editar la ficha del personaje.


## Stats de combate

El dashboard incluye ahora campos dedicados para `HP`, `ATK`, `Speed` y `Clase`. También permite configurar una `Habilidad` y una `Pasiva`, cada una con nombre, descripción y daño. El daño admite valores como `25`, `25-40` o `10%`, para que el sistema pueda soportar daño fijo, rangos o porcentajes.

Estos campos se guardan dentro de `stats` con las claves `HP`, `ATK`, `Speed`, `Clase`, `Habilidad`, `Descripción de habilidad`, `Daño de habilidad`, `Pasiva`, `Descripción de pasiva` y `Daño de pasiva`. Las stats extra en JSON siguen disponibles y se muestran junto con los campos de combate en el embed del personaje.
