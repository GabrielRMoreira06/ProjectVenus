"""
FileOrganizer.py

Sorts loose files in Downloads into subfolders by extension.
Registered as the ORGANIZEFILES on-call action (see
on_call_actions/__init__.py).

Same minimal shape as find_file/keyboard_control: no internal
threading (Server.py already runs this on its own thread), and the
return value becomes the follow-up SYSTEM message text fed back to
Gemini once the move is done.
"""

import os
import shutil

FOLDER = r"C:\Users\User\Downloads"

CATEGORIES = {
    ".jpg": "Images", ".jpeg": "Images", ".png": "Images", ".gif": "Images", ".webp": "Images",
    ".pdf": "Documents", ".docx": "Documents", ".txt": "Documents",
    ".mp4": "Videos", ".avi": "Videos",
    ".mp3": "Music", ".wav": "Music",
    ".zip": "Zips",
}


def organize_files(result):
    if not os.path.isdir(FOLDER):
        return f"Downloads folder not found at '{FOLDER}'."

    moved_by_category = {}

    for file in os.listdir(FOLDER):
        file_path = os.path.join(FOLDER, file)

        if not os.path.isfile(file_path):
            continue

        extension = os.path.splitext(file)[1].lower()
        category = CATEGORIES.get(extension, "Other")

        destination_folder = os.path.join(FOLDER, category)
        os.makedirs(destination_folder, exist_ok=True)

        try:
            shutil.move(file_path, os.path.join(destination_folder, file))
            moved_by_category[category] = moved_by_category.get(category, 0) + 1
        except OSError:
            continue  # likely still being downloaded / locked — skip it

    if not moved_by_category:
        return "Checked Downloads, nothing needed organizing."

    summary = ", ".join(f"{count} {category}" for category, count in moved_by_category.items())
    return f"Organized Downloads: {summary}."