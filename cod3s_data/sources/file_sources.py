"""File-based data sources for COD3S Data Framework."""

import asyncio
import csv
import io
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

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
                timestamp = timestamp.replace(tzinfo=UTC)
        else:
            timestamp = datetime.now(UTC)

        return Message(
            key=data.get("key", "unknown"),
            timestamp=timestamp,
            value=data.get("value"),
            tags=data.get("tags", {}),
        )


class CSVSource(Source):
    """
    Read messages from CSV files (BATCH or TRANSPOSE mode).

    Uses polars for performance, falls back to pandas if not available.

    Features:
    - Custom delimiter, encoding, skip_rows, has_header, max_rows
    - Multi-value columns (value_columns → dict value)
    - Column exclusion (exclude_columns)
    - Temporal replay with speed_factor
    - Fixed key (default_key) and fixed tags (default_tags)
    - Epoch timestamp mode (timestamp_mode="epoch")
    - Pack all remaining columns as dict value (pack_remaining_as_value)
    """

    def __init__(
        self,
        broker: Broker,
        channel: str,
        file_path: str | Path,
        # --- Column mapping ---
        key_column: str = "key",
        timestamp_column: str = "timestamp",
        value_column: str = "value",
        tag_columns: list[str] | None = None,
        delivery_guarantee: DeliveryGuarantee = DeliveryGuarantee.AT_MOST_ONCE,
        # --- CSV reading ---
        delimiter: str = ",",
        encoding: str = "utf-8",
        skip_rows: int = 0,
        has_header: bool = True,
        max_rows: int | None = None,
        # --- Column selection ---
        value_columns: list[str] | None = None,
        exclude_columns: list[str] | None = None,
        # --- Replay ---
        replay: bool = False,
        speed_factor: float = 1.0,
        # --- Fixed key & tags ---
        default_key: str | None = None,
        default_tags: dict[str, str] | None = None,
        # --- Timestamp mode ---
        timestamp_mode: str = "iso",
        timestamp_microseconds_column: str | None = None,
        # --- Pack remaining columns ---
        pack_remaining_as_value: bool = False,
        # --- Column renaming ---
        column_mapping: dict[str, str] | None = None,
        # --- Timestamp rebasing ---
        rebase_timestamps: bool = False,
    ) -> None:
        """
        Initialize CSV source.

        Args:
            broker: Message broker
            channel: Target channel
            file_path: Path to CSV file
            key_column: Column name for message key (ignored if default_key is set)
            timestamp_column: Column name for timestamp
            value_column: Column name for value (ignored if value_columns or pack_remaining_as_value is set)
            tag_columns: Column names to include as tags
            delivery_guarantee: Delivery guarantee
            delimiter: CSV separator (e.g. ";" for EGM files)
            encoding: File encoding (e.g. "latin-1")
            skip_rows: Number of rows to skip before header
            has_header: False if file has no header row (columns named column_0, column_1...)
            max_rows: Maximum number of data rows to read
            value_columns: Multiple columns to pack as dict value (takes priority over value_column)
            exclude_columns: Columns to exclude from the value dict
            replay: Enable temporal replay (sleep between messages based on timestamps)
            speed_factor: Replay speed multiplier (10.0 = 10x faster)
            default_key: Fixed message key (overrides key_column when set)
            default_tags: Fixed tags merged with tags from tag_columns
            timestamp_mode: "iso" for ISO 8601 parsing (default), "epoch" for Unix epoch seconds
            timestamp_microseconds_column: Column with microseconds to add to epoch timestamp
            pack_remaining_as_value: When True, all columns not used for key/timestamp/tags/exclude
                become the value dict
            column_mapping: Optional dict mapping original column names to new names.
                Applied to dict values after construction. Unmapped keys keep their original name.
            rebase_timestamps: When True, translate all timestamps so that the first message
                has timestamp=now(). Useful for replay mode so data appears as "live" in
                time-series tools like Grafana.
        """
        batch_mode = BatchMode.TRANSPOSE if replay else BatchMode.BATCH
        super().__init__(broker, channel, batch_mode, delivery_guarantee)
        self.file_path = Path(file_path)
        self.key_column = key_column
        self.timestamp_column = timestamp_column
        self.value_column = value_column
        self.tag_columns = tag_columns or []
        self.delimiter = delimiter
        self.encoding = encoding
        self.skip_rows = skip_rows
        self.has_header = has_header
        self.max_rows = max_rows
        self.value_columns = value_columns
        self.exclude_columns = set(exclude_columns) if exclude_columns else set()
        self.replay = replay
        self.speed_factor = speed_factor
        self.default_key = default_key
        self.default_tags = default_tags or {}
        self.timestamp_mode = timestamp_mode
        self.timestamp_microseconds_column = timestamp_microseconds_column
        self.pack_remaining_as_value = pack_remaining_as_value
        self.column_mapping = column_mapping or {}
        self.rebase_timestamps = rebase_timestamps

    def _read_csv_rows(self) -> list[dict[str, Any]]:
        """Read CSV file and return list of row dicts.

        Uses polars for performance. For non-utf8 encodings, reads the file
        with Python's open() first then passes content to polars via StringIO.
        Falls back to pandas if polars is not available.
        """
        is_utf8 = self.encoding.lower().replace("-", "") == "utf8"

        try:
            import polars as pl

            if is_utf8:
                df = pl.read_csv(
                    str(self.file_path),
                    separator=self.delimiter,
                    skip_rows=self.skip_rows,
                    has_header=self.has_header,
                    n_rows=self.max_rows,
                )
            else:
                # polars only supports utf-8; decode with Python first
                content = self.file_path.read_text(encoding=self.encoding)
                # Skip rows manually from the decoded content
                if self.skip_rows:
                    lines = content.split("\n")
                    content = "\n".join(lines[self.skip_rows :])
                df = pl.read_csv(
                    io.StringIO(content),
                    separator=self.delimiter,
                    has_header=self.has_header,
                    n_rows=self.max_rows,
                )

            if not self.has_header:
                df.columns = [f"column_{i}" for i in range(len(df.columns))]
            return list(df.iter_rows(named=True))

        except ImportError:
            pass

        # Fall back to pandas (supports all encodings)
        import pandas as pd  # type: ignore[import-untyped]

        df = pd.read_csv(
            str(self.file_path),
            sep=self.delimiter,
            encoding=self.encoding,
            skiprows=self.skip_rows if self.skip_rows else None,
            header=0 if self.has_header else None,
            nrows=self.max_rows,
        )
        if not self.has_header:
            df.columns = [f"column_{i}" for i in range(len(df.columns))]
        return [row.to_dict() for _, row in df.iterrows()]

    async def produce(self) -> AsyncIterator[Message]:
        """Read CSV and yield messages, with optional temporal replay."""
        if not self.file_path.exists():
            raise FileNotFoundError(f"File not found: {self.file_path}")

        rows = self._read_csv_rows()

        prev_ts: datetime | None = None
        ts_offset: timedelta | None = None
        for row in rows:
            message = self._parse_row(row)

            if self.rebase_timestamps:
                if ts_offset is None:
                    ts_offset = datetime.now(UTC) - message.timestamp
                message = message.model_copy(update={"timestamp": message.timestamp + ts_offset})

            if self.replay and prev_ts is not None:
                delta = (message.timestamp - prev_ts).total_seconds() / self.speed_factor
                if delta > 0:
                    await asyncio.sleep(delta)

            prev_ts = message.timestamp
            yield message

    def _parse_timestamp(self, row: dict[str, Any]) -> datetime:
        """Parse timestamp from a CSV row according to ``timestamp_mode``.

        Args:
            row: Full CSV row dict (before column filtering).

        Returns:
            Timezone-aware UTC datetime.
        """
        if self.timestamp_mode == "epoch":
            raw_sec = row.get(self.timestamp_column)
            if raw_sec is not None:
                epoch = float(raw_sec)
                if self.timestamp_microseconds_column:
                    raw_usec = row.get(self.timestamp_microseconds_column)
                    if raw_usec is not None:
                        epoch += float(raw_usec) / 1_000_000
                return datetime.fromtimestamp(epoch, tz=UTC)
            return datetime.now(UTC)

        # Default: ISO 8601 parsing
        timestamp_str = row.get(self.timestamp_column)
        if timestamp_str:
            try:
                timestamp = datetime.fromisoformat(str(timestamp_str))
            except (ValueError, TypeError):
                return datetime.now(UTC)
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=UTC)
            return timestamp
        return datetime.now(UTC)

    def _parse_row(self, row: dict[str, Any]) -> Message:
        """Parse message from CSV row.

        Extraction order:
        1. Key and timestamp are read from the **full** row.
        2. ``exclude_columns`` and metadata columns are removed to build the value.
        """
        # --- Key ---
        key = (
            self.default_key
            if self.default_key is not None
            else str(row.get(self.key_column, "unknown"))
        )

        # --- Timestamp (from full row, before filtering) ---
        timestamp = self._parse_timestamp(row)

        # --- Tags ---
        tags = {
            col: str(row[col]) for col in self.tag_columns if col in row and row[col] is not None
        }
        if self.default_tags:
            tags = {**tags, **self.default_tags}

        # --- Value ---
        if self.pack_remaining_as_value:
            # Columns used for metadata (not part of the value dict)
            used_columns = set(self.tag_columns) | self.exclude_columns
            if self.default_key is None:
                used_columns.add(self.key_column)
            used_columns.add(self.timestamp_column)
            if self.timestamp_microseconds_column:
                used_columns.add(self.timestamp_microseconds_column)
            value: Any = {col: row[col] for col in row if col not in used_columns}
        elif self.value_columns:
            value = {col: row[col] for col in self.value_columns if col in row}
        else:
            value = row.get(self.value_column)

        # Apply column renaming to dict values
        if self.column_mapping and isinstance(value, dict):
            value = {self.column_mapping.get(k, k): v for k, v in value.items()}

        return Message(key=key, timestamp=timestamp, value=value, tags=tags)


class CSVWatchSource(Source):
    """
    Watch a CSV file for new lines (REALTIME mode).

    Reads the entire file on start, then polls for new lines at a configurable interval.
    Uses csv.reader for incremental reading.
    """

    def __init__(
        self,
        broker: Broker,
        channel: str,
        file_path: str | Path,
        poll_interval: float = 1.0,
        # --- Column mapping (same as CSVSource) ---
        key_column: str = "key",
        timestamp_column: str = "timestamp",
        value_column: str = "value",
        value_columns: list[str] | None = None,
        tag_columns: list[str] | None = None,
        delimiter: str = ",",
        encoding: str = "utf-8",
        has_header: bool = True,
        delivery_guarantee: DeliveryGuarantee = DeliveryGuarantee.AT_MOST_ONCE,
    ) -> None:
        """
        Initialize CSV watch source.

        Args:
            broker: Message broker
            channel: Target channel
            file_path: Path to CSV file to watch
            poll_interval: Seconds between file polls
            key_column: Column name for message key
            timestamp_column: Column name for timestamp
            value_column: Column name for value (ignored if value_columns is set)
            value_columns: Multiple columns to pack as dict value
            tag_columns: Column names to include as tags
            delimiter: CSV separator
            encoding: File encoding
            has_header: Whether file has a header row
            delivery_guarantee: Delivery guarantee
        """
        super().__init__(broker, channel, BatchMode.REALTIME, delivery_guarantee)
        self.file_path = Path(file_path)
        self.poll_interval = poll_interval
        self.key_column = key_column
        self.timestamp_column = timestamp_column
        self.value_column = value_column
        self.value_columns = value_columns
        self.tag_columns = tag_columns or []
        self.delimiter = delimiter
        self.encoding = encoding
        self.has_header = has_header
        self._headers: list[str] = []
        self._file_position: int = 0

    async def produce(self) -> AsyncIterator[Message]:
        """Watch CSV file and yield messages as new lines appear."""
        if not self.file_path.exists():
            raise FileNotFoundError(f"File not found: {self.file_path}")

        # Initial read: emit all existing content
        with open(self.file_path, encoding=self.encoding, newline="") as f:
            reader = csv.reader(f, delimiter=self.delimiter)
            if self.has_header:
                self._headers = next(reader)
            else:
                # Read first row to determine column count, then process it
                first_row = next(reader, None)
                if first_row:
                    self._headers = [f"column_{i}" for i in range(len(first_row))]
                    yield self._parse_csv_row(first_row)

            for csv_row in reader:
                if csv_row:
                    yield self._parse_csv_row(csv_row)

            self._file_position = f.tell()

        # Poll loop: check for new lines
        while self._running:
            await asyncio.sleep(self.poll_interval)

            with open(self.file_path, encoding=self.encoding, newline="") as f:
                f.seek(self._file_position)
                new_content = f.read()
                new_position = f.tell()

            if new_content.strip():
                reader = csv.reader(io.StringIO(new_content), delimiter=self.delimiter)
                for csv_row in reader:
                    if csv_row:
                        yield self._parse_csv_row(csv_row)

                self._file_position = new_position

    def _parse_csv_row(self, csv_row: list[str]) -> Message:
        """Parse a raw CSV row (list of strings) into a Message."""
        row: dict[str, Any] = dict(zip(self._headers, csv_row, strict=False))

        # Extract key
        key = str(row.get(self.key_column, "unknown"))

        # Parse timestamp
        timestamp_str = row.get(self.timestamp_column)
        if timestamp_str:
            try:
                timestamp = datetime.fromisoformat(str(timestamp_str))
            except (ValueError, TypeError):
                timestamp = datetime.now(UTC)
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=UTC)
        else:
            timestamp = datetime.now(UTC)

        # Extract value. csv.reader yields strings, so numeric-looking cells are
        # converted here; polars already does it for CSVSource. Both branches
        # convert, otherwise a value_columns stream reaches numeric transforms as
        # strings and they drop every message without saying so.
        if self.value_columns:
            value: Any = {col: _maybe_float(row[col]) for col in self.value_columns if col in row}
        else:
            value = _maybe_float(row.get(self.value_column))

        # Extract tags
        tags = {
            col: str(row[col]) for col in self.tag_columns if col in row and row[col] is not None
        }

        return Message(key=key, timestamp=timestamp, value=value, tags=tags)


def _maybe_float(raw: Any) -> Any:
    """Return ``raw`` as a float when it looks numeric, unchanged otherwise."""
    if raw is None:
        return None
    try:
        return float(raw)
    except (ValueError, TypeError):
        return raw


class DirectoryWatchSource(Source):
    """
    Watch a directory for new files (REALTIME mode).

    Polls a directory at a configurable interval and emits a message
    for each new file detected. Useful for detecting incoming data files
    (logs, sensor exports, G-code, etc.) in IoT/industrial contexts.

    Features:
    - Glob pattern filtering (e.g. ``"*.csv"``, ``"*.gcode"``)
    - Optional emission of files already present at startup
    - Detection by filename (compares sets of names between polls)
    """

    def __init__(
        self,
        broker: Broker,
        channel: str,
        directory: str | Path,
        poll_interval: float = 1.0,
        glob_pattern: str = "*",
        emit_existing: bool = False,
        delivery_guarantee: DeliveryGuarantee = DeliveryGuarantee.AT_MOST_ONCE,
    ) -> None:
        """
        Initialize directory watch source.

        Args:
            broker: Message broker
            channel: Target channel
            directory: Path to the directory to watch
            poll_interval: Seconds between directory polls
            glob_pattern: Glob pattern to filter files (e.g. ``"*.csv"``)
            emit_existing: If True, emit messages for files already present at startup
            delivery_guarantee: Delivery guarantee
        """
        super().__init__(broker, channel, BatchMode.REALTIME, delivery_guarantee)
        self.directory = Path(directory)
        self.poll_interval = poll_interval
        self.glob_pattern = glob_pattern
        self.emit_existing = emit_existing

    async def produce(self) -> AsyncIterator[Message]:
        """Watch directory and yield messages for each new file."""
        if not self.directory.is_dir():
            raise NotADirectoryError(f"Not a directory: {self.directory}")

        # Initial scan — memorize existing files
        known_files = {p.name for p in self.directory.glob(self.glob_pattern) if p.is_file()}

        if self.emit_existing:
            for path in sorted(self.directory.glob(self.glob_pattern)):
                if path.is_file():
                    yield self._file_to_message(path)

        # Polling loop
        while self._running:
            await asyncio.sleep(self.poll_interval)
            current_files = {p.name for p in self.directory.glob(self.glob_pattern) if p.is_file()}
            new_files = current_files - known_files

            for name in sorted(new_files):
                path = self.directory / name
                if path.is_file():
                    yield self._file_to_message(path)

            known_files = current_files

    def _file_to_message(self, path: Path) -> Message:
        """Build a Message from a file's metadata.

        Args:
            path: Path to the file.

        Returns:
            Message with file name, absolute path, and size in value.
        """
        stat = path.stat()
        # Use st_birthtime if available (macOS), otherwise st_ctime
        ctime = getattr(stat, "st_birthtime", stat.st_ctime)
        timestamp = datetime.fromtimestamp(ctime, tz=UTC)
        return Message(
            key=self.channel,
            timestamp=timestamp,
            value={
                "name": path.name,
                "path": str(path.resolve()),
                "size": stat.st_size,
            },
            tags={},
        )
