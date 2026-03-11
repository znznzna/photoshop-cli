import pytest
from pydantic import ValidationError as PydanticValidationError

from photoshop_sdk.schema import (
    DocumentInfo,
    PhotoshopCommand,
    PhotoshopResponse,
)


def test_command_requires_id_and_command():
    cmd = PhotoshopCommand(id="abc-123", command="file.open", params={"path": "/foo.psd"})
    assert cmd.id == "abc-123"
    assert cmd.command == "file.open"
    assert cmd.params == {"path": "/foo.psd"}


def test_command_params_defaults_to_empty():
    cmd = PhotoshopCommand(id="abc-123", command="file.list")
    assert cmd.params == {}


def test_command_missing_id_raises():
    with pytest.raises(PydanticValidationError):
        PhotoshopCommand(command="file.list")


def test_response_success_true():
    resp = PhotoshopResponse(id="abc-123", success=True, result={"documentId": 1})
    assert resp.success is True
    assert resp.result == {"documentId": 1}
    assert resp.error is None


def test_response_success_false():
    resp = PhotoshopResponse(
        id="abc-123",
        success=False,
        error={"code": "DOCUMENT_NOT_FOUND", "message": "Not found"},
    )
    assert resp.success is False
    assert resp.error == {"code": "DOCUMENT_NOT_FOUND", "message": "Not found"}
    assert resp.result is None


def test_document_info_fields():
    doc = DocumentInfo(
        documentId=1,
        name="test.psd",
        path="/Users/test/test.psd",
        width=1920,
        height=1080,
    )
    assert doc.documentId == 1
    assert doc.name == "test.psd"
    assert doc.width == 1920
    assert doc.height == 1080


def test_document_info_optional_path():
    doc = DocumentInfo(documentId=2, name="untitled.psd", width=800, height=600)
    assert doc.path is None


# --- Phase 1.6: CommandSchema 整合性テスト ---

from photoshop_sdk.schema import COMMAND_SCHEMAS, CommandSchema, ParamSchema


class TestCommandSchemaIntegrity:
    """全 CommandSchema の整合性テスト"""

    def test_all_commands_have_group_action_format(self):
        """全コマンドが 'group.action' 形式であること"""
        for schema in COMMAND_SCHEMAS:
            parts = schema.command.split(".")
            assert len(parts) == 2, f"Invalid command format: {schema.command}"
            assert len(parts[0]) > 0
            assert len(parts[1]) > 0

    def test_mutating_commands_have_risk_level(self):
        """mutating=True のコマンドには risk_level が read 以外であること"""
        for schema in COMMAND_SCHEMAS:
            if schema.mutating:
                assert schema.risk_level != "read", (
                    f"Mutating command {schema.command} has risk_level='read'"
                )

    def test_no_duplicate_commands(self):
        """コマンド名に重複がないこと"""
        commands = [s.command for s in COMMAND_SCHEMAS]
        assert len(commands) == len(set(commands)), (
            f"Duplicate commands found: {[c for c in commands if commands.count(c) > 1]}"
        )

    def test_document_file_parity(self):
        """document.* と file.* が1:1対応していること"""
        doc_actions = sorted(
            s.command.split(".")[1] for s in COMMAND_SCHEMAS if s.command.startswith("document.")
        )
        file_actions = sorted(
            s.command.split(".")[1] for s in COMMAND_SCHEMAS if s.command.startswith("file.")
        )
        assert doc_actions == file_actions

    def test_param_sdk_name_or_default(self):
        """全パラメータに effective_sdk_name が取得できること"""
        for schema in COMMAND_SCHEMAS:
            for p in schema.params:
                assert isinstance(p.effective_sdk_name, str)
                assert len(p.effective_sdk_name) > 0
