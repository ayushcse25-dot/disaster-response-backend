"""Minimal logging setup so application log lines (not just uvicorn's) are visible."""

import logging


def configure_logging(level: str) -> None:
    """Configure the root logger once. A no-op if handlers are already installed."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
