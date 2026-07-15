"""Stable application errors for controlled spreadsheet imports."""


class SpreadsheetImportError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 422):
        self.code = code
        self.status_code = status_code
        super().__init__(message)


class ImportBlockedError(SpreadsheetImportError):
    def __init__(self, report: dict):
        self.report = report
        super().__init__("import_blocked", "Preflight contains unresolved errors", 422)
