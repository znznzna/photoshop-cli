"""psd schema のユニットテスト"""

from cli.main import cli
from cli.schema_gen import generate_command_schema, list_available_commands


class TestSchemaGen:
    """schema_gen.py のユニットテスト"""

    def test_generate_file_open_schema(self):
        """file.open の schema が生成される"""
        schema = generate_command_schema("file.open", cli)
        assert schema is not None
        assert schema["title"] == "file.open"
        assert "params" in schema["properties"]
        params = schema["properties"]["params"]
        assert "path" in params["properties"]
        assert params["properties"]["path"]["_cli_type"] == "argument"

    def test_generate_file_list_schema(self):
        """file.list の schema が生成される（response 含む）"""
        schema = generate_command_schema("file.list", cli)
        assert schema is not None
        assert "response" in schema
        assert schema["response"]["type"] == "array"

    def test_generate_unknown_command(self):
        """存在しないコマンド → None"""
        schema = generate_command_schema("foo.bar", cli)
        assert schema is None

    def test_list_available_commands(self):
        """利用可能なコマンド一覧を取得"""
        commands = list_available_commands(cli)
        assert "file.list" in commands
        assert "file.open" in commands
        assert "file.close" in commands
        assert "file.save" in commands
        assert "file.info" in commands

    def test_schema_includes_response_for_all_file_commands(self):
        """全ファイルコマンドに response schema が定義されている"""
        commands = [c for c in list_available_commands(cli) if c.startswith("file.")]
        for cmd in commands:
            schema = generate_command_schema(cmd, cli)
            assert schema is not None, f"Schema not found for {cmd}"
            assert "response" in schema, f"Response schema missing for {cmd}"

    def test_file_info_has_doc_id_param(self):
        """file.info に doc_id パラメータが含まれる"""
        schema = generate_command_schema("file.info", cli)
        params = schema["properties"]["params"]
        assert "doc_id" in params["properties"]
        assert params["properties"]["doc_id"]["type"] == "integer"
        assert "doc_id" in params["required"]
