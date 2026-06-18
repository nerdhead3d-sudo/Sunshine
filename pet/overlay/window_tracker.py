"""Lightweight Win32 window enumeration used to let the pet "climb" onto
the top edge of visible application windows, like a classic desktop
mascot. Pure ctypes, no extra dependency."""

import ctypes
from ctypes import wintypes

_user32 = ctypes.windll.user32
_EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)


def list_window_rects(exclude_hwnd: int | None = None) -> list[tuple[int, int, int, int]]:
    """Returns (left, top, right, bottom) for visible, titled, reasonably
    sized top-level windows, skipping the given hwnd (the pet's own)."""
    rects: list[tuple[int, int, int, int]] = []

    def callback(hwnd, _lparam):
        if exclude_hwnd is not None and hwnd == exclude_hwnd:
            return True
        if not _user32.IsWindowVisible(hwnd):
            return True
        if _user32.GetWindowTextLengthW(hwnd) == 0:
            return True

        rect = wintypes.RECT()
        if not _user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return True

        width = rect.right - rect.left
        height = rect.bottom - rect.top
        if width < 120 or height < 60 or rect.left <= -30000 or rect.top <= -30000:
            return True

        rects.append((rect.left, rect.top, rect.right, rect.bottom))
        return True

    _user32.EnumWindows(_EnumWindowsProc(callback), 0)
    return rects


def top_edge_platforms(screen_rect, exclude_hwnd=None, min_width=0, pet_height=0):
    """Returns (x0, x1, y) walkable platforms for each window's top edge
    that overlaps `screen_rect` horizontally with at least `min_width`
    pixels of overlap, and that leaves at least `pet_height` pixels of
    headroom above it within the screen — otherwise the pet would end up
    standing partly or fully above the visible monitor area."""
    sx0, sy0 = screen_rect.x(), screen_rect.y()
    sx1, sy1 = sx0 + screen_rect.width(), sy0 + screen_rect.height()

    platforms = []
    for left, top, right, bottom in list_window_rects(exclude_hwnd):
        if top < sy0 + pet_height or top > sy1:
            continue
        x0, x1 = max(left, sx0), min(right, sx1)
        if x1 - x0 >= min_width:
            platforms.append((x0, x1, top))
    return platforms
