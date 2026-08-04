from __future__ import annotations

import string

KNOWN_HALLUCINATIONS = {
    "click",
    "click click",
    "cough",
    "cough cough",
    "thank you",
    "thanks for watching",
    "please subscribe",
    "subscribe",
    "amara.org",
    "subtitle",
    "subtitles",
}

def is_valid_transcript(text: str) -> bool:
    """
    Validates a transcript chunk to filter out common Whisper hallucinations and garbage.
    Returns True if valid, False if it should be rejected.
    """
    if not text:
        return False
        
    text_stripped = text.strip()
    if not text_stripped:
        return False
        
    # Reject if entirely non-printable/no letters/numbers
    # A valid transcript should have at least one alphanumeric character
    has_alnum = any(c.isalnum() for c in text_stripped)
    if not has_alnum:
        return False
        
    # Reject known hallucination phrases (exact match, case insensitive, stripped of punctuation)
    clean_lower = text_stripped.lower().strip(string.punctuation)
    if clean_lower in KNOWN_HALLUCINATIONS:
        return False
        
    # Check for repeating garbage words like "click click click"
    words = clean_lower.split()
    if len(words) > 0 and len(set(words)) == 1 and words[0] in {"click", "cough"}:
        return False
        
    # Reject if any single word is > 40 chars
    for word in text_stripped.split():
        if len(word) > 40:
            return False
            
    return True
