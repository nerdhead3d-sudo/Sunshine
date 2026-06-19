"""Detects spoken requests to switch (or un-fix) the language Sunshine
listens/replies in, regardless of which language the request itself was
spoken in — e.g. both "parla in inglese" and "speak english" fix it to
English. Matched before anything else is interpreted."""

import re

# Each entry: (compiled pattern, target language code or None for "back to auto-detect")
_PATTERNS: list[tuple[re.Pattern, str | None]] = [
    (re.compile(r"parla (in )?italiano|speak italian|parle( en)? italien|habla italiano|sprich italienisch|fala italiano", re.IGNORECASE), "it"),
    (re.compile(r"parla (in )?inglese|speak english|parle( en)? anglais|habla ingl[eé]s|sprich englisch|fala ingl[eê]s", re.IGNORECASE), "en"),
    (re.compile(r"parla (in )?francese|speak french|parle( en)? fran[cç]ais|habla franc[eé]s|sprich franz[oö]sisch|fala franc[eê]s", re.IGNORECASE), "fr"),
    (re.compile(r"parla (in )?spagnolo|speak spanish|parle( en)? espagnol|habla espa[ñn]ol|sprich spanisch|fala espanhol", re.IGNORECASE), "es"),
    (re.compile(r"parla (in )?tedesco|speak german|parle( en)? allemand|habla alem[aá]n|sprich deutsch|fala alem[aã]o", re.IGNORECASE), "de"),
    (re.compile(r"parla (in )?portoghese|speak portuguese|parle( en)? portugais|habla portugu[eé]s|sprich portugiesisch|fala portugu[eê]s", re.IGNORECASE), "pt"),
    (
        re.compile(
            r"torna automatico|riconoscimento automatico|auto.?detect|d[eé]tection automatique"
            r"|detecci[oó]n autom[aá]tica|automatische erkennung|detec[cç][aã]o autom[aá]tica",
            re.IGNORECASE,
        ),
        None,
    ),
]

_CONFIRMATIONS = {
    "it": "Va bene, ora parlo in italiano!",
    "en": "Alright, I'll speak English now!",
    "fr": "D'accord, je parle français maintenant !",
    "es": "Vale, ahora hablo en español!",
    "de": "Okay, ich spreche jetzt Deutsch!",
    "pt": "Tudo bem, agora falo português!",
    None: "Ok, torno a riconoscere la lingua automaticamente.",
}


def detect(text: str) -> tuple[bool, str | None]:
    """Returns (matched, target_lang). target_lang is None both when there
    was no match (matched=False) and when the match was the "go back to
    auto-detect" command (matched=True, target_lang=None) — check
    `matched` first."""
    for pattern, lang in _PATTERNS:
        if pattern.search(text):
            return True, lang
    return False, None


def confirmation_for(target_lang: str | None) -> str:
    return _CONFIRMATIONS.get(target_lang, "Ok!")
