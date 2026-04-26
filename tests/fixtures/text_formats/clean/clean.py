"""Bayyinah clean Python reference fixture."""


def greet(name: str) -> str:
    """Return a plain ASCII greeting."""
    return f"Hello, {name}!"


if __name__ == "__main__":
    print(greet("world"))
