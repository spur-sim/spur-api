class SpurApiError(Exception):
    """Base class for spur-api's own error hierarchy."""


class NotFoundError(SpurApiError):
    """A requested resource (project, run, ...) does not exist."""


class InvalidProjectError(SpurApiError):
    """A project spec failed spur's own validation."""
