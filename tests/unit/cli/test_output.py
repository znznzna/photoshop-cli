import json

from cli.output import OutputFormatter


def test_format_json_mode():
    data = {"key": "value", "num": 42}
    result = OutputFormatter.format(data, mode="json")
    parsed = json.loads(result)
    assert parsed == data


def test_format_text_mode_dict():
    data = {"name": "test.psd", "width": 1920}
    result = OutputFormatter.format(data, mode="text")
    assert "name: test.psd" in result
    assert "width: 1920" in result


def test_format_text_mode_list():
    data = [{"name": "a.psd"}, {"name": "b.psd"}]
    result = OutputFormatter.format(data, mode="text")
    assert "a.psd" in result
    assert "b.psd" in result


def test_format_table_mode_list():
    data = [{"name": "a.psd", "id": 1}, {"name": "b.psd", "id": 2}]
    result = OutputFormatter.format(data, mode="table")
    assert "name" in result
    assert "a.psd" in result


def test_format_error_text():
    result = OutputFormatter.format_error("Something went wrong", mode="text")
    assert "Something went wrong" in result


def test_format_error_json():
    result = OutputFormatter.format_error(
        "Connection failed", mode="json", code="CONNECTION_ERROR"
    )
    parsed = json.loads(result)
    assert parsed["error"]["code"] == "CONNECTION_ERROR"
    assert parsed["error"]["message"] == "Connection failed"


def test_format_json_sanitizes_control_chars():
    data = {"msg": "hello\x00world\x01"}
    result = OutputFormatter.format(data, mode="json")
    parsed = json.loads(result)
    assert "\x00" not in parsed["msg"]
    assert "\x01" not in parsed["msg"]


def test_format_json_truncates_long_strings():
    data = {"big": "x" * 60000}
    result = OutputFormatter.format(data, mode="json")
    parsed = json.loads(result)
    assert len(parsed["big"]) < 60000
    assert "truncated" in parsed["big"]
