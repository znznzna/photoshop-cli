"""psd file サブコマンド群 — document のエイリアス（auto_commands で自動生成）"""

import click

from cli.auto_commands import register_group_commands


@click.group(name="file")
def file_cmd():
    """File operations (alias for 'document' commands)"""
    pass


register_group_commands(file_cmd, "file")
