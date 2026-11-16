from typer.testing import CliRunner

from insightbot.cli import app

runner = CliRunner()


def test_admin_cli_help():
    result = runner.invoke(app, ["admin", "--help"])
    assert result.exit_code == 0
    assert "create" in result.stdout


def test_admin_create_help():
    result = runner.invoke(app, ["admin", "create", "--help"])
    assert result.exit_code == 0
    assert "--username" in result.stdout
    assert "--email" in result.stdout
