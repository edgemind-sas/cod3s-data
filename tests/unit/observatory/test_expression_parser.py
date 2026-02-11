"""Tests for Observatory safe expression parser."""

import pytest

from cod3s_data.observatory.expression_parser import evaluate_expression, validate_expression


class TestValidateExpression:
    """Tests for expression validation."""

    def test_valid_comparison(self):
        validate_expression("value > 100")
        validate_expression("value >= 0")
        validate_expression("value == 42")
        validate_expression("value != 0")
        validate_expression("value < 1000")
        validate_expression("value <= 50")

    def test_valid_boolean_ops(self):
        validate_expression("value > 0 and value < 100")
        validate_expression("value == 1 or value == 2")

    def test_valid_string_comparison(self):
        validate_expression("key == 'temperature'")
        validate_expression("channel == 'sensor.1'")

    def test_valid_tags_access(self):
        validate_expression("tags.unit == 'celsius'")

    def test_valid_not(self):
        validate_expression("not value == 0")

    def test_valid_in_operator(self):
        validate_expression("key in 'temperature_high'")

    def test_reject_function_calls(self):
        with pytest.raises(ValueError, match="Disallowed"):
            validate_expression("len(key)")

    def test_reject_import(self):
        with pytest.raises(ValueError):
            validate_expression("__import__('os')")

    def test_reject_attribute_access_non_tags(self):
        with pytest.raises(ValueError, match="tags"):
            validate_expression("value.real > 0")

    def test_reject_list_comprehension(self):
        with pytest.raises(ValueError, match="Disallowed"):
            validate_expression("[x for x in range(10)]")

    def test_reject_lambda(self):
        with pytest.raises(ValueError, match="Disallowed"):
            validate_expression("(lambda: 1)()")

    def test_syntax_error(self):
        with pytest.raises(ValueError, match="syntax"):
            validate_expression("value >< 100")


class TestEvaluateExpression:
    """Tests for expression evaluation."""

    def test_simple_comparison(self):
        assert evaluate_expression("value > 100", {"value": 150}) is True
        assert evaluate_expression("value > 100", {"value": 50}) is False

    def test_equality(self):
        assert evaluate_expression("key == 'temp'", {"key": "temp"}) is True
        assert evaluate_expression("key == 'temp'", {"key": "humid"}) is False

    def test_and_operator(self):
        ctx = {"value": 75}
        assert evaluate_expression("value > 50 and value < 100", ctx) is True
        assert evaluate_expression("value > 50 and value < 70", ctx) is False

    def test_or_operator(self):
        ctx = {"value": 0}
        assert evaluate_expression("value == 0 or value == 1", ctx) is True
        ctx = {"value": 5}
        assert evaluate_expression("value == 0 or value == 1", ctx) is False

    def test_not_operator(self):
        assert evaluate_expression("not value == 0", {"value": 1}) is True
        assert evaluate_expression("not value == 0", {"value": 0}) is False

    def test_tags_access(self):
        ctx = {"tags.unit": "celsius"}
        assert evaluate_expression("tags.unit == 'celsius'", ctx) is True
        assert evaluate_expression("tags.unit == 'fahrenheit'", ctx) is False

    def test_in_operator(self):
        ctx = {"key": "temp"}
        assert evaluate_expression("key in 'temperature'", ctx) is True
        assert evaluate_expression("key in 'humidity'", ctx) is False

    def test_chained_comparison(self):
        ctx = {"value": 50}
        assert evaluate_expression("0 < value < 100", ctx) is True
        assert evaluate_expression("0 < value < 30", ctx) is False

    def test_unknown_variable(self):
        with pytest.raises(ValueError, match="Unknown variable"):
            evaluate_expression("unknown > 0", {})

    def test_arithmetic(self):
        ctx = {"value": 10}
        assert evaluate_expression("value + 5 > 14", ctx) is True
        assert evaluate_expression("value * 2 == 20", ctx) is True
