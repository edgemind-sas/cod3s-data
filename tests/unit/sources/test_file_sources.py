"""Unit tests for file sources (FileSource, CSVSource, CSVWatchSource, DirectoryWatchSource)."""

import asyncio
import contextlib
import time
from pathlib import Path

import pytest

from cod3s_data.broker import InMemoryBroker
from cod3s_data.core.message import Message
from cod3s_data.sources import CSVSource, CSVWatchSource, DirectoryWatchSource, FileSource


class TestFileSource:
    """Test FileSource."""

    @pytest.mark.asyncio
    async def test_file_source_reads_json_array(self):
        """Test FileSource reading JSON array."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        received = []

        async def callback(msg: Message):
            received.append(msg)

        broker.subscribe("test.channel", callback)

        # Get fixture path
        fixture_path = Path(__file__).parent.parent.parent / "fixtures" / "test_messages.json"

        source = FileSource(
            broker=broker,
            channel="test.channel",
            file_path=fixture_path,
        )

        await source.start()
        await asyncio.sleep(0.05)

        # Should have received 3 messages
        assert len(received) == 3

        # Check first message
        assert received[0].key == "temperature"
        assert received[0].value == 25.5
        assert received[0].tags["sensor"] == "TH001"

        await broker.stop()

    @pytest.mark.asyncio
    async def test_file_source_reads_jsonl(self):
        """Test FileSource reading JSONL."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        received = []

        async def callback(msg: Message):
            received.append(msg)

        broker.subscribe("test.channel", callback)

        # Get fixture path
        fixture_path = Path(__file__).parent.parent.parent / "fixtures" / "test_messages.jsonl"

        source = FileSource(
            broker=broker,
            channel="test.channel",
            file_path=fixture_path,
        )

        await source.start()
        await asyncio.sleep(0.05)

        # Should have received 3 messages
        assert len(received) == 3

        # Check messages
        assert received[0].key == "temperature"
        assert received[1].key == "temperature"
        assert received[2].key == "humidity"

        await broker.stop()

    @pytest.mark.asyncio
    async def test_file_source_file_not_found(self):
        """Test FileSource with nonexistent file."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        source = FileSource(
            broker=broker,
            channel="test.channel",
            file_path="/nonexistent/file.json",
        )

        with pytest.raises(FileNotFoundError):
            await source.start()

        await broker.stop()


class TestCSVSource:
    """Test CSVSource."""

    @pytest.mark.asyncio
    async def test_csv_source_reads_csv(self):
        """Test CSVSource reading CSV file."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        received = []

        async def callback(msg: Message):
            received.append(msg)

        broker.subscribe("test.channel", callback)

        # Get fixture path
        fixture_path = Path(__file__).parent.parent.parent / "fixtures" / "test_data.csv"

        source = CSVSource(
            broker=broker,
            channel="test.channel",
            file_path=fixture_path,
            key_column="key",
            timestamp_column="timestamp",
            value_column="value",
            tag_columns=["sensor", "location"],
        )

        await source.start()
        await asyncio.sleep(0.05)

        # Should have received 4 messages
        assert len(received) == 4

        # Check first message
        assert received[0].key == "temperature"
        assert received[0].value == 25.5
        assert received[0].tags["sensor"] == "TH001"
        assert received[0].tags["location"] == "room1"

        # Check last message
        assert received[3].key == "pressure"
        assert received[3].value == 1013.25

        await broker.stop()

    @pytest.mark.asyncio
    async def test_csv_source_custom_columns(self):
        """Test CSVSource with custom column names."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        received = []

        async def callback(msg: Message):
            received.append(msg)

        broker.subscribe("test.channel", callback)

        fixture_path = Path(__file__).parent.parent.parent / "fixtures" / "test_data.csv"

        # Use sensor as key column
        source = CSVSource(
            broker=broker,
            channel="test.channel",
            file_path=fixture_path,
            key_column="sensor",  # Different column
            timestamp_column="timestamp",
            value_column="value",
            tag_columns=["location"],
        )

        await source.start()
        await asyncio.sleep(0.05)

        # Check that key comes from sensor column
        assert received[0].key == "TH001"
        assert received[2].key == "HU001"

        await broker.stop()

    @pytest.mark.asyncio
    async def test_csv_source_no_tags(self):
        """Test CSVSource without tag columns."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        received = []

        async def callback(msg: Message):
            received.append(msg)

        broker.subscribe("test.channel", callback)

        fixture_path = Path(__file__).parent.parent.parent / "fixtures" / "test_data.csv"

        source = CSVSource(
            broker=broker,
            channel="test.channel",
            file_path=fixture_path,
            key_column="key",
            timestamp_column="timestamp",
            value_column="value",
            tag_columns=[],  # No tags
        )

        await source.start()
        await asyncio.sleep(0.05)

        # Check that messages have no tags
        assert len(received[0].tags) == 0

        await broker.stop()

    @pytest.mark.asyncio
    async def test_csv_source_file_not_found(self):
        """Test CSVSource with nonexistent file."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        source = CSVSource(
            broker=broker,
            channel="test.channel",
            file_path="/nonexistent/file.csv",
        )

        with pytest.raises(FileNotFoundError):
            await source.start()

        await broker.stop()

    @pytest.mark.asyncio
    async def test_csv_source_delimiter(self):
        """Test CSVSource with semicolon delimiter."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        received: list[Message] = []

        async def callback(msg: Message):
            received.append(msg)

        broker.subscribe("test.channel", callback)

        fixture_path = Path(__file__).parent.parent.parent / "fixtures" / "test_data_semicolon.csv"

        source = CSVSource(
            broker=broker,
            channel="test.channel",
            file_path=fixture_path,
            delimiter=";",
            tag_columns=["sensor", "location"],
        )

        await source.start()
        await asyncio.sleep(0.05)

        assert len(received) == 3
        assert received[0].key == "temperature"
        assert received[0].value == 25.5
        assert received[0].tags["sensor"] == "TH001"

        await broker.stop()

    @pytest.mark.asyncio
    async def test_csv_source_max_rows(self):
        """Test CSVSource with max_rows limit."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        received: list[Message] = []

        async def callback(msg: Message):
            received.append(msg)

        broker.subscribe("test.channel", callback)

        fixture_path = Path(__file__).parent.parent.parent / "fixtures" / "test_data.csv"

        source = CSVSource(
            broker=broker,
            channel="test.channel",
            file_path=fixture_path,
            max_rows=2,
        )

        await source.start()
        await asyncio.sleep(0.05)

        assert len(received) == 2

        await broker.stop()

    @pytest.mark.asyncio
    async def test_csv_source_value_columns(self):
        """Test CSVSource with value_columns producing dict values."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        received: list[Message] = []

        async def callback(msg: Message):
            received.append(msg)

        broker.subscribe("test.channel", callback)

        fixture_path = Path(__file__).parent.parent.parent / "fixtures" / "test_data.csv"

        source = CSVSource(
            broker=broker,
            channel="test.channel",
            file_path=fixture_path,
            value_columns=["value", "sensor"],
        )

        await source.start()
        await asyncio.sleep(0.05)

        assert len(received) == 4
        # value should be a dict with both columns
        assert isinstance(received[0].value, dict)
        assert received[0].value["value"] == 25.5
        assert received[0].value["sensor"] == "TH001"

        await broker.stop()

    @pytest.mark.asyncio
    async def test_csv_source_value_columns_priority_over_value_column(self):
        """Test that value_columns takes priority over value_column."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        received: list[Message] = []

        async def callback(msg: Message):
            received.append(msg)

        broker.subscribe("test.channel", callback)

        fixture_path = Path(__file__).parent.parent.parent / "fixtures" / "test_data.csv"

        source = CSVSource(
            broker=broker,
            channel="test.channel",
            file_path=fixture_path,
            value_column="value",
            value_columns=["value", "sensor"],
        )

        await source.start()
        await asyncio.sleep(0.05)

        # value_columns should take priority → dict value
        assert isinstance(received[0].value, dict)
        assert "value" in received[0].value
        assert "sensor" in received[0].value

        await broker.stop()

    @pytest.mark.asyncio
    async def test_csv_source_exclude_columns(self):
        """Test that exclude_columns removes columns from the value dict."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        received: list[Message] = []

        async def callback(msg: Message):
            received.append(msg)

        broker.subscribe("test.channel", callback)

        fixture_path = Path(__file__).parent.parent.parent / "fixtures" / "test_data.csv"

        source = CSVSource(
            broker=broker,
            channel="test.channel",
            file_path=fixture_path,
            tag_columns=["sensor"],
            exclude_columns=["location"],
            pack_remaining_as_value=True,
        )

        await source.start()
        await asyncio.sleep(0.05)

        # location should be excluded from the value dict
        assert "location" not in received[0].value
        # sensor (tag column) should also not be in the value dict
        assert "sensor" not in received[0].value
        # value should still contain the 'value' column from CSV
        assert "value" in received[0].value
        # tags should still work
        assert "sensor" in received[0].tags

        await broker.stop()

    @pytest.mark.asyncio
    async def test_csv_source_skip_rows(self):
        """Test CSVSource with skip_rows."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        received: list[Message] = []

        async def callback(msg: Message):
            received.append(msg)

        broker.subscribe("test.channel", callback)

        # Create a CSV fixture with extra rows at the top
        import tempfile

        csv_content = (
            "# comment line 1\n"
            "# comment line 2\n"
            "key,timestamp,value\n"
            "temperature,2024-01-15T10:00:00Z,25.5\n"
            "humidity,2024-01-15T10:00:00Z,65.0\n"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(csv_content)
            tmp_path = f.name

        source = CSVSource(
            broker=broker,
            channel="test.channel",
            file_path=tmp_path,
            skip_rows=2,
        )

        await source.start()
        await asyncio.sleep(0.05)

        assert len(received) == 2
        assert received[0].key == "temperature"
        assert received[1].key == "humidity"

        Path(tmp_path).unlink()
        await broker.stop()

    @pytest.mark.asyncio
    async def test_csv_source_no_header(self):
        """Test CSVSource with has_header=False (columns named by position)."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        received: list[Message] = []

        async def callback(msg: Message):
            received.append(msg)

        broker.subscribe("test.channel", callback)

        fixture_path = Path(__file__).parent.parent.parent / "fixtures" / "test_data_noheader.csv"

        source = CSVSource(
            broker=broker,
            channel="test.channel",
            file_path=fixture_path,
            has_header=False,
            key_column="column_0",
            timestamp_column="column_1",
            value_column="column_2",
            tag_columns=["column_3"],
        )

        await source.start()
        await asyncio.sleep(0.05)

        assert len(received) == 2
        assert received[0].key == "temperature"
        assert received[1].key == "humidity"
        assert received[0].tags["column_3"] == "TH001"

        await broker.stop()

    @pytest.mark.asyncio
    async def test_csv_source_encoding(self):
        """Test CSVSource with non-utf8 encoding (latin-1)."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        received: list[Message] = []

        async def callback(msg: Message):
            received.append(msg)

        broker.subscribe("test.channel", callback)

        import tempfile

        csv_content = (
            "key,timestamp,value,label\ntempérature,2024-01-15T10:00:00Z,25.5,capteur café\n"
        )
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="latin-1"
        ) as f:
            f.write(csv_content)
            tmp_path = f.name

        source = CSVSource(
            broker=broker,
            channel="test.channel",
            file_path=tmp_path,
            encoding="latin-1",
            tag_columns=["label"],
        )

        await source.start()
        await asyncio.sleep(0.05)

        assert len(received) == 1
        assert received[0].key == "température"
        assert received[0].tags["label"] == "capteur café"

        Path(tmp_path).unlink()
        await broker.stop()

    @pytest.mark.asyncio
    async def test_csv_source_replay(self):
        """Test CSVSource replay mode adds delay between messages."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        received: list[Message] = []

        async def callback(msg: Message):
            received.append(msg)

        broker.subscribe("test.channel", callback)

        # Create CSV with 1-second gaps between timestamps
        import tempfile

        csv_content = (
            "key,timestamp,value\n"
            "t,2024-01-15T10:00:00Z,1\n"
            "t,2024-01-15T10:00:01Z,2\n"
            "t,2024-01-15T10:00:02Z,3\n"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(csv_content)
            tmp_path = f.name

        source = CSVSource(
            broker=broker,
            channel="test.channel",
            file_path=tmp_path,
            replay=True,
            speed_factor=100.0,  # 100x speed to keep test fast
        )

        start = time.monotonic()
        await source.start()
        elapsed = time.monotonic() - start
        await asyncio.sleep(0.05)

        assert len(received) == 3
        # 2 seconds total delay at 100x speed = 0.02s minimum
        assert elapsed >= 0.01

        Path(tmp_path).unlink()
        await broker.stop()

    @pytest.mark.asyncio
    async def test_csv_source_replay_speed_factor(self):
        """Test CSVSource replay speed_factor controls delay."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        received: list[Message] = []

        async def callback(msg: Message):
            received.append(msg)

        broker.subscribe("test.channel", callback)

        import tempfile

        csv_content = "key,timestamp,value\nt,2024-01-15T10:00:00Z,1\nt,2024-01-15T10:00:10Z,2\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(csv_content)
            tmp_path = f.name

        # At 1000x speed, 10 seconds → 0.01s
        source = CSVSource(
            broker=broker,
            channel="test.channel",
            file_path=tmp_path,
            replay=True,
            speed_factor=1000.0,
        )

        start = time.monotonic()
        await source.start()
        elapsed = time.monotonic() - start
        await asyncio.sleep(0.05)

        assert len(received) == 2
        # Should be fast (~0.01s), not 10s
        assert elapsed < 1.0

        Path(tmp_path).unlink()
        await broker.stop()


class TestCSVSourceNewFeatures:
    """Tests for default_key, default_tags, timestamp_mode, pack_remaining_as_value."""

    @pytest.mark.asyncio
    async def test_default_key(self):
        """Test that default_key overrides key_column."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        received: list[Message] = []
        broker.subscribe("ch", lambda msg: received.append(msg))

        fixture_path = Path(__file__).parent.parent.parent / "fixtures" / "test_data.csv"
        source = CSVSource(
            broker=broker,
            channel="ch",
            file_path=fixture_path,
            default_key="fixed_key",
        )

        await source.start()
        await asyncio.sleep(0.05)

        assert len(received) == 4
        assert all(m.key == "fixed_key" for m in received)
        await broker.stop()

    @pytest.mark.asyncio
    async def test_default_tags(self):
        """Test that default_tags are merged with tag_columns."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        received: list[Message] = []
        broker.subscribe("ch", lambda msg: received.append(msg))

        fixture_path = Path(__file__).parent.parent.parent / "fixtures" / "test_data.csv"
        source = CSVSource(
            broker=broker,
            channel="ch",
            file_path=fixture_path,
            tag_columns=["sensor"],
            default_tags={"source": "test", "env": "ci"},
        )

        await source.start()
        await asyncio.sleep(0.05)

        assert len(received) == 4
        # default_tags are present
        assert received[0].tags["source"] == "test"
        assert received[0].tags["env"] == "ci"
        # tag_columns value also present
        assert received[0].tags["sensor"] == "TH001"
        await broker.stop()

    @pytest.mark.asyncio
    async def test_timestamp_epoch_mode(self):
        """Test timestamp_mode='epoch' reads epoch seconds."""
        import tempfile

        csv_content = "key,ts,value\na,1700000000,42\nb,1700000060,43\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(csv_content)
            tmp_path = f.name

        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        received: list[Message] = []
        broker.subscribe("ch", lambda msg: received.append(msg))

        source = CSVSource(
            broker=broker,
            channel="ch",
            file_path=tmp_path,
            timestamp_column="ts",
            timestamp_mode="epoch",
        )

        await source.start()
        await asyncio.sleep(0.05)

        assert len(received) == 2
        from datetime import UTC, datetime

        expected = datetime.fromtimestamp(1700000000, tz=UTC)
        assert received[0].timestamp == expected
        assert received[1].timestamp == datetime.fromtimestamp(1700000060, tz=UTC)

        Path(tmp_path).unlink()
        await broker.stop()

    @pytest.mark.asyncio
    async def test_timestamp_epoch_with_microseconds(self):
        """Test epoch mode with a separate microseconds column."""
        import tempfile

        csv_content = "key,sec,usec,value\na,1700000000,500000,42\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(csv_content)
            tmp_path = f.name

        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        received: list[Message] = []
        broker.subscribe("ch", lambda msg: received.append(msg))

        source = CSVSource(
            broker=broker,
            channel="ch",
            file_path=tmp_path,
            timestamp_column="sec",
            timestamp_microseconds_column="usec",
            timestamp_mode="epoch",
        )

        await source.start()
        await asyncio.sleep(0.05)

        assert len(received) == 1
        from datetime import UTC, datetime

        expected = datetime.fromtimestamp(1700000000.5, tz=UTC)
        assert received[0].timestamp == expected

        Path(tmp_path).unlink()
        await broker.stop()

    @pytest.mark.asyncio
    async def test_pack_remaining_as_value(self):
        """Test pack_remaining_as_value packs all non-metadata columns."""
        import tempfile

        csv_content = "key,timestamp,sensor,temp,pressure\na,2024-01-15T10:00:00Z,S1,25.5,1013\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(csv_content)
            tmp_path = f.name

        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        received: list[Message] = []
        broker.subscribe("ch", lambda msg: received.append(msg))

        source = CSVSource(
            broker=broker,
            channel="ch",
            file_path=tmp_path,
            tag_columns=["sensor"],
            pack_remaining_as_value=True,
        )

        await source.start()
        await asyncio.sleep(0.05)

        assert len(received) == 1
        value = received[0].value
        assert isinstance(value, dict)
        # temp and pressure should be in the value
        assert "temp" in value
        assert "pressure" in value
        # key, timestamp, and sensor (tag) should NOT be in the value
        assert "key" not in value
        assert "timestamp" not in value
        assert "sensor" not in value

        Path(tmp_path).unlink()
        await broker.stop()

    @pytest.mark.asyncio
    async def test_pack_remaining_excludes_metadata_columns(self):
        """Test that pack_remaining excludes key, timestamp, usec, tags, and exclude_columns."""
        import tempfile

        csv_content = "sec,usec,tag1,col_a,col_b,junk\n1700000000,500000,x,10,20,99\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(csv_content)
            tmp_path = f.name

        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        received: list[Message] = []
        broker.subscribe("ch", lambda msg: received.append(msg))

        source = CSVSource(
            broker=broker,
            channel="ch",
            file_path=tmp_path,
            default_key="reading",
            timestamp_column="sec",
            timestamp_microseconds_column="usec",
            timestamp_mode="epoch",
            tag_columns=["tag1"],
            exclude_columns=["junk"],
            pack_remaining_as_value=True,
        )

        await source.start()
        await asyncio.sleep(0.05)

        assert len(received) == 1
        value = received[0].value
        assert isinstance(value, dict)
        # Only col_a and col_b should remain
        assert set(value.keys()) == {"col_a", "col_b"}
        # Verify metadata is correctly extracted
        assert received[0].key == "reading"
        assert received[0].tags["tag1"] == "x"

        Path(tmp_path).unlink()
        await broker.stop()


class TestCSVWatchSource:
    """Test CSVWatchSource."""

    @pytest.mark.asyncio
    async def test_csv_watch_initial_read(self):
        """Test CSVWatchSource reads existing file on start."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        received: list[Message] = []

        async def callback(msg: Message):
            received.append(msg)

        broker.subscribe("test.channel", callback)

        fixture_path = Path(__file__).parent.parent.parent / "fixtures" / "test_data.csv"

        source = CSVWatchSource(
            broker=broker,
            channel="test.channel",
            file_path=fixture_path,
            poll_interval=0.1,
            tag_columns=["sensor", "location"],
        )

        # Start source and stop after initial read
        task = asyncio.create_task(source.start())
        await asyncio.sleep(0.2)
        await source.stop()
        await asyncio.sleep(0.05)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

        # Should have received all 4 existing messages
        assert len(received) == 4
        assert received[0].key == "temperature"

        await broker.stop()

    @pytest.mark.asyncio
    async def test_csv_watch_detects_new_lines(self, tmp_path: Path):
        """Test CSVWatchSource detects and emits new lines added to file."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        received: list[Message] = []

        async def callback(msg: Message):
            received.append(msg)

        broker.subscribe("test.channel", callback)

        # Create initial CSV
        csv_file = tmp_path / "watch_test.csv"
        csv_file.write_text("key,timestamp,value\ntemperature,2024-01-15T10:00:00Z,25.5\n")

        source = CSVWatchSource(
            broker=broker,
            channel="test.channel",
            file_path=csv_file,
            poll_interval=0.1,
        )

        task = asyncio.create_task(source.start())
        await asyncio.sleep(0.2)

        # Should have received 1 message from initial read
        assert len(received) == 1

        # Append new line
        with open(csv_file, "a") as f:
            f.write("humidity,2024-01-15T10:01:00Z,65.0\n")

        # Wait for poll to pick it up
        await asyncio.sleep(0.3)

        assert len(received) == 2
        assert received[1].key == "humidity"

        await source.stop()
        await asyncio.sleep(0.05)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

        await broker.stop()

    @pytest.mark.asyncio
    async def test_csv_watch_stop(self, tmp_path: Path):
        """Test CSVWatchSource stops properly."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        csv_file = tmp_path / "watch_stop.csv"
        csv_file.write_text("key,timestamp,value\nt,2024-01-15T10:00:00Z,1\n")

        source = CSVWatchSource(
            broker=broker,
            channel="test.channel",
            file_path=csv_file,
            poll_interval=0.1,
        )

        task = asyncio.create_task(source.start())
        await asyncio.sleep(0.2)

        await source.stop()
        await asyncio.sleep(0.1)

        assert not source.is_running

        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

        await broker.stop()


class TestDirectoryWatchSource:
    """Test DirectoryWatchSource."""

    @pytest.mark.asyncio
    async def test_detects_new_file(self, tmp_path: Path):
        """A file added after start() is detected and a message is emitted."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        received: list[Message] = []

        async def callback(msg: Message):
            received.append(msg)

        broker.subscribe("files.new", callback)

        source = DirectoryWatchSource(
            broker=broker,
            channel="files.new",
            directory=tmp_path,
            poll_interval=0.1,
        )

        task = asyncio.create_task(source.start())
        await asyncio.sleep(0.15)

        # No messages yet (empty directory)
        assert len(received) == 0

        # Create a new file
        (tmp_path / "data_001.csv").write_text("hello")
        await asyncio.sleep(0.25)

        assert len(received) == 1
        assert received[0].value["name"] == "data_001.csv"

        await source.stop()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

        await broker.stop()

    @pytest.mark.asyncio
    async def test_ignores_existing_files(self, tmp_path: Path):
        """Files present at startup do not generate messages (default)."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        received: list[Message] = []

        async def callback(msg: Message):
            received.append(msg)

        broker.subscribe("files.new", callback)

        # Create files before starting the source
        (tmp_path / "existing1.txt").write_text("a")
        (tmp_path / "existing2.txt").write_text("b")

        source = DirectoryWatchSource(
            broker=broker,
            channel="files.new",
            directory=tmp_path,
            poll_interval=0.1,
        )

        task = asyncio.create_task(source.start())
        await asyncio.sleep(0.25)

        # No messages — existing files are ignored
        assert len(received) == 0

        await source.stop()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

        await broker.stop()

    @pytest.mark.asyncio
    async def test_emit_existing(self, tmp_path: Path):
        """With emit_existing=True, existing files are emitted at startup."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        received: list[Message] = []

        async def callback(msg: Message):
            received.append(msg)

        broker.subscribe("files.new", callback)

        (tmp_path / "a.txt").write_text("aaa")
        (tmp_path / "b.txt").write_text("bbb")

        source = DirectoryWatchSource(
            broker=broker,
            channel="files.new",
            directory=tmp_path,
            poll_interval=0.1,
            emit_existing=True,
        )

        task = asyncio.create_task(source.start())
        await asyncio.sleep(0.25)

        assert len(received) == 2
        names = {m.value["name"] for m in received}
        assert names == {"a.txt", "b.txt"}

        await source.stop()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

        await broker.stop()

    @pytest.mark.asyncio
    async def test_glob_pattern_filter(self, tmp_path: Path):
        """Only files matching the glob pattern are detected."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        received: list[Message] = []

        async def callback(msg: Message):
            received.append(msg)

        broker.subscribe("files.new", callback)

        source = DirectoryWatchSource(
            broker=broker,
            channel="files.new",
            directory=tmp_path,
            poll_interval=0.1,
            glob_pattern="*.csv",
        )

        task = asyncio.create_task(source.start())
        await asyncio.sleep(0.15)

        # Create one matching and one non-matching file
        (tmp_path / "data.csv").write_text("csv data")
        (tmp_path / "data.json").write_text("{}")
        await asyncio.sleep(0.25)

        # Only the .csv file should be detected
        assert len(received) == 1
        assert received[0].value["name"] == "data.csv"

        await source.stop()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

        await broker.stop()

    @pytest.mark.asyncio
    async def test_message_content(self, tmp_path: Path):
        """The message value contains name, path, and size."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        received: list[Message] = []

        async def callback(msg: Message):
            received.append(msg)

        broker.subscribe("files.new", callback)

        source = DirectoryWatchSource(
            broker=broker,
            channel="files.new",
            directory=tmp_path,
            poll_interval=0.1,
        )

        task = asyncio.create_task(source.start())
        await asyncio.sleep(0.15)

        file_content = "hello world"
        (tmp_path / "test.txt").write_text(file_content)
        await asyncio.sleep(0.25)

        assert len(received) == 1
        msg = received[0]

        # Check key
        assert msg.key == "files.new"

        # Check value fields
        assert msg.value["name"] == "test.txt"
        assert msg.value["path"] == str((tmp_path / "test.txt").resolve())
        assert msg.value["size"] == len(file_content)

        # Check tags is empty dict
        assert msg.tags == {}

        # Check timestamp is set
        assert msg.timestamp is not None

        await source.stop()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

        await broker.stop()

    @pytest.mark.asyncio
    async def test_not_a_directory_error(self, tmp_path: Path):
        """NotADirectoryError is raised if the path is not a directory."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        # Point to a file, not a directory
        file_path = tmp_path / "not_a_dir.txt"
        file_path.write_text("I am a file")

        source = DirectoryWatchSource(
            broker=broker,
            channel="files.new",
            directory=file_path,
            poll_interval=0.1,
        )

        with pytest.raises(NotADirectoryError):
            await source.start()

        await broker.stop()

    @pytest.mark.asyncio
    async def test_multiple_new_files(self, tmp_path: Path):
        """Multiple files added at once are all detected."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        received: list[Message] = []

        async def callback(msg: Message):
            received.append(msg)

        broker.subscribe("files.new", callback)

        source = DirectoryWatchSource(
            broker=broker,
            channel="files.new",
            directory=tmp_path,
            poll_interval=0.1,
        )

        task = asyncio.create_task(source.start())
        await asyncio.sleep(0.15)

        # Create multiple files at once
        (tmp_path / "file_a.txt").write_text("a")
        (tmp_path / "file_b.txt").write_text("bb")
        (tmp_path / "file_c.txt").write_text("ccc")
        await asyncio.sleep(0.25)

        assert len(received) == 3
        names = sorted(m.value["name"] for m in received)
        assert names == ["file_a.txt", "file_b.txt", "file_c.txt"]

        await source.stop()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

        await broker.stop()


class TestSourceIntegration:
    """Integration tests for sources."""

    @pytest.mark.asyncio
    async def test_multiple_sources_same_channel(self):
        """Test multiple sources publishing to same channel."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        received = []

        async def callback(msg: Message):
            received.append(msg)

        broker.subscribe("test.channel", callback)

        # Create two sources
        from cod3s_data.sources import SequenceSource

        source1 = SequenceSource(
            broker=broker,
            channel="test.channel",
            start_value=0,
            end_value=3,
            rate=100.0,
        )

        source2 = SequenceSource(
            broker=broker,
            channel="test.channel",
            start_value=100,
            end_value=103,
            rate=100.0,
        )

        # Run both sources
        await asyncio.gather(source1.start(), source2.start())

        await asyncio.sleep(0.05)

        # Should have received messages from both sources
        assert len(received) == 6

        values = sorted([msg.value for msg in received])
        assert values == [0, 1, 2, 100, 101, 102]

        await broker.stop()

    @pytest.mark.asyncio
    async def test_source_to_different_channels(self):
        """Test sources publishing to different channels."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        channel1_received = []
        channel2_received = []

        async def callback1(msg: Message):
            channel1_received.append(msg)

        async def callback2(msg: Message):
            channel2_received.append(msg)

        broker.subscribe("channel1", callback1)
        broker.subscribe("channel2", callback2)

        from cod3s_data.sources import SequenceSource

        source1 = SequenceSource(
            broker=broker,
            channel="channel1",
            start_value=0,
            end_value=2,
            rate=100.0,
        )

        source2 = SequenceSource(
            broker=broker,
            channel="channel2",
            start_value=10,
            end_value=12,
            rate=100.0,
        )

        await asyncio.gather(source1.start(), source2.start())

        await asyncio.sleep(0.05)

        # Each channel should receive its own messages
        assert len(channel1_received) == 2
        assert len(channel2_received) == 2

        assert channel1_received[0].value == 0
        assert channel2_received[0].value == 10

        await broker.stop()
