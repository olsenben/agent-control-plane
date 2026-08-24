from src.api import public_greeting
from src.config_parser import supported_names


def test_supported_names() -> None:
    assert supported_names() == ("offset", "scale")


def test_public_greeting() -> None:
    assert public_greeting("ada") == "Hello, Ada"
