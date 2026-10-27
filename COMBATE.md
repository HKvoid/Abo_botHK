# Peleas carta contra carta

Abo incluye una primera versión jugable de duelos PvP entre dos usuarios.

## Flujo

1. Un usuario usa `/pelea @usuario`.
2. El rival acepta el desafío.
3. Ambos eligen un equipo de **3 cartas** de su colección (si tienen menos, pelean con las que tengan). La carta más rápida del equipo sale primero.
4. Comienza el personaje con mayor `Speed`.
5. El jugador activo elige entre ataque básico, habilidad, defenderse o rendirse.
6. Cuando la carta activa llega a 0 HP, entra la siguiente carta viva del equipo. La pelea termina cuando todo un equipo cae o un jugador se rinde.

## Reglas iniciales

- Cada carta inicia con el HP definido en sus stats; si no está definido, usa 100 HP.
- El ataque básico usa `ATK`; la defensa reduce el daño recibido mediante `DEF / 2`.
- Defender reduce a la mitad el siguiente daño recibido y recupera 1 punto de energía.
- La habilidad cuesta 2 de energía y el ataque básico recupera 1.
- La energía máxima es 5.
- Las habilidades pueden aplicar Quemadura, Veneno, Aturdimiento, Escudo, Regeneración, Silencio, Debilitado o Lento cuando estén configuradas.
- Los efectos de Quemadura y Veneno hacen 3 de daño al final del turno mientras duren.
- La pelea y sus acciones quedan registradas en `card_battles` y `card_battle_logs`.

## Equipos de 3 cartas

- Cada jugador tiene una carta activa; las otras esperan en la banca con su HP y estados guardados.
- Botón **🔄 Cambiar**: cambia la carta activa por una viva de la banca. Consume el turno y la energía se conserva (es del jugador, no de la carta).
- Si la carta activa cae (por golpe o por estado), entra automáticamente la siguiente viva, por orden de Speed.
- Aturdimiento sigue aplicando aunque intentes cambiar: el turno se pierde igual.
- Última carta en pie: cada carta tiene su propio *Último aliento* (una vez por carta).
- `card_battles` guarda las cartas iniciales de cada jugador (`card_a`, `card_b`) y los equipos completos en `result.teams` al terminar.
- La revancha reutiliza los mismos equipos con el HP restaurado.
