

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
