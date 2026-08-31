"""Unit tests for ParamRef and is_param_ref helper."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from cod3s_data.config.models import ParamRef, is_param_ref


class TestParamRefValidation:
    def test_minimal_ref(self):
        ref = ParamRef(ref="params.alarm.extruder")
        assert ref.ref == "params.alarm.extruder"
        assert ref.default is None
        assert ref.key is None
        assert ref.merge is False

    def test_merge_ref(self):
        ref = ParamRef(ref="params.consignes", merge=True, default={})
        assert ref.merge is True
        assert ref.default == {}

    def test_full_ref(self):
        ref = ParamRef(ref="params.alarm", default=200.0, key="extruder")
        assert ref.ref == "params.alarm"
        assert ref.default == 200.0
        assert ref.key == "extruder"

    def test_default_can_be_dict(self):
        ref = ParamRef(ref="params.x", default={"a": 1, "b": 2})
        assert ref.default == {"a": 1, "b": 2}

    def test_frozen(self):
        ref = ParamRef(ref="params.x")
        with pytest.raises(ValidationError):
            ref.ref = "params.y"  # type: ignore[misc]

    def test_missing_ref_field(self):
        with pytest.raises(ValidationError):
            ParamRef()  # type: ignore[call-arg]


class TestIsParamRef:
    def test_dict_with_ref(self):
        assert is_param_ref({"ref": "params.x"})
        assert is_param_ref({"ref": "params.x", "default": 1})

    def test_dict_without_ref(self):
        assert not is_param_ref({"value": 1})
        assert not is_param_ref({})

    def test_non_dict(self):
        assert not is_param_ref(1.0)
        assert not is_param_ref("params.x")
        assert not is_param_ref(None)
        assert not is_param_ref([1, 2, 3])

    def test_ref_must_be_string(self):
        assert not is_param_ref({"ref": 123})
