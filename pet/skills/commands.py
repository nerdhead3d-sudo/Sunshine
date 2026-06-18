"""Side-effect implementations for Sunshine's simple PC-control skills:
media/volume keys, opening apps/sites, and read-only system info. Uses
only ctypes/stdlib so no extra dependencies are needed."""

import ctypes
import datetime
import shutil
import subprocess
import webbrowser

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32

_VK_VOLUME_MUTE = 0xAD
_VK_VOLUME_DOWN = 0xAE
_VK_VOLUME_UP = 0xAF
_VK_MEDIA_NEXT_TRACK = 0xB0
_VK_MEDIA_PREV_TRACK = 0xB1
_VK_MEDIA_PLAY_PAUSE = 0xB3

_KEYEVENTF_KEYUP = 0x0002


def _press_key(vk_code: int):
    _user32.keybd_event(vk_code, 0, 0, 0)
    _user32.keybd_event(vk_code, 0, _KEYEVENTF_KEYUP, 0)


def volume_up(steps: int = 2):
    for _ in range(steps):
        _press_key(_VK_VOLUME_UP)


def volume_down(steps: int = 2):
    for _ in range(steps):
        _press_key(_VK_VOLUME_DOWN)


def volume_mute():
    _press_key(_VK_VOLUME_MUTE)


def media_play_pause():
    _press_key(_VK_MEDIA_PLAY_PAUSE)


def media_next():
    _press_key(_VK_MEDIA_NEXT_TRACK)


def media_previous():
    _press_key(_VK_MEDIA_PREV_TRACK)


_APPS = {
    "blocco note": "notepad.exe",
    "calcolatrice": "calc.exe",
    "esplora file": "explorer.exe",
    "esplora risorse": "explorer.exe",
    "paint": "mspaint.exe",
}

_SITES = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "gmail": "https://mail.google.com",
}


def open_app_or_site(name: str) -> bool:
    """Best-effort: launches a known app or opens a known site by name.
    Returns False if `name` isn't recognized (caller should fall back to
    normal chat instead of claiming something was opened)."""
    name = name.strip().lower()
    if name in _APPS:
        subprocess.Popen(_APPS[name])
        return True
    if name in _SITES:
        webbrowser.open(_SITES[name])
        return True
    if name in ("il browser", "browser"):
        webbrowser.open("https://www.google.com")
        return True
    return False


def current_time() -> str:
    return datetime.datetime.now().strftime("%H:%M")


_GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
_MESI = [
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
]


def current_date() -> str:
    now = datetime.datetime.now()
    return f"{_GIORNI[now.weekday()]} {now.day} {_MESI[now.month - 1]}"


class _SystemPowerStatus(ctypes.Structure):
    _fields_ = [
        ("ACLineStatus", ctypes.c_byte),
        ("BatteryFlag", ctypes.c_byte),
        ("BatteryLifePercent", ctypes.c_byte),
        ("Reserved1", ctypes.c_byte),
        ("BatteryLifeTime", ctypes.c_ulong),
        ("BatteryFullLifeTime", ctypes.c_ulong),
    ]


def battery_percent() -> int | None:
    """Returns the battery charge percentage, or None if the machine has
    no battery (desktop PC)."""
    status = _SystemPowerStatus()
    ok = _kernel32.GetSystemPowerStatus(ctypes.byref(status))
    no_battery_flag = -128  # 0x80 as a signed byte: "no system battery"
    unknown_percent = -1    # 0xFF as a signed byte: "unknown"
    if not ok or status.BatteryFlag == no_battery_flag or status.BatteryLifePercent == unknown_percent:
        return None
    return status.BatteryLifePercent


def free_disk_gb(drive: str = "C:\\") -> float:
    _, _, free = shutil.disk_usage(drive)
    return free / (1024**3)
