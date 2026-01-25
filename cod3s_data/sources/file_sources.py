"""File-based data sources for COD3S Data Framework."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

from cod3s_data.broker.base import Broker, DeliveryGuarantee
from cod3s_data.core.message import Message
from cod3s_data.sources.base import BatchMode, Source


class FileSource(Source):
    """
    Read messages from JSON/JSONL files (BATCH mode).

    Supports:
    - Single JSON file with array of messages
    - JSONL file with one message per line
    """

    def __init__(
        self,
        broker: Broker,
        channel: str,
        file_path: str | Path,
        delivery_guarantee: DeliveryGuarantee = DeliveryGuarantee.AT_MOST_ONCE,
    ) -> None:
        """
        Initialize file source.

        Args:
            broker: Message broker
            channel: Target channel
            file_path: Path to JSON/JSONL file
            delivery_guarantee: Delivery guarantee
        """
        super().__init__(broker, channel, BatchMode.BATCH, delivery_guarantee)
        self.file_path = Path(file_path)

    async def produce(self) -> AsyncIterator[Message]:
        """Read messages from file."""
        if not self.file_path.exists():
            raise FileNotFoundError(f"File not found: {self.file_path}")

        content = self.file_path.read_text()

        # Try to parse as JSON array first
        try:
            data = json.loads(content)
            if isinstance(data, list):
                # JSON array
                for item in data:
                    yield self._parse_message(item)
            else:
                # Single JSON object
                yield self._parse_message(data)

        except json.JSONDecodeError:
            # Try JSONL (one JSON object per line)
            for line in content.strip().split("\n"):
                if line.strip():
                    item = json.loads(line)
                    yield self._parse_message(item)

    def _parse_message(self, data: dict[str, Any]) -> Message:
        """Parse message from dictionary."""
        # Parse timestamp
        timestamp_str = data.get("timestamp")
        if timestamp_str:
            timestamp = datetime.fromisoformat(timestamp_str)
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
        else:
            timestamp = datetime.now(timezone.utc)

        return Message(
            key=data.get("key", "unknown"),
            timestamp=timestamp,
            value=data.get("value"),
            tags=data.get("tags", {}),
        )


class CSVSource(Source):
    """
    Read messages from CSV files (BATCH mode).

    Uses polars for performance, falls back to pandas if not available.
    """

    def __init__(
        self,
        broker: Broker,
        channel: str,
        file_path: str | Path,
        key_column: str = "key",
        timestamp_column: str = "timestamp",
        value_column: str = "value",
        tag_columns: list[str] | None = None,
        delivery_guarantee: DeliveryGuarantee = DeliveryGuarantee.AT_MOST_ONCE,
    ) -> None:
        """
        Initialize CSV source.

        Args:
            broker: Message broker
            channel: Target channel
            file_path: Path to CSV file
            key_column: Column name for message key
            timestamp_column: Column name for timestamp
            value_column: Column name for value
            tag_columns: Column names to include as tags
            delivery_guarantee: Delivery guarantee
        """
        super().__init__(broker, channel, BatchMode.BATCH, delivery_guarantee)
        self.file_path = Path(file_path)
        self.key_column = key_column
        self.timestamp_column = timestamp_column
        self.value_column = value_column
        self.tag_columns = tag_columns or []

    async def produce(self) -> AsyncIterator[Message]:
        """Read CSV and yield messages."""
        if not self.file_path.exists():
            raise FileNotFoundError(f"File not found: {self.file_path}")

        # Try polars first (fast)
        try:
            import polars as pl

            df = pl.read_csv(str(self.file_path))

            for row in df.iter_rows(named=True):
                yield self._parse_row(row)

        except ImportError:
            # Fall back to pandas
            import pandas as pd

            df = pd.read_csv(str(self.file_path))

            for _, row in df.iterrows():
                yield self._parse_row(row.to_dict())

    def _parse_row(self, row: dict[str, Any]) -> Message:
        """Parse message from CSV row."""
        # Extract fields
        key = str(row.get(self.key_column, "unknown"))

        # Parse timestamp
        timestamp_str = row.get(self.timestamp_column)
        if timestamp_str:
            # Try ISO format first
            try:
                timestamp = datetime.fromisoformat(str(timestamp_str))
            except (ValueError, TypeError):
                # Fall back to current time
                timestamp = datetime.now(timezone.utc)

            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
        else:
            timestamp = datetime.now(timezone.utc)

        # Extract value
        value = row.get(self.value_column)

        # Extract tags
        tags = {
            col: str(row[col]) for col in self.tag_columns if col in row and row[col] is not None
        }

        return Message(key=key, timestamp=timestamp, value=value, tags=tags)
