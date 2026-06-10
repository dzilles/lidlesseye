import re


SAFE_CYPHER_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def validate_cypher_identifier(value: str, identifier_type: str) -> str:
    if not SAFE_CYPHER_IDENTIFIER.fullmatch(value):
        raise ValueError(f"Unsafe {identifier_type} for Cypher insertion: {value!r}")
    return value

