"""Process-wide logging configuration."""

from __future__ import annotations

import logging

_CONFIGURED = False


def configure_logging(level: str) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        logging.getLogger().setLevel(level.upper())
        return
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    _CONFIGURED = True
