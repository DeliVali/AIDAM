"""PyInstaller entry point: the `aidam` CLI as a frozen executable."""

import sys

from aidam.cli import main

if __name__ == "__main__":
    sys.exit(main())
