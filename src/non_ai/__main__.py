"""Позволяет запускать через `python -m non_ai`."""
from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())