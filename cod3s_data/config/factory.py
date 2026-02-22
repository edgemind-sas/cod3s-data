"""Component factory for COD3S Data Framework."""

from collections.abc import Callable
from typing import Any

from cod3s_data.broker.base import Broker
from cod3s_data.config.models import DestinationConfig, SourceConfig, TransformConfig
from cod3s_data.destinations.base import Destination
from cod3s_data.destinations.collect import CollectDestination
from cod3s_data.destinations.core import ConsoleDestination, FileDestination, InMemoryDestination
from cod3s_data.destinations.influxdb import InfluxDBDestination
from cod3s_data.sources.base import Source
from cod3s_data.sources.file_sources import CSVSource, CSVWatchSource, FileSource
from cod3s_data.sources.test_sources import RandomSource, SequenceSource
from cod3s_data.transformations.base import Transformation
from cod3s_data.transformations.builtin import (
    AggregateTransform,
    FilterTransform,
    MapTransform,
)


class ComponentFactory:
    """Factory for creating components from configuration."""

    def __init__(self, broker: Broker) -> None:
        self.broker = broker
        self._source_registry: dict[str, Callable[..., Source]] = {
            "random": RandomSource,
            "sequence": SequenceSource,
            "file": FileSource,
            "csv": CSVSource,
            "csv_watch": CSVWatchSource,
        }
        self._transform_registry: dict[str, Callable[..., Transformation]] = {
            "filter": self._create_filter_transform,
            "map": self._create_map_transform,
            "aggregate": self._create_aggregate_transform,
        }
        self._destination_registry: dict[str, Callable[..., Destination]] = {
            "console": ConsoleDestination,
            "file": FileDestination,
            "inmemory": InMemoryDestination,
            "collect": CollectDestination,
            "influxdb": InfluxDBDestination,
        }

    def create_source(self, config: SourceConfig) -> Source:
        """Create source from configuration.

        Args:
            config: Source configuration

        Returns:
            Source instance

        Raises:
            ValueError: If source type is unknown
        """
        if config.type not in self._source_registry:
            raise ValueError(f"Unknown source type: {config.type}")

        source_class = self._source_registry[config.type]
        return source_class(self.broker, config.channel, **config.params)

    def create_transformation(self, config: TransformConfig) -> Transformation:
        """Create transformation from configuration.

        Args:
            config: Transformation configuration

        Returns:
            Transformation instance

        Raises:
            ValueError: If transformation type is unknown
        """
        if config.type not in self._transform_registry:
            raise ValueError(f"Unknown transformation type: {config.type}")

        transform_fn = self._transform_registry[config.type]
        return transform_fn(
            self.broker, config.input_channels, config.output_channel, **config.params
        )

    def create_destination(self, config: DestinationConfig) -> Destination:
        """Create destination from configuration.

        Args:
            config: Destination configuration

        Returns:
            Destination instance

        Raises:
            ValueError: If destination type is unknown
        """
        if config.type not in self._destination_registry:
            raise ValueError(f"Unknown destination type: {config.type}")

        dest_class = self._destination_registry[config.type]
        return dest_class(self.broker, config.channel_pattern, **config.params)

    @property
    def registered_source_types(self) -> set[str]:
        """Return the set of registered source type names."""
        return set(self._source_registry.keys())

    @property
    def registered_transformation_types(self) -> set[str]:
        """Return the set of registered transformation type names."""
        return set(self._transform_registry.keys())

    @property
    def registered_destination_types(self) -> set[str]:
        """Return the set of registered destination type names."""
        return set(self._destination_registry.keys())

    def register_source(self, name: str, source_class: Callable[..., Source]) -> None:
        """Register custom source type."""
        self._source_registry[name] = source_class

    def register_transformation(
        self, name: str, transform_class: Callable[..., Transformation]
    ) -> None:
        """Register custom transformation type."""
        self._transform_registry[name] = transform_class

    def register_destination(
        self, name: str, destination_class: Callable[..., Destination]
    ) -> None:
        """Register custom destination type."""
        self._destination_registry[name] = destination_class

    def _create_filter_transform(
        self,
        broker: Broker,
        input_channels: str | list[str],
        output_channel: str,
        predicate_code: str | None = None,
        **kwargs: Any,
    ) -> FilterTransform:
        """Create FilterTransform from config.

        The predicate can be provided as Python code string that will be eval'd.
        For security, this should only be used with trusted configurations.
        """
        if predicate_code:
            # Create predicate function from code string
            # WARNING: eval is unsafe with untrusted input
            predicate = eval(predicate_code)  # noqa: S307
        elif "predicate" in kwargs:
            predicate = kwargs.pop("predicate")
        else:
            raise ValueError("FilterTransform requires 'predicate' or 'predicate_code' parameter")

        return FilterTransform(broker, input_channels, output_channel, predicate)

    def _create_map_transform(
        self,
        broker: Broker,
        input_channels: str | list[str],
        output_channel: str,
        map_fn_code: str | None = None,
        **kwargs: Any,
    ) -> MapTransform:
        """Create MapTransform from config.

        The map function can be provided as Python code string that will be eval'd.
        For security, this should only be used with trusted configurations.
        """
        if map_fn_code:
            # Create map function from code string
            # WARNING: eval is unsafe with untrusted input
            map_fn = eval(map_fn_code)  # noqa: S307
        elif "map_fn" in kwargs:
            map_fn = kwargs.pop("map_fn")
        else:
            raise ValueError("MapTransform requires 'map_fn' or 'map_fn_code' parameter")

        return MapTransform(broker, input_channels, output_channel, map_fn)

    def _create_aggregate_transform(
        self,
        broker: Broker,
        input_channels: str | list[str],
        output_channel: str,
        aggregation_fn_code: str | None = None,
        **kwargs: Any,
    ) -> AggregateTransform:
        """Create AggregateTransform from config.

        The aggregation function can be provided as Python code string that will be eval'd.
        For security, this should only be used with trusted configurations.
        """
        if aggregation_fn_code:
            # Create aggregation function from code string
            # WARNING: eval is unsafe with untrusted input
            aggregation_fn = eval(aggregation_fn_code)  # noqa: S307
            kwargs["aggregation_fn"] = aggregation_fn

        return AggregateTransform(broker, input_channels, output_channel, **kwargs)
