from __future__ import annotations

import ctypes
import os
from dataclasses import dataclass
from pathlib import Path
from ctypes import wintypes


@dataclass(frozen=True)
class GameWindow:
    handle: int
    bounds: tuple[int, int, int, int]


def place_overlay(
    game_bounds: tuple[int, int, int, int],
    panel_size: tuple[int, int],
    margin: int = 16,
) -> tuple[int, int, int, int] | None:
    """Place a panel at the game's upper-right corner, clamped to its bounds."""
    x, y, width, height = game_bounds
    panel_width, panel_height = panel_size
    if width <= margin * 2 or height <= margin * 2 or panel_width <= 0 or panel_height <= 0:
        return None
    panel_width = min(panel_width, width - margin * 2)
    panel_height = min(panel_height, height - margin * 2)
    return x + width - panel_width - margin, y + margin, panel_width, panel_height


def foreground_window_handle() -> int:
    if os.name != "nt":
        return 0
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetForegroundWindow.restype = wintypes.HWND
    return int(user32.GetForegroundWindow() or 0)


def get_csgo_window(handle: int) -> GameWindow | None:
    """Return a visible CS:GO Legacy top-level window and its screen bounds."""
    if os.name != "nt" or not handle:
        return None
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        class RECT(ctypes.Structure):
            _fields_ = [(name, wintypes.LONG) for name in ("left", "top", "right", "bottom")]

        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
        user32.GetWindowRect.restype = wintypes.BOOL
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)
        ]
        kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        hwnd = wintypes.HWND(handle)
        if not user32.IsWindowVisible(hwnd):
            return None
        process_id = wintypes.DWORD()
        if not user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id)):
            return None
        process = kernel32.OpenProcess(0x1000, False, process_id.value)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not process:
            return None
        try:
            image_path = ctypes.create_unicode_buffer(32768)
            path_length = wintypes.DWORD(len(image_path))
            if not kernel32.QueryFullProcessImageNameW(process, 0, image_path, ctypes.byref(path_length)):
                return None
        finally:
            kernel32.CloseHandle(process)
        if Path(image_path.value).name.casefold() != "csgo.exe":
            return None
        rect = RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return None
        bounds = (rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)
        if bounds[2] <= 0 or bounds[3] <= 0:
            return None
        return GameWindow(handle, bounds)
    except (AttributeError, OSError, ValueError):
        return None


def find_csgo_window() -> GameWindow | None:
    """Find a visible CS:GO Legacy top-level window."""
    handle = foreground_window_handle()
    foreground = get_csgo_window(handle) if handle else None
    if foreground is not None or os.name != "nt":
        return foreground
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        match: list[GameWindow] = []

        @callback_type
        def visit(hwnd, _lparam):
            info = get_csgo_window(int(hwnd))
            if info is not None:
                match.append(info)
                return False
            return True

        user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
        user32.EnumWindows.restype = wintypes.BOOL
        user32.EnumWindows(visit, 0)
        return match[0] if match else None
    except (AttributeError, OSError, ValueError):
        return None


def activate_window(handle: int) -> bool:
    if os.name != "nt" or not handle:
        return False
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    return bool(user32.SetForegroundWindow(wintypes.HWND(handle)))


def position_overlay_window(handle: int, bounds: tuple[int, int, int, int]) -> bool:
    if os.name != "nt" or not handle:
        return False
    x, y, width, height = bounds
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.SetWindowPos.argtypes = [
        wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT
    ]
    user32.SetWindowPos.restype = wintypes.BOOL
    hwnd_topmost = wintypes.HWND(-1)
    flags = 0x0010 | 0x0040 | 0x0200  # SWP_NOACTIVATE | SWP_SHOWWINDOW | SWP_NOOWNERZORDER
    return bool(user32.SetWindowPos(wintypes.HWND(handle), hwnd_topmost, x, y, width, height, flags))
