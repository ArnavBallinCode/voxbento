from __future__ import annotations

import pytest

from portal.transcript_processing import is_valid_transcript


def test_valid_transcripts():
    assert is_valid_transcript("Hello world.")
    assert is_valid_transcript("This is a normal sentence with 123 numbers.")
    assert is_valid_transcript("¡Hola! ¿Cómo estás?")
    assert is_valid_transcript("A")

def test_empty_or_whitespace():
    assert not is_valid_transcript("")
    assert not is_valid_transcript("   ")
    assert not is_valid_transcript("\n\t")

def test_non_printable_or_no_alnum():
    assert not is_valid_transcript("...")
    assert not is_valid_transcript("!@#$%")
    assert not is_valid_transcript("    -   ")
    assert not is_valid_transcript("🤔")

def test_known_hallucinations():
    assert not is_valid_transcript("Click click")
    assert not is_valid_transcript("Cough cough.")
    assert not is_valid_transcript("Thank you!")
    assert not is_valid_transcript("  Thanks for watching...  ")
    assert not is_valid_transcript("subscribe")

def test_repeating_hallucinations():
    assert not is_valid_transcript("click click click")
    assert not is_valid_transcript("cough cough cough cough")

def test_long_words():
    # 41 characters word
    long_word = "a" * 41
    assert not is_valid_transcript(f"This has a {long_word} word")
    assert is_valid_transcript(f"This has a {'a'*40} word")
