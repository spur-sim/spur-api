class SpurApiError(Exception):
    """Base class for spur-api's own error hierarchy."""


class NotFoundError(SpurApiError):
    """A requested resource (project, run, ...) does not exist."""


class InvalidProjectError(SpurApiError):
    """A project spec failed spur's own validation."""


class ProjectInvalidError(SpurApiError):
    """A project failed validation, so a run of it can't be started.

    `issues` are the `spur.validation.Issue`s found, warnings included.
    """

    def __init__(self, message: str, issues: list) -> None:
        super().__init__(message)
        self.issues = issues


class RunNotReadyError(SpurApiError):
    """A run has no results yet (it is still queued)."""


class RunAnalysisError(SpurApiError):
    """A run's events could not be analysed against its project."""
