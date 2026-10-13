"""
response_parser.py

Parses the raw line-based text Gemini returns (see RESPONSE_RULES in
prompts.py) into a structured dict. This is the single place that
understands that text format — nothing else should be splitting lines
like this.
"""

VALID_ACTIONS = {
    "NONE", "STEALMOUSE", "SHOWIMAGE", "ALLOWPET", "FINDFILE",
    "KEYBOARDCONTROL", "SCREAM", "REMINDER", "FLIP", "ORGANIZEFILES",
    "JUDGE", "CLEANDISK", "DEADPIXEL", "LOWERBRIGHTNESS", "NOTEPAD", "DICE",
}

VALID_ANIMATIONS = {"NONE", "IDLE", "WORKING", "RELAXING"}

# prefix in Gemini's response -> (key in result dict, default value)
FIELDS = {
    "TEXT": ("text", ""),
    "ACTION": ("action", "NONE"),
    "ANIMATION": ("animation", "NONE"),
    "MOOD_VARIANT": ("mood_variant", None),
    "MOOD_SHIFT": ("mood_shift", None),
    "MEMORY_TYPE": ("memory_type", "NONE"),
    "MEMORY_TEXT": ("memory_text", "NONE"),
    "MEMORY_EXPIRE": ("memory_expire", "NONE"),
    "IMAGE_QUERY": ("image_query", "NONE"),
    "FILE_QUERY": ("file_query", "NONE"),
    "KEYBOARDCONTROL_QUERY": ("keyboardcontrol_query", "NONE"),
    "REMINDER_QUERY": ("reminder_query", "NONE"),
    "REMINDER_MINUTES": ("reminder_minutes", "NONE"),
    "SELECT_DAYS": ("select_days", "NONE"),
    "REMINDER_TIME": ("reminder_time", "NONE"),
    "UPDATE_PROFILE_PICTURE": ("update_profile_picture", "NONE"),
    "UPDATE_UI_THEME": ("update_ui_theme", "NONE"),
    "EDIT_CONTENT": ("edit_content", "NONE"),
}

# fields that are allowed to span several lines
MULTILINE_FIELDS = {"text", "edit_content"}


class ResponseParser:

    def parse(self, response_text):
        result = {key: default for key, default in FIELDS.values()}
        current = None  # the field we're currently filling

        for line in response_text.splitlines():
            prefix, sep, value = line.partition(":")

            if sep and prefix in FIELDS:
                # a new field starts here
                current = FIELDS[prefix][0]
                result[current] = value.strip()
            elif current in MULTILINE_FIELDS:
                # continuation line of a multi-line field
                result[current] += "\n" + line

        # trim leading/trailing blank lines from multi-line fields
        for key in MULTILINE_FIELDS:
            result[key] = result[key].strip()

        result["animation"] = result["animation"].upper()

        if result["action"] not in VALID_ACTIONS:
            print(f"[ResponseParser] Unknown ACTION received from Gemini: '{result['action']}' — using NONE instead.")
            result["action"] = "NONE"

        if result["animation"] not in VALID_ANIMATIONS:
            print(f"[ResponseParser] Unknown ANIMATION received from Gemini: '{result['animation']}' — using NONE instead.")
            result["animation"] = "NONE"

        return result