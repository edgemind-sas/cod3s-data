"""Unit tests for configuration system."""

import os
import tempfile
from pathlib import Path

import pytest

from cod3s_data.broker import InMemoryBroker
from cod3s_data.config import (
    ComponentFactory,
    DestinationConfig,
    PipelineConfig,
    SourceConfig,
    TransformConfig,
    load_dict,
    load_yaml,
)
from cod3s_data.destinations import ConsoleDestination, InMemoryDestination
from cod3s_data.sources import RandomSource, SequenceSource
from cod3s_data.transformations import FilterTransform, MapTransform


class TestConfigModels:
    def test_source_config(self):
        config = SourceConfig(type="random", channel="test.channel", params={"rate": 10.0})
        assert config.type == "random"
        assert config.channel == "test.channel"
        assert config.params["rate"] == 10.0

    def test_transform_config(self):
        config = TransformConfig(
            type="filter",
            input_channels="input.channel",
            output_channel="output.channel",
            params={"predicate_code": "lambda msg: msg.value > 10"},
        )
        assert config.type == "filter"
        assert config.input_channels == "input.channel"
        assert config.output_channel == "output.channel"

    def test_destination_config(self):
        config = DestinationConfig(type="console", channel_pattern="test.*", params={})
        assert config.type == "console"
        assert config.channel_pattern == "test.*"

    def test_pipeline_config(self):
        config = PipelineConfig(
            name="test_pipeline",
            sources=[SourceConfig(type="random", channel="test.channel")],
            destinations=[DestinationConfig(type="console", channel_pattern="test.*")],
        )
        assert config.name == "test_pipeline"
        assert len(config.sources) == 1
        assert len(config.destinations) == 1


class TestConfigLoaders:
    def test_load_yaml_valid(self):
        yaml_content = """
name: test_pipeline
broker:
  enable_metrics: false
  history_size: 50
sources:
  - type: random
    channel: test.channel
    params:
      rate: 10.0
destinations:
  - type: console
    channel_pattern: test.*
    params: {}
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            temp_path = Path(f.name)

        try:
            config = load_yaml(temp_path)
            assert config.name == "test_pipeline"
            assert config.broker.enable_metrics is False
            assert config.broker.history_size == 50
            assert len(config.sources) == 1
            assert config.sources[0].type == "random"
            assert len(config.destinations) == 1
        finally:
            temp_path.unlink()

    def test_load_yaml_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_yaml("/nonexistent/file.yaml")

    def test_load_yaml_empty_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("")
            f.flush()
            temp_path = Path(f.name)

        try:
            with pytest.raises(ValueError, match="Empty configuration file"):
                load_yaml(temp_path)
        finally:
            temp_path.unlink()

    def test_load_dict(self):
        config_dict = {
            "name": "test_pipeline",
            "broker": {"enable_metrics": True},
            "sources": [{"type": "random", "channel": "test.channel", "params": {}}],
            "destinations": [{"type": "console", "channel_pattern": "test.*", "params": {}}],
        }
        config = load_dict(config_dict)
        assert config.name == "test_pipeline"
        assert config.broker.enable_metrics is True
        assert len(config.sources) == 1

    def test_env_overrides(self):
        os.environ["COD3S_BROKER_ENABLE_METRICS"] = "false"
        os.environ["COD3S_BROKER_HISTORY_SIZE"] = "200"
        os.environ["COD3S_PIPELINE_NAME"] = "env_pipeline"

        try:
            config_dict = {"name": "original_name", "broker": {"enable_metrics": True}}
            config = load_dict(config_dict)
            assert config.name == "env_pipeline"
            assert config.broker.enable_metrics is False
            assert config.broker.history_size == 200
        finally:
            del os.environ["COD3S_BROKER_ENABLE_METRICS"]
            del os.environ["COD3S_BROKER_HISTORY_SIZE"]
            del os.environ["COD3S_PIPELINE_NAME"]


class TestComponentFactory:
    @pytest.mark.asyncio
    async def test_create_source(self):
        broker = InMemoryBroker(enable_metrics=False)
        factory = ComponentFactory(broker)

        config = SourceConfig(
            type="random", channel="test.channel", params={"rate": 10.0, "max_messages": 5}
        )
        source = factory.create_source(config)

        assert isinstance(source, RandomSource)
        assert source.channel == "test.channel"

    @pytest.mark.asyncio
    async def test_create_source_sequence(self):
        broker = InMemoryBroker(enable_metrics=False)
        factory = ComponentFactory(broker)

        config = SourceConfig(
            type="sequence",
            channel="test.channel",
            params={"start_value": 0, "end_value": 10, "rate": 100.0},
        )
        source = factory.create_source(config)

        assert isinstance(source, SequenceSource)

    @pytest.mark.asyncio
    async def test_create_unknown_source(self):
        broker = InMemoryBroker(enable_metrics=False)
        factory = ComponentFactory(broker)

        config = SourceConfig(type="unknown", channel="test.channel")
        with pytest.raises(ValueError, match="Unknown source type"):
            factory.create_source(config)

    @pytest.mark.asyncio
    async def test_create_transformation_filter(self):
        broker = InMemoryBroker(enable_metrics=False)
        factory = ComponentFactory(broker)

        config = TransformConfig(
            type="filter",
            input_channels="input.channel",
            output_channel="output.channel",
            params={"predicate_code": "lambda msg: msg.value > 10"},
        )
        transform = factory.create_transformation(config)

        assert isinstance(transform, FilterTransform)

    @pytest.mark.asyncio
    async def test_create_transformation_map(self):
        broker = InMemoryBroker(enable_metrics=False)
        factory = ComponentFactory(broker)

        config = TransformConfig(
            type="map",
            input_channels="input.channel",
            output_channel="output.channel",
            params={"map_fn_code": "lambda x: x * 2"},
        )
        transform = factory.create_transformation(config)

        assert isinstance(transform, MapTransform)

    @pytest.mark.asyncio
    async def test_create_unknown_transformation(self):
        broker = InMemoryBroker(enable_metrics=False)
        factory = ComponentFactory(broker)

        config = TransformConfig(
            type="unknown", input_channels="input", output_channel="output"
        )
        with pytest.raises(ValueError, match="Unknown transformation type"):
            factory.create_transformation(config)

    @pytest.mark.asyncio
    async def test_create_destination(self):
        broker = InMemoryBroker(enable_metrics=False)
        factory = ComponentFactory(broker)

        config = DestinationConfig(type="console", channel_pattern="test.*", params={})
        destination = factory.create_destination(config)

        assert isinstance(destination, ConsoleDestination)

    @pytest.mark.asyncio
    async def test_create_destination_inmemory(self):
        broker = InMemoryBroker(enable_metrics=False)
        factory = ComponentFactory(broker)

        config = DestinationConfig(
            type="inmemory", channel_pattern="test.*", params={"buffer_size": 500}
        )
        destination = factory.create_destination(config)

        assert isinstance(destination, InMemoryDestination)

    @pytest.mark.asyncio
    async def test_create_unknown_destination(self):
        broker = InMemoryBroker(enable_metrics=False)
        factory = ComponentFactory(broker)

        config = DestinationConfig(type="unknown", channel_pattern="test.*")
        with pytest.raises(ValueError, match="Unknown destination type"):
            factory.create_destination(config)

    @pytest.mark.asyncio
    async def test_register_custom_source(self):
        broker = InMemoryBroker(enable_metrics=False)
        factory = ComponentFactory(broker)

        class CustomSource:
            def __init__(self, broker, channel, **kwargs):
                self.broker = broker
                self.channel = channel

        factory.register_source("custom", CustomSource)

        config = SourceConfig(type="custom", channel="test.channel", params={})
        source = factory.create_source(config)

        assert isinstance(source, CustomSource)


class TestIntegration:
    @pytest.mark.asyncio
    async def test_full_pipeline_from_config(self):
        yaml_content = """
name: integration_test
broker:
  enable_metrics: false
sources:
  - type: sequence
    channel: input.channel
    params:
      start_value: 0
      end_value: 5
      rate: 1000.0
transformations:
  - type: map
    input_channels: input.channel
    output_channel: output.channel
    params:
      map_fn_code: "lambda x: x * 2"
destinations:
  - type: inmemory
    channel_pattern: output.channel
    params: {}
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            temp_path = Path(f.name)

        try:
            config = load_yaml(temp_path)
            assert config.name == "integration_test"
            assert len(config.sources) == 1
            assert len(config.transformations) == 1
            assert len(config.destinations) == 1

            # Verify we can create components from config
            broker = InMemoryBroker(enable_metrics=config.broker.enable_metrics)
            factory = ComponentFactory(broker)

            source = factory.create_source(config.sources[0])
            transform = factory.create_transformation(config.transformations[0])
            destination = factory.create_destination(config.destinations[0])

            assert source is not None
            assert transform is not None
            assert destination is not None
        finally:
            temp_path.unlink()
