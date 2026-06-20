"""Simple regex-based Italian intent matching for Sunshine's "Alexa-style"
PC skills. A matched utterance is handled locally and immediately, with no
Ollama round-trip; anything that doesn't match returns None so the caller
can fall back to the normal chat flow."""

import re
from collections.abc import Callable

from . import commands

ScheduleFn = Callable[[float, str], None]

_POLITE_PREFIX_RE = re.compile(
    r"^(puoi|potresti|riesci a|mi sai|sai)\s+|\bper favore\b|\bper piacere\b"
)


def _normalize(text: str) -> str:
    """Lowercases and strips trailing punctuation/polite phrasing so
    "Puoi alzare un po' il volume per favore?" matches the same pattern as
    "alza il volume"."""
    t = text.strip().lower().rstrip("?!. ")
    t = _POLITE_PREFIX_RE.sub("", t).strip()
    return t


def try_handle(text: str, schedule_announcement: ScheduleFn, allow_open_apps: bool = True) -> str | None:
    """Returns a spoken reply if `text` matched a known command, else None.
    `schedule_announcement(seconds, text)` is used for delayed replies
    (timers/reminders). `allow_open_apps=False` disables the "apri X"
    command (the one with real-world side effects — launching programs or
    websites) so it doesn't fire for an unrecognized speaker; everything
    else (info, volume, reminders) stays available regardless."""
    t = _normalize(text)

    if re.search(r"\bche ore (sono|è)\b|\bche ora è\b|\bdimmi l'ora\b", t):
        return f"Sono le {commands.current_time()}."

    if re.search(r"\bche giorno è\b|\bche data è\b|\bdimmi la data\b", t):
        return f"Oggi è {commands.current_date()}."

    if re.search(r"\bbatteria\b|\blivello (della )?batteria\b", t):
        pct = commands.battery_percent()
        if pct is None:
            return "Il pc è collegato alla corrente, non ha batteria."
        return f"La batteria è al {pct} per cento."

    if re.search(r"\bspazio (su disco|libero)\b|\bquanto spazio\b|\bmemoria (libera|disponibile)\b", t):
        return f"Ci sono circa {commands.free_disk_gb():.0f} gigabyte liberi sul disco."

    if re.search(r"\b(alza|alzare|aumenta|aumentare|sali (con|col))\b.*\bvolume\b|\bpiù forte\b", t):
        commands.volume_up()
        return "Volume alzato."

    if re.search(r"\b(abbassa|abbassare|diminuisci|diminuire|scendi (con|col))\b.*\bvolume\b|\bpiù piano\b|\bpiù basso\b", t):
        commands.volume_down()
        return "Volume abbassato."

    if re.search(r"\bmuta\b|\bsilenzia\b|\btogli (il )?audio\b|\bspegni (il )?audio\b|\baudio (off|spento)\b", t):
        commands.volume_mute()
        return "Audio mutato."

    if re.search(r"\bmetti in pausa\b|\bpausa( la)? musica\b|\bferma( la)? musica\b|\bstoppa( la)? musica\b|\bstop( alla)? musica\b", t):
        commands.media_play_pause()
        return "Fatto."

    if re.search(r"\briprendi( la)? musica\b|\bsuona\b|\bplay\b|\bfai partire la musica\b", t):
        commands.media_play_pause()
        return "Riprendo la musica."

    if re.search(r"\bprossima canzone\b|\bsalta canzone\b|\bcanzone successiva\b|\bcambia canzone\b|\bavanti (con la )?canzone\b", t):
        commands.media_next()
        return "Prossima canzone."

    if re.search(r"\bcanzone precedente\b|\btorna indietro( la canzone)?\b|\bcanzone di prima\b", t):
        commands.media_previous()
        return "Canzone precedente."

    match = re.search(r"\bricordami (?:di|che) (.+)|\b(?:fammi|mettimi) un promemoria per (.+)", t)
    if match:
        task = next(g for g in match.groups() if g).strip()
        schedule_announcement(5 * 60, f"Promemoria: {task}.")
        return f"Va bene, te lo ricordo tra cinque minuti: {task}."

    match = re.search(r"\bmetti(?: un)? timer (?:di|per) (\d+) ?(minut[oi]|second[oi])\b", t)
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        seconds = amount * 60 if unit.startswith("minut") else amount
        schedule_announcement(seconds, "Timer scaduto!")
        return f"Timer impostato per {amount} {unit}."

    if allow_open_apps:
        match = re.search(r"\b(?:apri|aprire|apri(?:mi)?)\s+(?:il |la |lo |l['’])?([\w' àèéìòù]+)$", t)
        if match:
            target = match.group(1).strip()
            if commands.open_app_or_site(target):
                return f"Apro {target}."

    return None
