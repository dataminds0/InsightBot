from typer.testing import CliRunner

from insightbot.cli import app

runner = CliRunner()


def test_cli_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "InsightBot" in result.stdout
    assert "config" in result.stdout
    assert "db" in result.stdout
    assert "admin" in result.stdout
    assert "sources" in result.stdout


def test_cli_config_help():
    result = runner.invoke(app, ["config", "--help"])
    assert result.exit_code == 0
    assert "init" in result.stdout
    assert "check" in result.stdout


def test_cli_config_check():
    result = runner.invoke(app, ["config", "check"])
    assert "InsightBot Environment:" in result.stdout
    assert "MongoDB URI:" in result.stdout
