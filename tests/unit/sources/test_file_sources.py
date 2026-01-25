"""Unit tests for file sources (FileSource, CSVSource)."""

import asyncio
from pathlib import Path

import pytest

from cod3s_data.broker import InMemoryBroker
from cod3s_data.core.message import Message
from cod3s_data.sources import CSVSource, FileSource


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
