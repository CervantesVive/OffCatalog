import offcatalog


def test_package_has_version():
    assert isinstance(offcatalog.__version__, str)
    assert offcatalog.__version__


def test_cli_app_importable():
    from offcatalog.cli import app
    import typer

    assert isinstance(app, typer.Typer)
