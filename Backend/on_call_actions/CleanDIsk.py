"""
CleanDisk.py

Deletes the contents of the user's temp folders (%TEMP% and
C:\\Windows\\Temp), clears Edge's cache, and empties the Recycle Bin.
Registered as the CLEANDISK on-call action (see on_call_actions/__init__.py).

Same minimal shape as find_file()/keyboard_control(): runs
synchronously on Server.py's on-call-action thread, no internal
threading, and returns a short text summary. Server.py takes it from
there and feeds it back into Gemini as a follow-up SYSTEM message.

Edge cache is deleted through the same delete_folder_contents() helper
as the temp folders — if Edge is currently open, whatever files it has
locked are just skipped (same per-item try/except as everything else),
so this is best-effort, not a guaranteed full clear.
"""

import ctypes
import os
import shutil
import tempfile
import time
from ctypes import wintypes
from pathlib import Path

EDGE_CACHE_FOLDERS = [
    r"Microsoft\Edge\User Data\Default\Cache",
    r"Microsoft\Edge\User Data\Default\Code Cache",
]

# Anything modified more recently than this is left alone — protects
# in-flight files like a TTS .wav or a downloaded image that's just
# been generated for the CURRENT response and is still waiting to be
# served via /audio/<id> or /image/<id> (both also live in the temp
# folder, via tempfile.NamedTemporaryFile). Without this, this action
# can delete the very file its own response is about to serve.
MIN_FILE_AGE_SECONDS = 60

SHERB_NOCONFIRMATION = 0x00000001
SHERB_NOPROGRESSUI = 0x00000002
SHERB_NOSOUND = 0x00000004


class SHQUERYRBINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("i64Size", ctypes.c_int64),
        ("i64NumItems", ctypes.c_int64),
    ]


def _empty_recycle_bin():
    """
    Returns how many bytes were freed, or 0 if the bin was already
    empty or its size couldn't be queried. Querying the size FIRST is
    necessary — SHEmptyRecycleBinW doesn't report back how much it
    freed, so there's nothing to read after the fact.
    """
    info = SHQUERYRBINFO()
    info.cbSize = ctypes.sizeof(SHQUERYRBINFO)

    freed_bytes = 0
    try:
        result = ctypes.windll.shell32.SHQueryRecycleBinW(None, ctypes.byref(info))
        if result == 0:
            freed_bytes = info.i64Size

        ctypes.windll.shell32.SHEmptyRecycleBinW(
            None, None, SHERB_NOCONFIRMATION | SHERB_NOPROGRESSUI | SHERB_NOSOUND
        )
    except Exception:
        return 0

    return freed_bytes


def clean_disk(result):
    deleted_files = 0
    deleted_folders = 0
    deleted_bytes = 0

    def get_folder_size(folder):
        total = 0
        try:
            for item in folder.rglob("*"):
                if item.is_file():
                    total += item.stat().st_size
        except Exception:
            pass
        return total

    def delete_folder_contents(folder):
        nonlocal deleted_files, deleted_folders, deleted_bytes

        folder = Path(folder)
        if not folder.exists():
            return

        try:
            items = list(folder.iterdir())
        except (PermissionError, OSError):
            return

        for item in items:
            try:
                if time.time() - item.stat().st_mtime < MIN_FILE_AGE_SECONDS:
                    continue

                if item.is_file() or item.is_symlink():
                    size = item.stat().st_size
                    item.unlink()
                    deleted_files += 1
                    deleted_bytes += size

                elif item.is_dir():
                    size = get_folder_size(item)
                    shutil.rmtree(item)
                    deleted_folders += 1
                    deleted_bytes += size

            except Exception:
                pass

    delete_folder_contents(tempfile.gettempdir())
    delete_folder_contents(r"C:\Windows\Temp")

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        for relative_path in EDGE_CACHE_FOLDERS:
            delete_folder_contents(Path(local_app_data) / relative_path)

    deleted_bytes += _empty_recycle_bin()

    mb_freed = deleted_bytes / (1024 * 1024)

    return (
        f"Deleted {deleted_files} file(s) and {deleted_folders} folder(s), "
        f"freeing {mb_freed:.2f} MB."
    )