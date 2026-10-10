"""Application-specific exceptions."""


class PlanningSnapshotError(RuntimeError):
    """Raised when a complete planning snapshot cannot be loaded."""
