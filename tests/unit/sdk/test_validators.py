"""validate_file_path のユニットテスト"""

import pytest

from photoshop_sdk.exceptions import ValidationError
from photoshop_sdk.validators import validate_file_path


class TestValidateFilePath:
    """validate_file_path の正常系・異常系テスト"""

    def test_valid_absolute_path(self, tmp_path):
        """正常系: 存在するファイルの絶対パスを渡すと resolved Path が返る"""
        f = tmp_path / "test.psd"
        f.write_text("dummy")
        result = validate_file_path(str(f))
        assert result == f.resolve()
        assert result.is_absolute()

    def test_returns_resolved_path(self, tmp_path):
        """正規化された Path が返る（シンボリックリンク等も解決）"""
        f = tmp_path / "test.psd"
        f.write_text("dummy")
        result = validate_file_path(str(f))
        assert result == f.resolve()

    def test_relative_path_resolved(self, tmp_path, monkeypatch):
        """相対パスが絶対パスに解決される"""
        f = tmp_path / "relative.psd"
        f.write_text("dummy")
        monkeypatch.chdir(tmp_path)
        result = validate_file_path("relative.psd")
        assert result.is_absolute()
        assert result == f.resolve()

    def test_tilde_expansion(self, tmp_path, monkeypatch):
        """~ を含むパスが expanduser で展開される"""
        f = tmp_path / "file.psd"
        f.write_text("dummy")
        monkeypatch.setenv("HOME", str(tmp_path))
        result = validate_file_path("~/file.psd")
        assert result == f.resolve()

    def test_empty_string_raises(self):
        """空文字列 → ValidationError"""
        with pytest.raises(ValidationError, match="must not be empty"):
            validate_file_path("")

    def test_whitespace_only_raises(self):
        """空白のみ → ValidationError"""
        with pytest.raises(ValidationError, match="must not be empty"):
            validate_file_path("   ")

    def test_control_chars_raises(self):
        """制御文字を含む → ValidationError"""
        with pytest.raises(ValidationError, match="control characters"):
            validate_file_path("/path/to/\x00file.psd")

    def test_null_byte_raises(self):
        """NULL バイト → ValidationError"""
        with pytest.raises(ValidationError, match="control characters"):
            validate_file_path("/path/\x00/file.psd")

    def test_tab_in_path_raises(self):
        """タブ文字 → ValidationError"""
        with pytest.raises(ValidationError, match="control characters"):
            validate_file_path("/path/to/\tfile.psd")

    def test_path_traversal_raises(self):
        """.. を含むパス → ValidationError"""
        with pytest.raises(ValidationError, match="traversal"):
            validate_file_path("../etc/passwd")

    def test_nested_traversal_raises(self):
        """ネストされた .. → ValidationError"""
        with pytest.raises(ValidationError, match="traversal"):
            validate_file_path("foo/../../bar")

    def test_traversal_via_normpath_bypass(self, tmp_path):
        """normpath がトラバーサルを折り畳むバイパスを検出"""
        # subdir/../secret.psd は normpath で secret.psd に正規化されるが
        # 生パスに .. が含まれるため拒否されるべき
        target = tmp_path / "secret.psd"
        target.write_text("dummy")
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        with pytest.raises(ValidationError, match="traversal"):
            validate_file_path(str(subdir) + "/../secret.psd")

    def test_file_not_found_raises(self, tmp_path):
        """存在しないパス → ValidationError"""
        nonexistent = str(tmp_path / "nonexistent.psd")
        with pytest.raises(ValidationError, match="File not found"):
            validate_file_path(nonexistent)

    def test_directory_not_file_raises(self, tmp_path):
        """ディレクトリ → ValidationError"""
        with pytest.raises(ValidationError, match="not a file"):
            validate_file_path(str(tmp_path))

    def test_error_details_contain_field_and_rule(self):
        """ValidationError の details に field と rule が含まれる"""
        with pytest.raises(ValidationError) as exc_info:
            validate_file_path("")
        assert exc_info.value.details["field"] == "path"
        assert exc_info.value.details["rule"] == "non_empty"
