"""Import-workbook errors with stable, user-facing meanings."""


class ImportWorkbookError(ValueError):
    """Base class for workbook format and validation errors."""


class UnsafeWorkbookError(ImportWorkbookError):
    """Raised when an OOXML package violates safety limits."""


class UnsupportedWorkbookError(ImportWorkbookError):
    """Raised when a workbook does not match a supported contract."""
