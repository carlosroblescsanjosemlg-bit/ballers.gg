# Publicar Ballers.gg en Render desde GitHub

El repositorio contiene un Dockerfile y render.yaml. Un único Web Service sirve Angular compilado y la API bajo el mismo dominio HTTPS, manteniendo /api, cookies y CSRF. MariaDB permanece en tu servidor actual, fuera del contenedor. El backend es el único que se conecta a ella.

## Configuración

1. Sube el proyecto a tu repositorio de GitHub. .env, .venv, node_modules, dist, certificados y notas locales están excluidos.
2. En Render, New → Blueprint y selecciona el repositorio. Render leerá render.yaml. También puedes usar New → Web Service, repositorio, lenguaje Docker, Dockerfile en ./Dockerfile y contexto raíz.
3. Elige la rama main. El Blueprint usa el plan Free y región Frankfurt. No añadas una base Postgres: este proyecto requiere MariaDB.
4. Completa en Render las variables privadas DB_HOST, DB_PORT, DB_NAME, DB_USER y DB_PASSWORD con la conexión de tu MariaDB. SESSION_COOKIE_SECURE debe ser 1. No pegues credenciales en render.yaml ni en GitHub.
5. Render construye Angular y Python. El inicio es python Main.py --production, en 0.0.0.0 y el puerto PORT facilitado por Render. Health check: /api/health.
6. Abre la URL HTTPS onrender.com asignada por Render y comprueba acceso, alta de cuenta, jugadores, torneos y persistencia al volver a iniciar sesión.

No utilices npm start ni ng serve en Render. Node solo se usa para compilar; el contenedor final sirve los archivos desde Python. No necesitas cambiar las URLs de Angular ni configurar CORS entre dos dominios.

## MariaDB y tablas

El servidor MariaDB debe admitir conexiones desde Render y permitir al usuario acceder a esa base. Usar 127.0.0.1 en Render señalaría al contenedor, no a tu equipo. No cambies reglas del firewall ni permisos de otros usuarios para probar sin consultar al administrador del servidor.

Main.py --production comprueba las variables obligatorias y el esquema existente, pero no modifica tablas al iniciar. La MariaDB actual ya tiene las actualizaciones del proyecto. En otra base nueva, configura sus datos de conexión de forma privada y ejecuta python -m bd.preparar desde backend antes del despliegue. No se hace una copia de los datos ni se sustituye la base actual.

Si se dispone de una CA para la conexión TLS de MariaDB, debe añadirse la configuración correspondiente del proveedor al driver antes de publicar; el proyecto actual conserva la configuración de conexión de su servidor existente.

## Sesiones y plan Free

Se ejecuta un único worker porque los invitados viven en memoria. Una cuenta conserva sus datos en MariaDB. Los invitados se pierden al reiniciar, redesplegar o suspender la instancia; no se guardan en el disco del contenedor.

El plan Free de Render se suspende tras inactividad y puede tardar en despertar. La primera visita puede esperar; no es adecuado para disponibilidad permanente. Consulta sus límites actuales antes de contratar otro plan. No se ha configurado ningún servicio de pago.

## Ejecución y comprobación local

El uso habitual sigue siendo python Main.py. El modo de producción requiere Angular previamente compilado y variables DB_ del sistema; no exige un .env dentro del contenedor.

```powershell
cd frontend
npm.cmd ci
npm.cmd run build
cd ..
.\backend\.venv\Scripts\python.exe -m unittest pruebas.test_production_web -v
```

Las pruebas de producción comprueban HTML y recursos públicos, API privada, CSRF, cookies Secure/HttpOnly y que .env/código Python no se sirvan como recursos. No modifican MariaDB. Sin dist compilado se omiten esas pruebas específicas.

## Referencias oficiales

- https://render.com/docs/docker
- https://render.com/docs/web-services
- https://render.com/docs/blueprint-spec
- https://render.com/docs/free
