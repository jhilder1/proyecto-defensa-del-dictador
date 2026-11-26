"""Root-folder launcher that starts the FastAPI backend and opens the 2D frontend."""

import argparse
import os
import subprocess
import sys
import threading
import webbrowser


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inicia backend FastAPI y abre el frontend 2D desde la carpeta raíz."
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host del servidor (por defecto 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Puerto del servidor (por defecto 8000)")
    parser.add_argument("--no-browser", action="store_true", help="No abrir automáticamente el navegador")
    args = parser.parse_args()

    root_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.join(root_dir, "backend")
    url = f"http://{args.host}:{args.port}"

    print("================================================================")
    print("  Simulación de Defensa Estratégica - General P. Tardo")
    print("================================================================")
    print(f"  Frontend 2D : {url}")
    print(f"  Backend API : {url}/docs")
    print("================================================================")

    if not args.no_browser:
        timer = threading.Timer(2.0, webbrowser.open, args=[url])
        timer.daemon = True
        timer.start()

    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "main:app",
        "--app-dir",
        backend_dir,
        "--reload",
        "--host",
        args.host,
        "--port",
        str(args.port),
    ]

    try:
        return subprocess.call(cmd, cwd=root_dir)
    except KeyboardInterrupt:
        print("\nServidor detenido correctamente.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
