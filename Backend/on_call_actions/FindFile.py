"""
FindFile.py

Searches the user's common folders (and, as a last resort, every drive
on the machine) for files whose name contains the search text.
Registered as the FINDFILE on-call action (see
on_call_actions/__init__.py).

Adapted from the original synchronous, input()-driven CLI version —
that interactive "type a number to pick a file" step doesn't make
sense here (nothing is reading stdin, and this runs on a background
thread with no terminal). If exactly one file matches, Explorer is
opened with it selected, same spirit as before; otherwise the full
list of matches is handed back as text for Venus to relay.

find_file() is meant to be slow-tolerant: Server.py always runs it on
its own thread, never inside Orchestrator's worker thread, so a full
multi-drive scan doesn't stall anything else queued up behind it.
"""

import os
import subprocess

import psutil

# Folder names skipped on EVERY drive when the search falls back to a
# full scan — huge, low-signal, or permission-locked system folders.
IGNORED_FOLDER_NAMES = (
    "Windows",
    "Program Files",
    "Program Files (x86)",
    "$Recycle.Bin",
    "System Volume Information",
)

MAX_RESULTS_LISTED = 20


def find_file(result):
    """
    Entry point registered in ON_CALL_ACTIONS. `result` is the full
    parsed Gemini response dict — this reads FILE_QUERY off it.
    Returns a short text summary meant to be fed back into Gemini as a
    system message, not shown to the user directly.
    """
    query = (result.get("file_query") or "").strip().lower()

    if not query or query == "none":
        return "No search term was provided, so no search was run."

    home = os.path.expanduser("~")

    main_folders = [
        os.path.join(home, "Downloads"),
        os.path.join(home, "Documents"),
        os.path.join(home, "Pictures"),
        os.path.join(home, "Desktop"),
        r"D:\Downloads",
    ]

    matches = _search_folders(main_folders, query)

    # Fallback 1: everything else directly under the user's profile.
    if not matches:
        try:
            other_folders = [
                os.path.join(home, item)
                for item in os.listdir(home)
                if os.path.isdir(os.path.join(home, item))
            ]
            matches = _search_folders(other_folders, query)
        except (PermissionError, OSError):
            pass

    # Fallback 2: last resort, every drive on the machine (C:\, D:\, ...).
    if not matches:
        drive_roots = _get_drive_roots()
        matches = _search_folders(
            drive_roots, query, ignored=_build_ignored_folders(drive_roots)
        )

    if not matches:
        return f"No files matching '{query}' were found on the user's computer."

    if len(matches) == 1:
        _reveal_in_explorer(matches[0])
        return f"Found 1 file matching '{query}': {matches[0]}. Opened it in Explorer for the user."

    shown = matches[:MAX_RESULTS_LISTED]
    listing = "\n".join(shown)
    remaining = len(matches) - len(shown)
    truncated_note = f"\n(+{remaining} more not shown)" if remaining > 0 else ""

    return f"Found {len(matches)} files matching '{query}':\n{listing}{truncated_note}"


def _get_drive_roots():
    """
    Mount points of every fixed/local drive (C:\\, D:\\, ...), skipping
    CD-ROMs. Same filter DiskInspector uses, so a newly added drive is
    picked up automatically with no code change.
    """
    roots = []

    for partition in psutil.disk_partitions(all=False):
        if "cdrom" in partition.opts or partition.fstype == "":
            continue
        roots.append(partition.mountpoint)

    return roots


def _build_ignored_folders(drive_roots):
    return {
        os.path.normcase(os.path.join(root, name))
        for root in drive_roots
        for name in IGNORED_FOLDER_NAMES
    }


def _search_folders(folders, query, ignored=None):
    ignored = ignored or set()
    visited = set()
    matches = []

    for folder in folders:
        if not folder or not os.path.isdir(folder):
            continue

        folder = os.path.abspath(folder)

        if os.path.normcase(folder) in visited:
            continue

        visited.add(os.path.normcase(folder))

        try:
            for root, dirs, files in os.walk(folder):
                dirs[:] = [
                    d for d in dirs
                    if os.path.normcase(os.path.join(root, d)) not in ignored
                ]

                for name in files:
                    if query in name.lower():
                        matches.append(os.path.join(root, name))

        except (PermissionError, OSError):
            continue

    return matches


def _reveal_in_explorer(path):
    try:
        subprocess.run(["explorer.exe", "/select,", os.path.normpath(path)])
    except OSError:
        pass