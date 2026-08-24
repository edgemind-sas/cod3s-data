"""Unit tests for Message class."""

import json
from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from cod3s_data.core.message import Message


class TestMessageCreation:
    """Test message creation and validation."""

    def test_create_message_minimal(self):
        """Test creating a message with minimal required fields."""
        msg = Message(
            key="temperature",
            timestamp=datetime.now(UTC),
            value=42.5,
        )

        assert msg.key == "temperature"
        assert msg.value == 42.5
        assert msg.tags == {}
        assert isinstance(msg.id, UUID)

    def test_create_message_with_tags(self):
        """Test creating a message with tags."""
        msg = Message(
            key="temperature",
            timestamp=datetime.now(UTC),
            value=42.5,
            tags={"sensor": "TH001", "location": "warehouse_A"},
        )

        assert msg.tags == {"sensor": "TH001", "location": "warehouse_A"}

    def test_message_is_frozen(self):
        """Test that messages are immutable."""
        msg = Message(
            key="temperature",
            timestamp=datetime.now(UTC),
            value=42.5,
        )

        with pytest.raises(ValidationError):
            msg.key = "pressure"  # type: ignore

        with pytest.raises(ValidationError):
            msg.value = 100  # type: ignore


class TestTimestampValidation:
    """Test timestamp validation."""

    def test_naive_timestamp_rejected(self):
        """Test that naive timestamps are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            Message(
                key="temperature",
                timestamp=datetime.now(),  # Naive datetime
                value=42.5,
            )

        assert "timezone-aware" in str(exc_info.value)

    def test_timezone_aware_timestamp_accepted(self):
        """Test that timezone-aware timestamps are accepted."""
        msg = Message(
            key="temperature",
            timestamp=datetime.now(UTC),
            value=42.5,
        )

        assert msg.timestamp.tzinfo is not None
        assert msg.timestamp.tzinfo == UTC

    def test_non_utc_timestamp_converted(self):
        """Test that non-UTC timezones are converted to UTC."""
        # Create a timestamp in a different timezone
        eastern = timezone(timedelta(hours=-5))
        eastern_time = datetime.now(eastern)

        msg = Message(
            key="temperature",
            timestamp=eastern_time,
            value=42.5,
        )

        # Should be converted to UTC
        assert msg.timestamp.tzinfo == UTC


class TestKeyValidation:
    """Test key validation."""

    def test_empty_key_rejected(self):
        """Test that empty keys are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            Message(
                key="",
                timestamp=datetime.now(UTC),
                value=42.5,
            )

        error_msg = str(exc_info.value).lower()
        # Either min_length validation or our custom validation should catch this
        assert "at least 1 character" in error_msg or "empty" in error_msg

    def test_whitespace_key_rejected(self):
        """Test that whitespace-only keys are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            Message(
                key="   ",
                timestamp=datetime.now(UTC),
                value=42.5,
            )

        error_msg = str(exc_info.value).lower()
        assert "whitespace" in error_msg or "empty" in error_msg

    def test_key_whitespace_trimmed(self):
        """Test that keys are trimmed."""
        msg = Message(
            key="  temperature  ",
            timestamp=datetime.now(UTC),
            value=42.5,
        )

        assert msg.key == "temperature"


class TestTagValidation:
    """Test tag validation."""

    def test_tag_values_converted_to_strings(self):
        """Test that tag values are converted to strings."""
        msg = Message(
            key="temperature",
            timestamp=datetime.now(UTC),
            value=42.5,
            tags={"sensor": "TH001", "count": 42, "active": True},  # type: ignore
        )

        # All values should be strings
        assert msg.tags == {"sensor": "TH001", "count": "42", "active": "True"}
        assert all(isinstance(v, str) for v in msg.tags.values())


class TestSerialization:
    """Test message serialization."""

    def test_to_json(self):
        """Test JSON serialization."""
        now = datetime(2024, 1, 15, 10, 30, 45, tzinfo=UTC)
        msg = Message(
            key="temperature",
            timestamp=now,
            value=42.5,
            tags={"sensor": "TH001"},
        )

        json_str = msg.to_json()
        data = json.loads(json_str)

        assert data["key"] == "temperature"
        assert data["value"] == 42.5
        assert data["tags"] == {"sensor": "TH001"}

    def test_from_json(self):
        """Test JSON deserialization."""
        json_str = """
        {
            "key": "temperature",
            "timestamp": "2024-01-15T10:30:45Z",
            "value": 42.5,
            "tags": {"sensor": "TH001"}
        }
        """

        msg = Message.from_json(json_str)

        assert msg.key == "temperature"
        assert msg.value == 42.5
        assert msg.tags == {"sensor": "TH001"}
        assert isinstance(msg.id, UUID)

    def test_to_dict(self):
        """Test dictionary conversion."""
        now = datetime.now(UTC)
        msg = Message(
            key="temperature",
            timestamp=now,
            value=42.5,
            tags={"sensor": "TH001"},
        )

        data = msg.to_dict()

        assert isinstance(data, dict)
        assert data["key"] == "temperature"
        assert data["value"] == 42.5
        assert data["tags"] == {"sensor": "TH001"}

    def test_from_dict(self):
        """Test creating message from dictionary."""
        data = {
            "key": "temperature",
            "timestamp": datetime.now(UTC),
            "value": 42.5,
            "tags": {"sensor": "TH001"},
        }

        msg = Message.from_dict(data)

        assert msg.key == "temperature"
        assert msg.value == 42.5
        assert msg.tags == {"sensor": "TH001"}

    def test_roundtrip_json(self):
        """Test JSON roundtrip preserves data."""
        original = Message(
            key="temperature",
            timestamp=datetime.now(UTC),
            value=42.5,
            tags={"sensor": "TH001", "location": "warehouse"},
        )

        json_str = original.to_json()
        restored = Message.from_json(json_str)

        assert restored.key == original.key
        assert restored.value == original.value
        assert restored.tags == original.tags
        # Timestamp might differ slightly due to serialization
        assert abs((restored.timestamp - original.timestamp).total_seconds()) < 1


class TestUtilityMethods:
    """Test utility methods."""

    def test_with_tags(self):
        """Test adding tags to a message."""
        msg = Message(
            key="temperature",
            timestamp=datetime.now(UTC),
            value=42.5,
            tags={"sensor": "TH001"},
        )

        msg2 = msg.with_tags(priority="high", alert="yes")

        # Original message unchanged
        assert msg.tags == {"sensor": "TH001"}

        # New message has merged tags
        assert msg2.tags == {
            "sensor": "TH001",
            "priority": "high",
            "alert": "yes",
        }

        # Other fields unchanged
        assert msg2.key == msg.key
        assert msg2.value == msg.value
        assert msg2.timestamp == msg.timestamp

    def test_with_tags_overwrites(self):
        """Test that with_tags overwrites existing tags."""
        msg = Message(
            key="temperature",
            timestamp=datetime.now(UTC),
            value=42.5,
            tags={"sensor": "TH001"},
        )

        msg2 = msg.with_tags(sensor="TH002")

        assert msg2.tags == {"sensor": "TH002"}

    def test_with_value(self):
        """Test changing message value."""
        msg = Message(
            key="temperature",
            timestamp=datetime.now(UTC),
            value=42.5,
            tags={"sensor": "TH001"},
        )

        msg2 = msg.with_value(100.0)

        # Original message unchanged
        assert msg.value == 42.5

        # New message has new value
        assert msg2.value == 100.0

        # Other fields unchanged
        assert msg2.key == msg.key
        assert msg2.tags == msg.tags
        assert msg2.timestamp == msg.timestamp


class TestRepr:
    """Test string representation."""

    def test_repr_contains_fields(self):
        """Test that repr contains key fields."""
        msg = Message(
            key="temperature",
            timestamp=datetime.now(UTC),
            value=42.5,
            tags={"sensor": "TH001"},
        )

        repr_str = repr(msg)

        assert "temperature" in repr_str
        assert "42.5" in repr_str
        assert "sensor" in repr_str


class TestValueTypes:
    """Test different value types."""

    def test_numeric_value(self):
        """Test numeric values."""
        msg = Message(
            key="temperature",
            timestamp=datetime.now(UTC),
            value=42.5,
        )
        assert msg.value == 42.5

    def test_string_value(self):
        """Test string values."""
        msg = Message(
            key="status",
            timestamp=datetime.now(UTC),
            value="OK",
        )
        assert msg.value == "OK"

    def test_dict_value(self):
        """Test dictionary values."""
        msg = Message(
            key="sensor_data",
            timestamp=datetime.now(UTC),
            value={"temp": 42.5, "humidity": 65.0},
        )
        assert msg.value == {"temp": 42.5, "humidity": 65.0}

    def test_list_value(self):
        """Test list values."""
        msg = Message(
            key="readings",
            timestamp=datetime.now(UTC),
            value=[1, 2, 3, 4, 5],
        )
        assert msg.value == [1, 2, 3, 4, 5]

    def test_none_value(self):
        """Test None value."""
        msg = Message(
            key="status",
            timestamp=datetime.now(UTC),
            value=None,
        )
        assert msg.value is None
