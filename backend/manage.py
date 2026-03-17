#!/usr/bin/env python
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "No se pudo importar Django. Asegurate de que esta instalado y disponible "
            "en tu PYTHONPATH. Recuerda activar el entorno virtual."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
