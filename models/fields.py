import re
from datetime import datetime, date

MAX_NAME_LENGTH = 50
MAX_ADDRESS_LENGTH = 100


class Field:
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return str(self.value)


# Validation lives in the model so every Record gets the same rules whatever path
# creates it. A name part may mix letters with hyphens and apostrophes so real
# names like O'Brien, Anne-Marie and Jean-Luc are accepted, but it must still hold
# at least one letter — that keeps out digits and bare "-"/"'" tokens.
class Name(Field):
    _ALLOWED_PUNCTUATION = {"-", "'"}

    def __init__(self, value):
        value = value.strip()
        if not value:
            raise ValueError("Name is required.")
        if len(value) > MAX_NAME_LENGTH:
            raise ValueError(f"Name must be at most {MAX_NAME_LENGTH} characters.")
        for part in value.split():
            has_letter = any(ch.isalpha() for ch in part)
            only_allowed = all(
                ch.isalpha() or ch in self._ALLOWED_PUNCTUATION for ch in part
            )
            if not (has_letter and only_allowed):
                raise ValueError(
                    f"'{part}' may contain only letters, hyphens and apostrophes."
                )
        super().__init__(value)


class Phone(Field):
    def __init__(self, value):
        # Store digits only (strip any formatting) so the same number always
        # compares equal regardless of how the user typed it.
        cleaned_value = re.sub(r"\D", "", value)
        if len(cleaned_value) != 10:
            raise ValueError(f"Phone number must contain exactly 10 digits: {cleaned_value}")
        super().__init__(cleaned_value)

    def __str__(self):
        # Render the bare digits as a Ukrainian-formatted number for display only.
        v = self.value
        return f"+38({v[:3]}){v[3:6]}-{v[6:8]}-{v[8:]}"


class Birthday(Field):
    def __init__(self, value):
        # Keep a real date object (not the string) so AddressBook can do date
        # arithmetic for upcoming-birthday calculations.
        try:
            parsed = datetime.strptime(value, "%d.%m.%Y").date()
        except ValueError:
            raise ValueError("Invalid date format. Use DD.MM.YYYY")
        # A birthday in the future is always a typo, so reject it.
        if parsed > date.today():
            raise ValueError("Birthday cannot be in the future.")
        self.value = parsed

    def __str__(self):
        return self.value.strftime("%d.%m.%Y")


class Email(Field):
    def __init__(self, value):
        # Require a letters-only TLD of length >= 2 so trailing dots/hyphens and
        # bare domains (user@example.) are rejected.
        pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        if not re.match(pattern, value):
            raise ValueError("Invalid email format. Example: user@example.com")
        super().__init__(value)


# Free-form text, but length-capped so a stray paste can't bloat the record.
class Address(Field):
    def __init__(self, value):
        value = value.strip()
        if not value:
            raise ValueError("Address cannot be empty.")
        if len(value) > MAX_ADDRESS_LENGTH:
            raise ValueError(f"Address must be at most {MAX_ADDRESS_LENGTH} characters.")
        super().__init__(value)


class Note(Field):
    def __init__(self, value, note_id):
        # Reject empty/whitespace notes so the list never holds blank entries.
        if not value.strip():
            raise ValueError("Note cannot be empty.")
        super().__init__(value.strip())
        self.id = note_id
        self.tags = []

    def edit_text(self, new_text):
        # Edit text in place (instead of rebuilding the Note) so the note keeps
        # its id and tags; reuse the same non-empty rule as creation.
        if not new_text.strip():
            raise ValueError("Note cannot be empty.")
        self.value = new_text.strip()

    def add_tag(self, tag):
        # Skip duplicates so the same tag can't pile up on one note.
        if tag not in self.tags:
            self.tags.append(tag)

    def remove_tag(self, tag):
        # Raise on a missing tag so the caller reports it instead of silently
        # doing nothing.
        if tag not in self.tags:
            raise ValueError(f"Note #{self.id} has no tag '{tag}'.")
        self.tags.remove(tag)

    def set_tags(self, tags):
        # Replace the whole tag list at once (used by edit-tag). De-duplicate and
        # drop blanks while preserving the given order.
        cleaned = []
        for tag in tags:
            tag = tag.strip()
            if tag and tag not in cleaned:
                cleaned.append(tag)
        self.tags = cleaned
