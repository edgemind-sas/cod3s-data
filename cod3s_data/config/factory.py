"""Component factory for COD3S Data Framework."""

from collections.abc import Callable
from typing import Any

from cod3s_data.broker.base import Broker
from cod3s_data.config.models import (
    DestinationConfig,
    ParamRef,
    SourceConfig,
    TransformConfig,
    is_param_ref,
)
from cod3s_data.destinations.base import Destination
from cod3s_data.destinations.collect import CollectDestination
from cod3s_data.destinations.core import ConsoleDestination, FileDestination, InMemoryDestination
from cod3s_data.destinations.influxdb import InfluxDBDestination
from cod3s_data.destinations.mqtt import MQTTDestination
from cod3s_data.sources.base import Source
from cod3s_data.sources.file_sources import (
    CSVDirectorySource,
    CSVSource,
    CSVWatchSource,
    DirectoryWatchSource,
    FileSource,
)
from cod3s_data.sources.mqtt_source import MQTTSource
from cod3s_data.sources.param_file import ParamFileSource
from cod3s_data.sources.test_sources import RandomSource, SequenceSource
from cod3s_data.transformations.base import Transformation
from cod3s_data.transformations.builtin import (
    AggregateTransform,
    AlarmGateTransform,
    AlarmTransform,
    BoundsAlarmTransform,
    DeviationFilterTransform,
    FilterTransform,
    MapTransform,
    MedianFilterTransform,
    MovingAverageTransform,
    RateAlarmTransform,
    RelativeAlarmTransform,
    ThrottleTransform,
    UnpackTransform,
)
from cod3s_data.transformations.param_store import ParameterStore


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
            "directory_watch": DirectoryWatchSource,
            "param_file": ParamFileSource,
            "csv_directory": CSVDirectorySource,
            "mqtt": MQTTSource,
        }
        self._transform_registry: dict[str, Callable[..., Transformation]] = {
            "filter": self._create_filter_transform,
            "map": self._create_map_transform,
            "aggregate": self._create_aggregate_transform,
            "alarm": self._create_alarm_transform,
            "throttle": self._create_throttle_transform,
            "unpack": UnpackTransform,
            "moving_average": self._create_moving_average_transform,
            "median_filter": self._create_median_filter_transform,
            "deviation_filter": self._create_deviation_filter_transform,
            "relative_alarm": self._create_relative_alarm_transform,
            "bounds_alarm": BoundsAlarmTransform,
            "rate_alarm": RateAlarmTransform,
            "alarm_gate": AlarmGateTransform,
        }
        self._destination_registry: dict[str, Callable[..., Destination]] = {
            "console": ConsoleDestination,
            "file": FileDestination,
            "inmemory": InMemoryDestination,
            "collect": CollectDestination,
            "influxdb": InfluxDBDestination,
            "mqtt": MQTTDestination,
        }

    def _resolve_param_refs(
        self, params: dict[str, Any]
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Split a params dict into (concrete_params, param_specs).

        Walks the dict; any value matching the ``ParamRef`` shape is replaced
        by its ``default`` and recorded as a spec. Specs are turned into
        ``ParameterStore`` instances by ``_attach_param_stores`` once the
        owning component exists.

        Nested dicts/lists are not traversed: a ParamRef must appear at the
        top level of ``params`` (matching how component constructors receive
        their kwargs).
        """
        cleaned: dict[str, Any] = {}
        specs: list[dict[str, Any]] = []
        for name, value in params.items():
            if is_param_ref(value):
                ref = ParamRef.model_validate(value)
                cleaned[name] = ref.default
                specs.append(
                    {
                        "name": name,
                        "ref": ref.ref,
                        "default": ref.default,
                        "key": ref.key,
                        "merge": ref.merge,
                    }
                )
            else:
                cleaned[name] = value
        return cleaned, specs

    def _attach_param_stores(self, owner: Any, specs: list[dict[str, Any]]) -> None:
        """Build ParameterStore instances for each spec and attach to owner."""
        if not specs:
            return
        stores: list[ParameterStore] = getattr(owner, "_param_stores", None) or []
        for spec in specs:
            stores.append(
                ParameterStore(
                    broker=self.broker,
                    owner=owner,
                    param_name=spec["name"],
                    ref=spec["ref"],
                    default=spec["default"],
                    dict_key=spec["key"],
                    merge=spec["merge"],
                )
            )
        owner._param_stores = stores

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
        cleaned, specs = self._resolve_param_refs(config.params)
        source = source_class(self.broker, config.channel, **cleaned)
        self._attach_param_stores(source, specs)
        return source

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
        cleaned, specs = self._resolve_param_refs(config.params)
        transform = transform_fn(
            self.broker, config.input_channels, config.output_channel, **cleaned
        )
        self._attach_param_stores(transform, specs)
        return transform

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
        cleaned, specs = self._resolve_param_refs(config.params)
        destination = dest_class(self.broker, config.channel_pattern, **cleaned)
        self._attach_param_stores(destination, specs)
        return destination

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

    def _create_throttle_transform(
        self,
        broker: Broker,
        input_channels: str | list[str],
        output_channel: str,
        **kwargs: Any,
    ) -> ThrottleTransform:
        """Create ThrottleTransform from config."""
        return ThrottleTransform(broker, input_channels, output_channel, **kwargs)

    def _create_alarm_transform(
        self,
        broker: Broker,
        input_channels: str | list[str],
        output_channel: str,
        **kwargs: Any,
    ) -> AlarmTransform:
        """Create AlarmTransform from config."""
        return AlarmTransform(broker, input_channels, output_channel, **kwargs)

    def _create_moving_average_transform(
        self,
        broker: Broker,
        input_channels: str | list[str],
        output_channel: str,
        **kwargs: Any,
    ) -> MovingAverageTransform:
        """Create MovingAverageTransform from config."""
        return MovingAverageTransform(broker, input_channels, output_channel, **kwargs)

    def _create_median_filter_transform(
        self,
        broker: Broker,
        input_channels: str | list[str],
        output_channel: str,
        **kwargs: Any,
    ) -> MedianFilterTransform:
        """Create MedianFilterTransform from config."""
        return MedianFilterTransform(broker, input_channels, output_channel, **kwargs)

    def _create_deviation_filter_transform(
        self,
        broker: Broker,
        input_channels: str | list[str],
        output_channel: str,
        **kwargs: Any,
    ) -> DeviationFilterTransform:
        """Create DeviationFilterTransform from config."""
        return DeviationFilterTransform(broker, input_channels, output_channel, **kwargs)

    def _create_relative_alarm_transform(
        self,
        broker: Broker,
        input_channels: str | list[str],
        output_channel: str,
        **kwargs: Any,
    ) -> RelativeAlarmTransform:
        """Create RelativeAlarmTransform from config."""
        return RelativeAlarmTransform(broker, input_channels, output_channel, **kwargs)
