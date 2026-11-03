"""Punto de entrada de Ballers.gg: python Main.py.

Arranca FastAPI y Angular sin scripts de shell. Solo usa la biblioteca estándar;
las dependencias de la API se ejecutan con el entorno virtual del backend.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, build_opener
import webbrowser

ROOT = Path(__file__).resolve().parent
HOST = '127.0.0.1'
WEB_URL = f'http://{HOST}:4200'
API_URL = f'http://{HOST}:8000'


def check_requirements() -> tuple[Path, str, Path]:
    backend = ROOT / 'backend'
    python = backend / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    angular = ROOT / 'frontend/node_modules/@angular/cli/bin/ng.js'
    node = shutil.which('node')
    if not python.is_file():
        raise RuntimeError('Falta backend/.venv. Prepara el entorno Python siguiendo README.md.')
    if not (backend / '.env').is_file():
        raise RuntimeError('Falta backend/.env. Copia .env.example y configura la conexión a MariaDB.')
    if node is None:
        raise RuntimeError('No se encuentra Node.js. Instálalo y vuelve a abrir la terminal.')
    if not angular.is_file():
        raise RuntimeError('Faltan las dependencias de Angular. Ejecuta npm install dentro de frontend.')
    for port, name in ((8000, 'backend'), (4200, 'frontend')):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            if os.name == 'nt':
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            try:
                probe.bind((HOST, port))
            except OSError:
                raise RuntimeError(f'El puerto {port} del {name} está ocupado. Cierra la instancia anterior y vuelve a ejecutar Main.py.') from None
    return python, node, angular


def start(command: list[str], directory: Path) -> subprocess.Popen:
    options = {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt' else {'start_new_session': True}
    # A list of arguments and shell=False preserve spaces and accents in paths.
    return subprocess.Popen(command, cwd=directory, shell=False, **options)


def ensure_running(processes: list[tuple[str, subprocess.Popen]]) -> None:
    for name, process in processes:
        code = process.poll()
        if code is not None:
            raise RuntimeError(f'{name} se ha detenido (código {code}). Revisa los mensajes de esta terminal.')


def wait_until_ready(processes: list[tuple[str, subprocess.Popen]], timeout: float = 90) -> None:
    # Loopback requests must not go through a machine's configured HTTP proxy.
    opener = build_opener(ProxyHandler({}))
    pending = {f'{API_URL}/api/health': 'La API', WEB_URL: 'Angular'}
    deadline = time.monotonic() + timeout
    while pending:
        ensure_running(processes)
        for url in list(pending):
            try:
                with opener.open(url, timeout=1) as response:
                    if response.status == 200:
                        del pending[url]
            except HTTPError as error:
                if url.endswith('/api/health') and error.code == 503:
                    raise RuntimeError('La API ha arrancado, pero no puede acceder a MariaDB. Revisa la conexión y las migraciones indicadas en README.md.') from None
            except (URLError, TimeoutError, OSError):
                pass
        if pending and time.monotonic() >= deadline:
            names = ', '.join(pending.values())
            raise RuntimeError(f'{names} no están listos después de {timeout:g} segundos. Revisa los mensajes de arranque.')
        if pending:
            time.sleep(0.25)


def stop(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == 'nt':
        # Stop the complete tree, including the venv redirector and Angular workers.
        subprocess.run(['taskkill.exe', '/PID', str(process.pid), '/T', '/F'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if os.name != 'nt':
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            process.kill()
        process.wait(timeout=5)


def production() -> int:
    """En Render se ejecuta un solo proceso con Angular ya compilado."""
    required = ('DB_HOST', 'DB_PORT', 'DB_NAME', 'DB_USER', 'DB_PASSWORD')
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        print('Faltan variables de producción: ' + ', '.join(missing), file=sys.stderr)
        return 1
    try:
        port = int(os.environ.get('PORT', '10000'))
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError:
        print('PORT debe ser un entero entre 1 y 65535.', file=sys.stderr)
        return 1
    sys.path.insert(0, str(ROOT / 'backend'))
    from bd.conexion import engine
    from bd.comprobar import verify_schema
    try:
        with engine.connect() as connection:
            verify_schema(connection)
    except Exception:
        print('MariaDB no está accesible o su esquema está pendiente. Comprueba las variables DB_ y ejecuta python -m bd.preparar antes de desplegar.', file=sys.stderr)
        return 1
    import uvicorn
    # Un solo worker: las sesiones invitadas son temporales y viven en memoria.
    uvicorn.run('app.web:application', host='0.0.0.0', port=port, workers=1,
                proxy_headers=True, forwarded_allow_ips='*')
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description='Arranca Ballers.gg: backend Python y frontend Angular.')
    parser.add_argument('--no-browser', action='store_true', help='Arranca sin abrir el navegador automáticamente.')
    parser.add_argument('--production', action='store_true', help='Sirve Angular compilado y la API en el puerto PORT (Render).')
    args = parser.parse_args()
    if args.production:
        return production()
    processes: list[tuple[str, subprocess.Popen]] = []
    try:
        python, node, angular = check_requirements()
        print('\nBALLERS.GG | Arrancando la aplicación…', flush=True)
        processes.append(('Backend', start([str(python), '-m', 'uvicorn', 'app.main:app',
                                           '--host', HOST, '--port', '8000'], ROOT / 'backend')))
        processes.append(('Frontend', start([node, str(angular), 'serve', '--host', HOST,
                                            '--port', '4200', '--proxy-config', 'proxy.conf.json'], ROOT / 'frontend')))
        wait_until_ready(processes)
        print(f'\nBallers.gg listo: {WEB_URL}\nAPI: {API_URL}/docs\nPulsa Ctrl+C para cerrar la aplicación.\n', flush=True)
        if not args.no_browser:
            try:
                if not webbrowser.open(WEB_URL):
                    print(f'Abre {WEB_URL} en tu navegador.', flush=True)
            except webbrowser.Error:
                print(f'Abre {WEB_URL} en tu navegador.', flush=True)
        while True:
            ensure_running(processes)
            time.sleep(0.5)
    except KeyboardInterrupt:
        print('\nCerrando Ballers.gg…', flush=True)
        return 0
    except (RuntimeError, OSError) as error:
        print(f'\nNo se pudo iniciar Ballers.gg: {error}', file=sys.stderr, flush=True)
        return 1
    finally:
        # Also close the first server if starting the second one fails.
        for _, process in reversed(processes):
            stop(process)


if __name__ == '__main__':
    raise SystemExit(main())
