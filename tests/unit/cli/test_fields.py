"""--fields フィルタリングのユニットテスト"""

import json

from cli.output import OutputFormatter


class TestFilterFields:
    """OutputFormatter._filter_fields のユニットテスト"""

    def test_filter_dict_fields(self):
        """dict から指定フィールドのみ抽出"""
        data = {"id": 1, "name": "photo.psd", "width": 1920, "height": 1080}
        result = OutputFormatter._filter_fields(data, ["id", "name"])
        assert result == {"id": 1, "name": "photo.psd"}

    def test_filter_list_of_dicts(self):
        """list[dict] の各要素をフィルタ"""
        data = [
            {"id": 1, "name": "a.psd", "width": 100},
            {"id": 2, "name": "b.psd", "width": 200},
        ]
        result = OutputFormatter._filter_fields(data, ["id", "name"])
        assert result == [
            {"id": 1, "name": "a.psd"},
            {"id": 2, "name": "b.psd"},
        ]

    def test_filter_nonexistent_field(self):
        """存在しないフィールド → サイレント無視"""
        data = {"id": 1, "name": "photo.psd"}
        result = OutputFormatter._filter_fields(data, ["id", "nonexistent"])
        assert result == {"id": 1}

    def test_filter_all_excluded(self):
        """全フィールドが除外 → {} をサイレントに返す"""
        data = {"id": 1, "name": "photo.psd"}
        result = OutputFormatter._filter_fields(data, ["nonexistent"])
        assert result == {}

    def test_filter_non_dict_passthrough(self):
        """dict/list でないデータ → そのまま返す"""
        assert OutputFormatter._filter_fields("hello", ["id"]) == "hello"
        assert OutputFormatter._filter_fields(42, ["id"]) == 42

    def test_format_with_fields_json(self):
        """format() に fields を渡すとフィルタリングされる"""
        data = {"id": 1, "name": "photo.psd", "width": 1920}
        result = OutputFormatter.format(data, "json", fields=["id", "name"])
        parsed = json.loads(result)
        assert parsed == {"id": 1, "name": "photo.psd"}

    def test_format_with_fields_none(self):
        """fields=None → フィルタなし"""
        data = {"id": 1, "name": "photo.psd"}
        result = OutputFormatter.format(data, "json", fields=None)
        parsed = json.loads(result)
        assert parsed == {"id": 1, "name": "photo.psd"}
