"""CommandSchema 定義の網羅性・整合性テスト"""

import pytest

from photoshop_sdk.schema import COMMAND_SCHEMAS, CommandSchema, ParamSchema


class TestParamSchema:
    def test_effective_sdk_name_with_override(self):
        """sdk_name が指定されている場合はそちらを返す"""
        p = ParamSchema(name="doc_id", type=int, description="Doc ID", sdk_name="documentId")
        assert p.effective_sdk_name == "documentId"

    def test_effective_sdk_name_without_override(self):
        """sdk_name が None の場合は name を返す"""
        p = ParamSchema(name="path", type=str, description="Path")
        assert p.effective_sdk_name == "path"

    def test_frozen(self):
        """ParamSchema は frozen（不変）"""
        p = ParamSchema(name="x", type=int, description="X")
        with pytest.raises(AttributeError):
            p.name = "y"


class TestCommandSchema:
    def test_frozen(self):
        """CommandSchema は frozen（不変）"""
        s = CommandSchema(command="test.cmd", description="Test")
        with pytest.raises(AttributeError):
            s.command = "other"

    def test_defaults(self):
        """デフォルト値が正しい"""
        s = CommandSchema(command="test.cmd", description="Test")
        assert s.params == []
        assert s.mutating is False
        assert s.risk_level == "read"
        assert s.requires_confirm is False
        assert s.supports_dry_run is False
        assert s.timeout == 30.0
        assert s.validator is None


class TestCommandSchemas:
    def test_all_commands_have_schemas(self):
        """全11コマンド（document.* 5 + file.* 5 + system.ping）の CommandSchema が定義されている"""
        commands = {s.command for s in COMMAND_SCHEMAS}
        expected = {
            "document.list",
            "document.info",
            "document.open",
            "document.close",
            "document.save",
            "file.list",
            "file.info",
            "file.open",
            "file.close",
            "file.save",
            "system.ping",
        }
        assert commands == expected

    def test_no_duplicate_commands(self):
        """重複するコマンドがない"""
        commands = [s.command for s in COMMAND_SCHEMAS]
        assert len(commands) == len(set(commands))

    def test_risk_levels_valid(self):
        """risk_level が許可された値のみ"""
        for s in COMMAND_SCHEMAS:
            assert s.risk_level in ("read", "write", "destructive"), f"{s.command}: invalid risk_level={s.risk_level}"

    def test_mutating_commands_have_dry_run(self):
        """mutating コマンドは supports_dry_run が有効"""
        for s in COMMAND_SCHEMAS:
            if s.mutating:
                assert s.supports_dry_run, f"{s.command} is mutating but doesn't support dry_run"

    def test_file_open_has_validator(self):
        """file.open に validate_file_path バリデータが設定されている"""
        schema = next(s for s in COMMAND_SCHEMAS if s.command == "file.open")
        assert schema.validator == "validate_file_path"

    def test_file_open_timeout(self):
        """file.open のタイムアウトは120秒"""
        schema = next(s for s in COMMAND_SCHEMAS if s.command == "file.open")
        assert schema.timeout == 120.0

    def test_system_ping_timeout(self):
        """system.ping のタイムアウトは5秒"""
        schema = next(s for s in COMMAND_SCHEMAS if s.command == "system.ping")
        assert schema.timeout == 5.0

    def test_file_close_requires_confirm(self):
        """file.close は requires_confirm が有効"""
        schema = next(s for s in COMMAND_SCHEMAS if s.command == "file.close")
        assert schema.requires_confirm is True

    def test_doc_id_params_have_sdk_name(self):
        """doc_id パラメータは sdk_name=documentId が設定されている"""
        for s in COMMAND_SCHEMAS:
            for p in s.params:
                if p.name == "doc_id":
                    assert p.sdk_name == "documentId", f"{s.command}: doc_id missing sdk_name"

    def test_read_commands_not_mutating(self):
        """read risk_level のコマンドは mutating=False"""
        for s in COMMAND_SCHEMAS:
            if s.risk_level == "read":
                assert not s.mutating, f"{s.command}: read command should not be mutating"
