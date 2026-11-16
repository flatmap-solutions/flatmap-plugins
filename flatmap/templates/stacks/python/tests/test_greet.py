from {{PY_PACKAGE}} import greet


def test_greets_by_name() -> None:
    assert greet("world") == "Hello, world!"
