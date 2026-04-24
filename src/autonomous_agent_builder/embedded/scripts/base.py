"""Base script interface for the script library."""

from abc import ABC, abstractmethod
from typing import Any, TypedDict


class ScriptResult(TypedDict):
    """Standard return format for all scripts."""

    success: bool
    data: Any
    error: str | None


class Script(ABC):
    """Abstract base class for all scripts in the library.
    
    All scripts must inherit from this class and implement the run() method.
    Scripts should validate their arguments in validate_args() before execution.
    """

    @abstractmethod
    def run(self, **kwargs: Any) -> ScriptResult:
        """Execute the script with the provided arguments.
        
        Args:
            **kwargs: Script-specific arguments
            
        Returns:
            ScriptResult with success status, data, and optional error message
        """
        pass

    def validate_args(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate script arguments before execution.
        
        Args:
            **kwargs: Script-specific arguments to validate
            
        Returns:
            Tuple of (is_valid, error_message)
            - is_valid: True if arguments are valid, False otherwise
            - error_message: None if valid, error description if invalid
        """
        return True, None

    @property
    def name(self) -> str:
        """Return the script name (defaults to class name in snake_case)."""
        return self.__class__.__name__.lower()

    @property
    def description(self) -> str:
        """Return a brief description of what the script does."""
        return self.__doc__ or "No description available"
