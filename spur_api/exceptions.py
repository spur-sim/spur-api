class SpurApiError(Exception):
    """Base class for spur-api's own error hierarchy."""


class NotFoundError(SpurApiError):
    """A requested resource (project, run, ...) does not exist."""


class InvalidProjectError(SpurApiError):
    """A project spec failed spur's own validation."""


class RunNotReadyError(SpurApiError):
    """A run has no results yet (it is still queued)."""


class RunAnalysisError(SpurApiError):
    """A run's events could not be analysed against its project."""
