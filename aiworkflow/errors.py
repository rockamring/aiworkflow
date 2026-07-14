class AIWorkflowError(Exception):
    """Base error for user-facing workflow failures."""


class ConfigError(AIWorkflowError):
    """Raised when configuration cannot be loaded or validated."""


class DependencyError(AIWorkflowError):
    """Raised when an optional runtime dependency is missing."""


class GraphConnectionError(AIWorkflowError):
    """Raised when Neo4j cannot be reached."""


class ModelGatewayError(AIWorkflowError):
    """Raised when model gateway calls fail."""
