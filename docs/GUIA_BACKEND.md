# Cómo leer el backend de Ballers.gg

El backend tiene dos carpetas de código: **`app`** y **`bd`**. Puedes empezar por estos tres archivos, en este orden:

1. **`app/main.py`**: recibe las peticiones de Angular.
2. **`app/participantes.py`**: comprueba los datos y realiza las operaciones.
3. **`bd/consultas.py`**: hace las consultas a MariaDB.

## Qué hay en cada carpeta

| Archivo | Qué hace |
|---|---|
| `app/main.py` | Crea la API y define las direcciones para listar, crear y editar jugadores. |
| `app/participantes.py` | Contiene las funciones para validar, crear, editar y cambiar de estado. |
| `app/sesiones.py` | Comprueba el acceso, crea cuentas y gestiona sesiones y contraseñas. |
| `app/invitados.py` | Gestiona jugadores temporales en memoria, sin guardar en MariaDB. |
| `app/torneos.py` | Valida, guarda y consulta torneos e inscritos. |
| `app/cuadros.py` | Calcula emparejamientos, upper/lower, grupos y rondas. |
| `app/datos.py` | Describe los datos que intercambian Angular y Python y los convierte a diccionarios. |
| `bd/conexion.py` | Lee la conexión de `.env` y abre una sesión para cada petición. |
| `bd/modelos.py` | Describe cuentas, sesiones, participantes y logos. |
| `bd/consultas.py` | Busca participantes, aplica filtros y cuenta resultados. |
| `bd/preparar.py` | Guarda el SQL y prepara las tablas cuando sea necesario. |
| `bd/comprobar.py` | Permite comprobar la conexión y la estructura sin cambiar los datos. |

El **`Main.py` de la raíz** arranca todo el programa. El `app/main.py` del backend contiene la API; no necesitas ejecutarlo por separado.

## Ejemplo: crear un jugador

1. Angular envía el nick, el estado y, opcionalmente, el logo.
2. La dependencia `require_access` identifica la cuenta o invitado. `app/main.py` recibe la petición y llama a `participantes.create_participant`.
3. Esa función comprueba el nick, prepara el logo y crea un objeto `Participant`.
4. Si es una cuenta, `save_changes` guarda los cambios juntos en MariaDB con su propietario. Si es invitado, `invitados.py` los conserva solamente en memoria.
5. `participant_to_dict` prepara los datos públicos para devolverlos a Angular.

Para consultar jugadores, `app/participantes.py` llama a `bd/consultas.py`. Para editarlos, utiliza sus propias funciones de validación y guardado. Las reglas permanecen en Python.

## Palabras que encontrarás

- **Modelo:** clase que representa una tabla. Un objeto `Participant` representa un jugador.
- **Sesión:** permite consultar y guardar los datos de una petición.
- **`commit()`:** confirma los cambios.
- **`rollback()`:** deshace los cambios si no se pudieron guardar.
- **`Depends(get_session)`:** FastAPI entrega una sesión a la ruta y la cierra al terminar.
- **`HTTPException`:** devuelve un error y un mensaje a Angular.
- **`version`:** detecta que otra sesión ha modificado el mismo participante.

## Carpetas que puedes dejar para después

**`.venv`** contiene Python y sus librerías; no es código de la aplicación que tengas que estudiar.

Las comprobaciones automáticas se conservan en **`pruebas`**, en la raíz del proyecto, fuera del backend. Veremos su contenido más adelante. No se ejecutan al arrancar `Main.py`.

## Dos tipos de sesión

La sesión de **base de datos** (`get_session`) es una conexión de trabajo para una petición. La sesión de **acceso** identifica a la persona mediante una cookie; `sesiones.py` comprueba si pertenece a una cuenta o invitado. Son conceptos distintos.

Una cuenta tiene un ID en `users`; cada jugador persistente tiene su `owner_id`. Para buscar un jugador no basta su ID: también se comprueba que pertenezca al usuario que lo solicita. Una sesión invitada guarda un diccionario temporal; no crea filas de usuarios ni jugadores en la base.

Al añadir rutas futuras, la dependencia global ya pedirá acceso. Las consultas nuevas deberán restringir sus recursos al propietario y definir qué datos son temporales para los invitados. Las contraseñas solo pasan por funciones de hash y verificación; nunca deben imprimirse ni incorporarse a la documentación.


## Ejemplo: crear un torneo

1. Angular envía nombre, formato, mínimo, máximo y los IDs elegidos.
2. `app/main.py` exige acceso y llama a `torneos.create`.
3. `torneos.py` comprueba límites, duplicados, propietario y actividad. Baraja una vez los IDs.
4. `cuadros.generate` devuelve un plan de fases, rondas y plazas. No guarda nada por sí mismo.
5. `save_plan` convierte ese plan en filas de las tablas de `bd/modelos.py`; un único commit confirma todo.
6. `torneos.detail` lee lo guardado y prepara la respuesta. Consultar no baraja ni genera otro cuadro.

En modo invitado se conserva el plan solamente en el diccionario de la sesión. Las rondas futuras contienen referencias al ganador o perdedor de un partido, o al clasificado de un grupo: no contienen resultados inventados. La siguiente fase podrá añadir resultados referenciando los IDs de partidos existentes.


## Marcadores (fase 3)
La ruta de resultados está en `app/main.py`, sus campos en `app/datos.py` y las reglas en `app/resultados.py`. `validate_result` comprueba que el partido esté disponible y que el ganador corresponda al marcador. `standings` calcula puntos y diferencia de goles. `new_draws` sortea solo los empates que persisten al terminar un grupo. `present` sigue las referencias del cuadro hasta obtener los siguientes rivales y el campeón. `record` guarda todo junto y cierra el torneo al terminar la final. No hay una operación para editar resultados confirmados.

`MatchResult` y `GroupDraw`, en `bd/modelos.py`, describen las dos tablas nuevas. `bd/preparar.py` aplica su SQL como versión 5; `bd/comprobar.py` comprueba su estructura. No se necesitan carpetas ni dependencias adicionales.


El formulario de torneo utiliza ahora un solo `participant_count`: Python exige seleccionar exactamente ese número. `torneos.remove` elimina únicamente el torneo del propietario y sus datos asociados; primero retira las referencias que impedirían la eliminación y después elimina el torneo. Un fallo revierte toda la operación. La plantilla de jugadores se conserva. La ruta DELETE está junto a las demás rutas de torneos en main.py.


## Ligas y parejas
cuadros.league crea el calendario de una o dos vueltas. torneos.generate_plan forma las parejas manuales o aleatorias y sortea sus inscripciones como unidades. TournamentPartner guarda el segundo miembro; las relaciones existentes guardan el primero, el cuadro y los resultados. resultados.present usa la clasificación definitiva de la liga para obtener campeón, sin inventar una final.

estadisticas.py contiene funciones de lectura: views recupera torneos propios; records transforma sus partidos resueltos en historial por miembro; accumulate suma sus resultados y títulos una sola vez por partido/miembro; ranking e history preparan la paginación. No se almacenan contadores de victorias ni estadísticas duplicadas. Si se elimina un torneo, deja de contribuir a estas consultas.
