# Peleas carta contra carta

Abo incluye una primera versión jugable de duelos PvP entre dos usuarios.

## Flujo

1. Un usuario usa `/pelea @usuario`.
2. El rival acepta el desafío.
3. Ambos seleccionan un personaje que tengan en su colección.
4. Comienza el personaje con mayor `Speed`.
5. El jugador activo elige entre ataque básico, habilidad, defenderse o rendirse.
6. La pelea termina cuando una carta llega a 0 HP o un jugador se rinde.

## Reglas iniciales

- Cada carta inicia con el HP definido en sus stats; si no está definido, usa 100 HP.
- El ataque básico usa `ATK`; la defensa reduce el daño recibido mediante `DEF / 2`.
- Defender reduce a la mitad el siguiente daño recibido y recupera 1 punto de energía.
- La habilidad cuesta 2 de energía y el ataque básico recupera 1.
- La energía máxima es 5.
- Las habilidades pueden aplicar Quemadura, Veneno, Aturdimiento, Escudo, Regeneración, Silencio, Debilitado o Lento cuando estén configuradas.
- Los efectos de Quemadura y Veneno hacen 3 de daño al final del turno mientras duren.
- La pelea y sus acciones quedan registradas en `card_battles` y `card_battle_logs`.

Esta fase utiliza una carta activa por jugador. El equipo de tres cartas y el cambio de personaje pueden añadirse después sin cambiar el modelo base.

## Modalidades de `/pelea`

Al ejecutar `/pelea`, el comando incluye el parámetro **modalidad**, con las opciones **1v1** (una carta por jugador) y **3v3** (tres cartas distintas por equipo). Después, el rival acepta el desafío y cada jugador selecciona sus cartas. En 3v3, la carta con mayor velocidad sale primero; cuando una carta cae, entra automáticamente la siguiente, y el jugador puede cambiar manualmente a otra carta viva con **Cambiar**.
