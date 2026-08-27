"""Core message structure for COD3S Data Framework."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


class Message(BaseModel):
    """
    Core message structure for COD3S Data Framework.

    All messages flowing through the framework use this structure,
    regardless of source or destination.

    Attributes:
        key: Identifies what is being measured (e.g., "temperature")
        timestamp: When the measurement was taken (UTC, timezone-aware)
        value: The actual measurement (flexible type)
        tags: Optional metadata for filtering/routing (all string values)
        id: Unique message identifier (auto-generated if not provided)

    Examples:
        >>> from datetime import datetime, timezone
        >>> msg = Message(
        ...     key="temperature",
        ...     timestamp=datetime.now(timezone.utc),
        ...     value=42.5,
        ...     tags={"sensor": "TH001", "location": "warehouse_A"}
        ... )
        >>> msg.key
        'temperature'
        >>> msg.value
        42.5
    """

    # Required fields
    key: str = Field(
        ...,
        description="Identifier for what is being measured",
        min_length=1,
        max_length=255,
    )

    timestamp: datetime = Field(
        ..., description="When the measurement was taken (must be timezone-aware UTC)"
    )

    value: Any = Field(..., description="The actual measurement (any JSON-serializable type)")

    # Optional fields
    tags: dict[str, str] = Field(
        default_factory=dict,
        description="Metadata for filtering and routing (all values are strings)",
    )

    id: UUID = Field(
        default_factory=uuid4, description="Unique message identifier (auto-generated)"
    )

    # Configuration
    model_config = {
        "frozen": True,  # Immutable after creation (thread-safe)
        "validate_assignment": True,  # Validate if reassignment attempted
        "arbitrary_types_allowed": True,  # Allow any type in 'value' field
        "json_schema_extra": {
            "examples": [
                {
                    "key": "temperature_extruder",
                    "timestamp": "2024-01-15T10:30:45Z",
                    "value": 235.7,
                    "tags": {"location": "warehouse_A", "sensor_id": "TH001"},
                }
            ]
        },
    }

    # Validators

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp_tz(cls, v: datetime) -> datetime:
        """
        Ensure timestamp is timezone-aware and in UTC.

        Args:
            v: Timestamp to validate

        Returns:
            Validated timestamp (guaranteed UTC)

        Raises:
            ValueError: If timestamp is naive (no timezone)
        """
        if v.tzinfo is None:
            raise ValueError(
                "Timestamp must be timezone-aware. "
                "Use datetime.now(timezone.utc) instead of datetime.now()"
            )

        # Convert to UTC if not already
        if v.tzinfo != UTC:
            v = v.astimezone(UTC)

        return v

    @field_validator("tags", mode="before")
    @classmethod
    def validate_tags_strings(cls, v: dict[str, Any]) -> dict[str, str]:
        """
        Ensure all tag values are strings.

        Automatically converts numbers and booleans to strings.

        Args:
            v: Tags dictionary

        Returns:
            Tags with all values as strings
        """
        if not isinstance(v, dict):
            return v
        return {k: str(val) for k, val in v.items()}

    @field_validator("key", mode="after")
    @classmethod
    def validate_key_not_empty(cls, v: str) -> str:
        """
        Ensure key is not whitespace-only and trim it.

        Args:
            v: Key string

        Returns:
            Validated and trimmed key

        Raises:
            ValueError: If key is whitespace-only
        """
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("Key cannot be whitespace-only")
        return trimmed

    # Serialization

    def to_json(self) -> str:
        """
        Serialize to JSON string.

        Uses Pydantic's built-in JSON serialization (Rust-based, fast).

        Returns:
            JSON string representation

        Examples:
            >>> msg.to_json()
            '{"key":"temperature","timestamp":"2024-01-15T10:30:45Z",...}'
        """
        return self.model_dump_json()

    @classmethod
    def from_json(cls, json_str: str) -> "Message":
        """
        Deserialize from JSON string.

        Args:
            json_str: JSON string to deserialize

        Returns:
            Message instance

        Raises:
            ValidationError: If JSON is invalid or doesn't match schema

        Examples:
            >>> json_str = '{"key":"temp","timestamp":"2024-01-15T10:30:45Z","value":42}'
            >>> msg = Message.from_json(json_str)
            >>> msg.key
            'temp'
        """
        return cls.model_validate_json(json_str)

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to Python dictionary (excludes internal fields).

        Returns:
            Dictionary representation (JSON-serializable)
        """
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Message":
        """
        Create message from dictionary.

        Args:
            data: Dictionary with message fields

        Returns:
            Message instance

        Raises:
            ValidationError: If data is invalid
        """
        return cls.model_validate(data)

    # Utility methods

    def with_tags(self, **new_tags: str) -> "Message":
        """
        Create a new message with additional tags.

        Since messages are immutable, this creates a new instance.

        Args:
            **new_tags: Additional tags to add

        Returns:
            New message with merged tags

        Examples:
            >>> msg2 = msg.with_tags(priority="high", alert="yes")
            >>> "priority" in msg2.tags
            True
        """
        merged_tags = {**self.tags, **new_tags}
        return self.model_copy(update={"tags": merged_tags})

    def with_value(self, new_value: Any) -> "Message":
        """
        Create a new message with a different value.

        Useful for transformations.

        Args:
            new_value: New value to set

        Returns:
            New message with updated value

        Examples:
            >>> celsius_msg = fahrenheit_msg.with_value(celsius_value)
        """
        return self.model_copy(update={"value": new_value})

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"Message(key={self.key!r}, "
            f"timestamp={self.timestamp.isoformat()}, "
            f"value={self.value!r}, "
            f"tags={self.tags}, "
            f"id={self.id})"
        )
