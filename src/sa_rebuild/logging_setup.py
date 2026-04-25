"""Configure rich logging once, return a module-level logger."""
from __future__ import annotations

import logging

from rich.logging import RichHandler


def setup(level: str = "INFO") -> logging.Logger:
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="%H:%M:%S",
        handlers=[RichHandler(rich_tracebacks=True, show_path=False, markup=True)],
    )
    return logging.getLogger("sa_rebuild")
