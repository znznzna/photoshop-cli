"""psd document サブコマンド群 — auto_commands で自動生成"""

import click

from cli.auto_commands import register_group_commands


@click.group(name="document")
def document_cmd():
    """Document operations (open, close, save, info, list, and more)"""
    pass


register_group_commands(document_cmd, "document")
