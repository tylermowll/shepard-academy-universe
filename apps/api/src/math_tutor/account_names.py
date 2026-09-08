"""Canonical account names shared by validation and persistence."""

import unicodedata


def display_name(value: str) -> str:
    if any(unicodedata.category(char).startswith("C") for char in value):
        raise ValueError("Username cannot contain control characters.")
    name = " ".join(unicodedata.normalize("NFKC", value).split())
    if not 1 <= len(name) <= 64:
        raise ValueError("Username must be 1–64 characters.")
    return name


def account_key(value: str) -> str:
    return display_name(value).casefold()
