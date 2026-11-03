# Ballers.gg · Fases 1 y 2

Gestión de participantes y torneos con eliminación directa, doble oportunidad y grupos seguidos de K.O. Interfaz Angular, API Python/FastAPI y persistencia en **MariaDB**. Estética de fútbol para FC 27; los modelos no dependen de un videojuego.

## Funciones entregadas

- Crear una cuenta, iniciar sesión o entrar como invitado.
- Plantilla privada para cada cuenta; el invitado utiliza memoria temporal, sin escribir sus jugadores en MariaDB.

- Crear, consultar y editar participantes con nick y logo opcional.
- Activar y desactivar conservando sus datos.
- Buscar por nick, filtrar por estado y paginar los resultados.
- Vista previa, sustitución y retirada de logos. Sin logo se muestran las iniciales.
- Resumen de los participantes de tu cuenta o sesión invitada, activos e inactivos.
- Rechazo de nicks duplicados y ediciones con una versión desactualizada.

## Arrancar en este equipo

El punto de entrada es **`Main.py`**, en la raíz del proyecto. Abre una sola terminal en esa carpeta y ejecuta:

```powershell
.\backend\.venv\Scripts\python.exe .\Main.py
```

Si tienes un Python instalado y disponible como `python`, también puedes ejecutar `python Main.py`. En Visual Studio Code, selecciona `backend/.venv/Scripts/python.exe` como intérprete, abre `Main.py` y pulsa **Ejecutar archivo Python**.

`Main.py` arranca la API y Angular directamente, espera a que respondan y abre http://127.0.0.1:4200 en el navegador. Mantén esa terminal abierta; **Ctrl+C cierra los dos servidores**. Para arrancar sin abrir automáticamente el navegador, añade `--no-browser`.

Documentación de la API: http://127.0.0.1:8000/docs. Si un puerto está ocupado, Main.py muestra un aviso y no inicia otra instancia. No instala dependencias ni modifica tablas al arrancar.

Los datos se guardan en `2DAM_alumno18`, en el servidor MariaDB configurado en `backend/.env`. Los jugadores y logos de las cuentas se conservan al cerrar o reiniciar. Los invitados no guardan sus jugadores en MariaDB. El frontend utiliza `/api`; el proxy de Angular reenvía las peticiones al backend. Solo Python se conecta a MariaDB.

## Preparar otro equipo

Requisitos: Python 3.12 o posterior compatible con las dependencias y Node.js 24.15 o posterior de la rama 24, con npm. Para Python usa `py` o el ejecutable instalado en tu equipo.

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
# Completar la contraseña en .env sin añadirlo a Git.
.\.venv\Scripts\python.exe -m bd.preparar
.\.venv\Scripts\python.exe -m bd.comprobar
cd ..\frontend
npm.cmd ci
```

El backend utiliza un único `requirements.txt` con las librerías necesarias para la aplicación y el cliente de pruebas. `unittest` viene incluido en Python. Angular conserva su `package-lock.json`.

El SQL de preparación y las nuevas versiones de las tablas están en `backend/bd/preparar.py`. `bd.preparar` ejecuta los cambios pendientes y registra sus versiones en `schema_updates`. No borrar tablas para actualizar la aplicación ni modificar versiones ya registradas.

## Estructura

```text
Main.py                    Arranque de toda la aplicación
backend/
  app/
    main.py                API y rutas de Angular
    participantes.py       Validaciones y operaciones
    datos.py               Datos de entrada y salida
    sesiones.py            Cuentas, contraseñas y acceso
    invitados.py           Jugadores temporales en memoria
    torneos.py             Validar, guardar y consultar torneos
    cuadros.py             Generar cuadros y grupos
  bd/
    conexion.py            Configuración y conexión a MariaDB
    modelos.py             Tablas de cuentas, sesiones, participantes y logos
    consultas.py           Consultas a la base de datos
    preparar.py            SQL y preparación de tablas
    comprobar.py           Comprobación de conexión y estructura
  .venv/                   Entorno Python; no es código de la aplicación
  .env                     Conexión privada
  requirements.txt         Librerías necesarias
frontend/                  Interfaz Angular
pruebas/                   Comprobaciones conservadas para más adelante
docs/                      Documentación
```

## Reglas de esta fase

Nick de 2 a 24 caracteres: se eliminan espacios exteriores y se normaliza Unicode NFKC; se rechazan caracteres de control. La unicidad se aplica dentro de cada cuenta y usa la intercalación `utf8mb4_unicode_ci` de MariaDB: no distingue mayúsculas ni acentos, y se aplica también a participantes inactivos. Un nick libre no implica un identificador nuevo: cada participante conserva su ID al editarse.

El logo es opcional: PNG, JPG o WebP de hasta 2 MiB y 4096 × 4096 píxeles. El backend verifica el contenido real, lo reduce a un máximo de 512 × 512 y lo convierte a PNG. La imagen y los cambios del participante se guardan en la misma transacción. La API sirve el logo por ID, sin rutas de archivos proporcionadas por el cliente.

La versión de cada participante evita sobrescribir cambios hechos desde otra sesión. Si hay conflicto, el formulario conserva lo escrito y muestra un mensaje; cancela, recarga la lista y vuelve a abrir el perfil actualizado.

No hay borrado de participantes en esta fase: se desactivan para conservar la identidad que usarán sus futuros combates. Los torneos, sus inscripciones, grupos y cuadros ya están implementados. Los resultados y estadísticas deportivas se añadirán en las fases siguientes. Las operaciones requieren una cuenta o una sesión invitada; los servidores se arrancan en la interfaz local `127.0.0.1`.

## Comprobar

Desde `backend`, puedes comprobar MariaDB sin modificar sus datos:

```powershell
.\.venv\Scripts\python.exe -m bd.comprobar
```

Las pruebas automáticas se han apartado en la carpeta `pruebas` de la raíz para retomarlas más adelante. No forman parte del arranque de la aplicación. Si necesitas ejecutarlas, desde la raíz:

```powershell
.\backend\.venv\Scripts\python.exe -m unittest discover -s pruebas -v
```

Las comprobaciones utilizan datos ficticios y retiran únicamente sus propios registros o tablas de prueba. Los identificadores autoincrementales pueden presentar saltos después de ejecutarlas.

Desde `frontend`:

```powershell
npm.cmd run build
```

## Lectura del backend

El backend usa funciones normales para las consultas y las operaciones. Las funciones de app/participantes.py llaman a las consultas de bd/consultas.py. Consulta docs/GUIA_BACKEND.md para seguir el recorrido de una petición, archivo por archivo.

## Preparar o actualizar las tablas

Desde `backend`, ejecuta:

```powershell
.\.venv\Scripts\python.exe -m bd.preparar
```

En una base vacía crea las tablas; en esta instalación conserva los datos existentes. Puedes repetirlo: las versiones ya aplicadas no se repiten. El arranque de la aplicación sigue siendo `Main.py` y no ejecuta cambios de estructura automáticamente.

Para una fase nueva, añade su SQL y registra la versión en la lista `UPDATES` de `bd/preparar.py`. Actualiza también las comprobaciones de `bd/comprobar.py`. Los cambios deben poder reintentarse si quedan incompletos: MariaDB confirma las instrucciones de estructura de forma independiente. No hay una operación automática para deshacer o borrar tablas.

La antigua tabla técnica `alembic_version` se conserva en esta instalación como información histórica y ya no se utiliza. No necesitas Alembic, pytest ni archivos `.ini` para preparar o comprobar el proyecto.
## Cuentas e invitados

La primera pantalla permite crear una cuenta, iniciar sesión o entrar como invitado. El usuario admite de 3 a 24 letras ASCII, números, puntos, guiones y guiones bajos. La contraseña tiene entre 10 y 128 caracteres. No se solicita correo y aún no hay recuperación de contraseñas.

Cada cuenta ve únicamente sus propios jugadores, también al consultar logos o modificar un ID directamente. Se pueden repetir nicks en cuentas distintas. Cerrar sesión conserva los datos; vuelve a entrar para recuperarlos. La sesión autenticada caduca a las 24 horas; la cookie de acceso no es persistente. La contraseña se almacena con sal y PBKDF2-SHA256, nunca en texto plano.

El invitado dispone de hasta 32 jugadores en memoria del backend durante un máximo de 2 horas. Recargar la misma pestaña conserva el trabajo. «Salir y descartar» lo elimina inmediatamente. Al cerrar normalmente la pestaña se pierde su indicador en sessionStorage; volver a abrir muestra la pantalla de acceso y descarta la sesión invitada anterior. El navegador puede restaurar sessionStorage al restaurar pestañas cerradas: no es un mecanismo de borrado seguro instantáneo. Los restos de memoria caducan en el servidor y desaparecen al detener Main.py. Los datos invitados no se importan al crear una cuenta.

El acceso se comprueba en Python, mediante una dependencia global de FastAPI. Las nuevas funciones deberán filtrar también sus datos por el usuario autenticado, como hacen las consultas actuales. Las escrituras necesitan el token CSRF que Angular envía automáticamente; las cookies de sesión son HttpOnly y SameSite=Strict. Las respuestas privadas usan Cache-Control: no-store.

La preparación SQL aplica las versiones 2 (cuentas, sesiones y relación con jugadores) y 3 (propietario obligatorio), conservando la versión 1. No elimina datos automáticamente: si una instalación anterior tiene jugadores sin propietario, la versión 3 pide resolverlos antes de continuar. En este equipo el usuario pidió expresamente eliminar el único jugador anterior, operación ya realizada. Una instalación pública requerirá HTTPS; el arranque actual sigue siendo local.

El formulario de acceso explica los errores de cada campo al intentar enviarlo. El registro exige al menos 10 caracteres y contraseñas iguales; los datos inválidos no se envían. Las peticiones de acceso tienen un máximo de espera de 15 segundos. Si se agota durante un registro, prueba primero a iniciar sesión: la cuenta podría haberse creado aunque no llegara la respuesta.


## Fase 2: torneos

En la cabecera, abre **Torneos → Crear torneo**. Introduce nombre (3–80 caracteres), formato y número de jugadores, y marca exactamente esa cantidad de jugadores. Solo se ofrecen los activos de tu propia plantilla. El servidor vuelve a comprobar que sigan activos al crear el torneo.

El número de jugadores debe ser entero entre 2 y 128. Debes seleccionar exactamente la cantidad indicada para crear el torneo. La sesión invitada sigue limitada a sus 32 jugadores y admite 20 torneos temporales.

| Formato | Cuadro que se genera |
|---|---|
| K.O. directo | Emparejamientos aleatorios y rondas hasta la final. Si el número no es potencia de dos, se sortean pases libres. |
| Doble oportunidad | Upper, lower y una final general. El perdedor de la final del upper va a la final del lower; sus dos campeones juegan la final general. La final general es única, sin segunda final de reinicio. Con dos jugadores, el perdedor del upper es directamente el representante del lower. |
| Grupos + K.O. | `ceil(jugadores / 4)` grupos equilibrados de 2–4 jugadores, todos contra todos a una vuelta. Pasan dos por grupo; el K.O. inicial cruza grupos distintos si hay más de uno. Con un solo grupo, sus dos clasificados disputarán la final. |

El sorteo se realiza **una sola vez**, al crear. Se guardan tanto las inscripciones sin duplicados como las fases, rondas, partidos y el origen de las plazas futuras. Consultar el torneo nunca vuelve a sortear. El formulario identifica cada envío: repetirlo con los mismos datos recupera el mismo torneo y cuadro. Si cambias los datos se considera un envío nuevo.

En grupos impares cada jornada tiene un jugador que descansa; no se crea un partido ficticio. Los pases libres del K.O. se resuelven sin victorias ni marcadores inventados. Cuando hay pases en el K.O. de grupos, se priorizan los primeros de grupo; el grupo asignado a cada participante procede del sorteo. En un grupo de dos pasan ambos, según la posición que obtengan.

Las cuentas conservan los torneos al reiniciar. Los invitados usan únicamente la memoria de su sesión y los pierden igual que sus jugadores. Cada cuenta e invitado solo puede consultar sus propios torneos. Desactivar después a un inscrito no elimina su plaza en torneos anteriores. Los nicks mostrados son los actuales del participante, referenciado por ID.

La primera ronda se puede consultar y la estructura de las siguientes se ve con plazas «Ganador…», «Perdedor…» o «1.º/2.º de Grupo…». La fase 3 incorpora marcadores, clasificación real de grupos, avances y campeón, descritos a continuación.

La versión SQL 4 crea siete tablas nuevas sin cambiar las versiones aplicadas ni borrar datos. `python -m bd.preparar` aplica las actualizaciones; `Main.py` sigue arrancando la aplicación sin modificar el esquema por su cuenta.

Desde Crear torneo puedes usar «Crear jugador» o «Crear mi primer jugador» para abrir el mismo formulario de nick, logo y estado sin salir del torneo. Al guardar se actualiza la plantilla, se conservan nombre, formato, número de jugadores y selección, y el jugador activo queda seleccionado si hay plaza. Si se cubren las plazas o se crea inactivo, se explica por qué no se añade a la selección.

Al entrar con una cuenta o como invitado se muestra Inicio con dos opciones visuales: Añadir jugadores y Crear torneo. Cada opción abre directamente su formulario. El menú superior conserva los listados de Jugadores y Torneos; Inicio y el logotipo permiten volver a la pantalla principal.

Si falta el nombre o el número de jugadores es incorrecto, el formulario explica el error junto a ese campo y te lleva a él al enviar. Los jugadores seleccionados se conservan; no necesitas recargarlos para corregir el nombre o la cantidad.


## Fase 3: resultados y campeón
Abre un torneo y pulsa **Registrar resultado** en un partido con dos rivales definidos. Introduce ambos marcadores (enteros entre 0 y 99) y confirma después de revisarlos. Los resultados confirmados no se editan. Si una eliminatoria acaba empatada, indica el ganador por penaltis; el marcador no incluye los goles de la tanda.

En grupos se permiten empates: victoria 3 puntos, empate 1 y derrota 0. La clasificación utiliza puntos y después diferencia de goles (GF − GC). Si persiste el empate al terminar el grupo, el backend realiza un sorteo entre los empatados y guarda su orden. La pantalla avisa y señala a los afectados. No se utiliza enfrentamiento directo ni goles a favor como otro desempate. Los dos primeros pasan al K.O.

Los partidos se habilitan cuando sus dos rivales están resueltos. Los pases libres no suman partidos ni resultados. En doble oportunidad se conservan las rutas upper/lower y la final general única.

Al confirmar la final se guarda la fecha de cierre: el torneo ya no admite resultados, incluso mediante la API. Se muestra al campeón con copa, felicitación y confeti (sin animación si el dispositivo pide movimiento reducido). La celebración y el cuadro final se pueden volver a consultar. Los torneos de cuentas conservan resultados y sorteos en MariaDB; los invitados siguen siendo temporales.

SQL versión 5: añade versión y cierre del torneo, `match_results` y `group_draws`. No borra ni vuelve a sortear los torneos existentes. El arranque sigue siendo `Main.py`.


## Eliminar torneos
Puedes eliminar un torneo propio desde su tarjeta o desde su cuadro, también si está finalizado. El diálogo identifica el torneo y pide confirmación: se borran cuadro, inscripciones, sorteos y resultados, conservando los jugadores de la plantilla y los demás torneos. La eliminación es definitiva. Cancelar no modifica nada.

Si alguien registra un resultado después de abrir el diálogo, la API rechaza la eliminación con conflicto y pide recargar. Ante una espera agotada, recarga el listado para comprobar si ya se eliminó.


## Ligas, parejas y sorteo animado
Al crear una competición puedes elegir **Liga** además de K.O., doble oportunidad y grupos + K.O. La liga permite una o dos vueltas, con calendario por jornadas y descansos cuando el número de competidores es impar. En ida y vuelta se invierten local y visitante. Se admiten empates, con 3/1/0 puntos; clasificación por puntos, diferencia de goles y sorteo persistido si sigue el empate. Al completar todos los partidos se proclama al primero y se cierra la liga.

La modalidad es independiente del formato: Individual, Parejas elegidas o Parejas aleatorias. En parejas indica el total de personas (por ejemplo, 8 personas = 4 parejas); hace falta un número par, al menos cuatro. Solo jugadores propios activos, sin repetir. En modalidad elegida, selecciona los jugadores y ajusta los desplegables de las parejas: cambiar un miembro intercambia su posición, evitando duplicados. En aleatoria, Python forma las parejas y guarda la composición al crear; permanecen unidas hasta el final.

Después de crear se revela el sorteo con animación: parejas si son aleatorias, grupos o primeros enfrentamientos. Puedes saltarlo en cualquier momento. La animación muestra lo ya guardado por el backend y no genera otro sorteo; recargar abre la competición persistida. La animación completa del sorteo está activada directamente. Las ligas muestran una jornada a la vez para mantener legible el calendario.

## Estadísticas e historial
La cabecera incluye **Estadísticas** con ranking paginado y búsqueda: partidos, victorias, empates, derrotas, GF/GC/DG, porcentaje de victorias y títulos. Se ordena por títulos, victorias y diferencia de goles. Incluye jugadores inactivos y con cero partidos. El total global de partidos cuenta cada partido una sola vez; los pases libres se excluyen.

Abre **Historial** desde el ranking o la fila de un jugador para consultar sus números, palmarés y partidos: torneo, fase/jornada, rival, marcador, resultado, fecha y compañero si lo hubo. Una tanda de penaltis decide victoria/derrota sin añadir goles al marcador. En parejas, ambos miembros reciben el resultado y el título del equipo; los goles indicados son los del equipo, no goles individuales atribuidos a un miembro.

Los datos se calculan desde los resultados guardados, sin contadores duplicados. Eliminar un torneo retira sus partidos y títulos de las estadísticas. Todo es privado por cuenta; los invitados conservan el mismo carácter temporal.

La versión SQL 6 añade configuración de liga/parejas y la tabla de segundos miembros, sin modificar IDs, inscripciones o resultados de los torneos anteriores. No hay nuevas dependencias y Main.py sigue siendo el punto de entrada.

En la modalidad de parejas, los grupos contienen de 2 a 4 parejas; las plazas del cuadro, los descansos y las clasificaciones se calculan por equipos.


El sorteo revela y conserva todos los cruces en pantalla. Puedes pausar/continuar, mostrar todos de golpe y repetir la presentación sin volver a sortear. Desde un torneo guardado, «Ver sorteo» permite volver a verla. La animación completa se ejecuta directamente, como ha pedido el usuario, sin selector de movimiento. Los recuadros no muestran numeración ni códigos de partido en su esquina.


## Despliegue en Render

El proyecto incluye Dockerfile y render.yaml para publicar Angular y FastAPI en un solo servicio desde GitHub, manteniendo MariaDB externa. Guía: [docs/RENDER.md](docs/RENDER.md). El uso local sigue siendo Main.py; Render utiliza Main.py --production y variables privadas de conexión.
