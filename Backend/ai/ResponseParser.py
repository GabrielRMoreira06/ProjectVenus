"""
response_parser.py

Parses the raw line-based text Gemini returns (see RESPONSE_RULES in
prompts.py) into a structured dict. This is the single place that
understands that text format — nothing else should be splitting lines
like this.
"""

VALID_ACTIONS = {
    "NONE",
    "STEALMOUSE",
    "SHOWIMAGE",
    "ALLOWPET",
    "FINDFILE",
    "KEYBOARDCONTROL",
    "SCREAM",
    "REMINDER",
    "FLIP",
    "ORGANIZEFILES",
    "JUDGE",
    "CLEANDISK",
}


class ResponseParser:

    def parse(self, response_text):
        text = ""
        action = "NONE"
        mood_variant = None
        mood_shift = None
        memory_type = "NONE"
        memory_id = "NONE"
        memory_text = "NONE"
        memory_expire = "NONE"
        image_query = "NONE"
        file_query = "NONE"
        keyboardcontrol_query = "NONE"
        reminder_query = "NONE"
        reminder_minutes = "NONE"
        select_days = "NONE"
        reminder_time = "NONE"
        update_profile_picture = "NONE"
        update_ui_theme = "NONE"

        for line in response_text.splitlines():

            if line.startswith("TEXT:"):
                text = line[5:].strip()

            elif line.startswith("ACTION:"):
                action = line[7:].strip()

            elif line.startswith("MOOD_VARIANT:"):
                mood_variant = line.replace("MOOD_VARIANT:", "").strip()

            elif line.startswith("MOOD_SHIFT:"):
                mood_shift = line.replace("MOOD_SHIFT:", "").strip()

            elif line.startswith("MEMORY_TYPE:"):
                memory_type = line.replace("MEMORY_TYPE:", "").strip()

            elif line.startswith("MEMORY_ID:"):
                memory_id = line.replace("MEMORY_ID:", "").strip()

            elif line.startswith("MEMORY_TEXT:"):
                memory_text = line.replace("MEMORY_TEXT:", "").strip()

            elif line.startswith("MEMORY_EXPIRE:"):
                memory_expire = line.replace("MEMORY_EXPIRE:", "").strip()

            elif line.startswith("IMAGE_QUERY:"):
                image_query = line.replace("IMAGE_QUERY:", "").strip()

            elif line.startswith("FILE_QUERY:"):
                file_query = line.replace("FILE_QUERY:", "").strip()

            elif line.startswith("KEYBOARDCONTROL_QUERY:"):
                keyboardcontrol_query = line.replace("KEYBOARDCONTROL_QUERY:", "").strip()

            elif line.startswith("REMINDER_QUERY:"):
                reminder_query = line.replace("REMINDER_QUERY:", "").strip()

            elif line.startswith("REMINDER_MINUTES:"):
                reminder_minutes = line.replace("REMINDER_MINUTES:", "").strip()
            elif line.startswith("SELECT_DAYS:"):
                select_days = line.replace("SELECT_DAYS:", "").strip()

            elif line.startswith("REMINDER_TIME:"):
                reminder_time = line.replace("REMINDER_TIME:", "").strip()

            elif line.startswith("UPDATE_PROFILE_PICTURE:"):
                update_profile_picture = line.replace("UPDATE_PROFILE_PICTURE:", "").strip()

            elif line.startswith("UPDATE_UI_THEME:"):
                update_ui_theme = line.replace("UPDATE_UI_THEME:", "").strip()

        if action not in VALID_ACTIONS:
            print(f"[ResponseParser] Unknown ACTION received from Gemini: '{action}' — using NONE instead.")
            action = "NONE"

        return {
            "text": text,
            "action": action,
            "mood_variant": mood_variant,
            "mood_shift": mood_shift,
            "memory_type": memory_type,
            "memory_id": memory_id,
            "memory_text": memory_text,
            "memory_expire": memory_expire,
            "image_query": image_query,
            "file_query": file_query,
            "keyboardcontrol_query": keyboardcontrol_query,
            "reminder_query": reminder_query,
            "reminder_minutes": reminder_minutes,
            "select_days": select_days,
            "reminder_time": reminder_time,
            "update_profile_picture": update_profile_picture,
            "update_ui_theme": update_ui_theme,
        }