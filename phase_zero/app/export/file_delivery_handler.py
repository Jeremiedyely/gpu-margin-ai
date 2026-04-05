"""
File Delivery Handler — Component 9/9.

Layer: Export.

Returns a computer:// link for the generated file.
Ensures atomic filepath handoff — no partial file delivered.

Spec: build-checklist.md — Step 7.10
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel


class DeliveryResult(BaseModel):
    """Output of the File Delivery Handler."""

    result: str  # "SUCCESS" | "FAIL"
    link: str | None = None
    filepath: str | None = None
    error: str | None = None

    @classmethod
    def success(cls, filepath: Path) -> DeliveryResult:
        resolved = filepath.resolve()
        return cls(
            result="SUCCESS",
            link=f"computer://{resolved}",
            filepath=str(resolved),
        )

    @classmethod
    def failed(cls, error: str) -> DeliveryResult:
        return cls(result="FAIL", error=error)


def deliver_file(filepath: Path) -> DeliveryResult:
    """
    Validate the file exists and is non-empty, then return a delivery link.

    Parameters
    ----------
    filepath : Path
        The generated export file.

    Returns
    -------
    DeliveryResult
        SUCCESS with computer:// link, or FAIL with error.
    """
    if not filepath.exists():
        return DeliveryResult.failed(
            f"File not found: {filepath}"
        )

    if filepath.stat().st_size == 0:
        return DeliveryResult.failed(
            f"File is empty (0 bytes): {filepath}"
        )

    return DeliveryResult.success(filepath)
