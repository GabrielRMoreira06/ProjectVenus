"""
StartupManager.py

Adds/removes a Windows Registry Run key so Project Venus launches
automatically at login. Backed directly by the registry (not
preferences.json) since the registry key IS the actual state — the
user could remove it manually outside the app, and preferences.json
would then be lying.
"""

import os
import sys
import winreg

RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "ProjectVenus"


def _launch_command():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'

    script = os.path.abspath(sys.argv[0])
    return f'"{sys.executable}" "{script}"'


def is_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, APP_NAME)
            return True
    except FileNotFoundError:
        return False


def set_enabled(enabled):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _launch_command())
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass
    except OSError as error:
        print(f"[StartupManager] Failed to update Run key: {error}")