"""Single source of truth for command names, arg hints, descriptions and groups.

Both the help table (show_help) and the autocompletion (CommandCompleter) read
from here, so adding/renaming a command only needs an edit in one place.
"""

# Display order of help sections; show_help renders groups in this sequence.
GROUP_ORDER = [
    "General",
    "Contacts",
    "Phones",
    "Emails",
    "Birthdays",
    "Addresses",
    "Notes",
    "Tags",
    "Data",
]

COMMAND_META: dict[str, tuple[str, str, str]] = {
    #  command: (args_hint, description, group)
    "hello": ("", "Greet the bot", "General"),
    "help": ("", "Show all available commands", "General"),
    "close": ("", "Quit the bot", "General"),
    "exit": ("", "Quit the bot", "General"),

    "add": (
        "[name] [phone]",
        "Add by name (+optional phone), or 'add' alone for full interactive entry",
        "Contacts",
    ),
    "show-contacts": ("", "Show all contacts", "Contacts"),
    "show-contacts-full": (
        "",
        "Show all contacts with all fields including notes",
        "Contacts",
    ),
    "find-contact": ("[query]", "Search contacts by name or phone", "Contacts"),
    "delete-contact": ("[name]", "Delete a contact", "Contacts"),

    "add-phone": ("[name] [phone]", "Add a phone to a contact (prompts if no number)", "Phones"),
    "edit-phone": ("[name]", "Edit a phone (choose if several)", "Phones"),
    "show-phone": ("[name]", "Show phone number(s)", "Phones"),
    "delete-phone": ("[name] [phone]", "Remove phone(s) - pick one or many if several", "Phones"),

    "add-email": ("[name] [email]", "Add an email to a contact (prompts if none)", "Emails"),
    "edit-email": ("[name]", "Edit an email (choose if several)", "Emails"),
    "delete-email": ("[name] [email]", "Remove email(s) - pick one or many if several", "Emails"),

    "add-birthday": ("[name] [DD.MM.YYYY]", "Add birthday", "Birthdays"),
    "edit-birthday": ("[name] [DD.MM.YYYY]", "Edit birthday", "Birthdays"),
    "delete-birthday": ("[name]", "Remove birthday", "Birthdays"),
    "show-birthday": ("[name]", "Show birthday", "Birthdays"),
    "upcoming-birthdays": ("[days]", "Upcoming birthdays (default: 7 days)", "Birthdays"),

    "add-address": ("[name]", "Add an address (guided entry)", "Addresses"),
    "edit-address": ("[name]", "Edit the address (guided entry)", "Addresses"),
    "delete-address": ("[name]", "Remove the address", "Addresses"),

    "add-note": ("[name] [text]", "Add a note to a contact", "Notes"),
    "edit-note": ("[name|id]", "Edit a note's text (by note id or contact)", "Notes"),
    "delete-note": ("[name|id]", "Delete a note (by note id or contact)", "Notes"),
    "show-notes": ("[name]", "Show all notes for a contact", "Notes"),
    "show-all-notes": ("", "Show all notes across all contacts", "Notes"),
    "find-notes": ("[query]", "Search notes across all contacts", "Notes"),

    "add-tag": ("[name|id]", "Add tag(s) to a note, comma-separated", "Tags"),
    "edit-tag": ("[name|id]", "Replace a note's whole tag list", "Tags"),
    "delete-tag": ("[name|id]", "Remove tag(s) from a note - pick one or many", "Tags"),
    "find-by-tag": ("[tag]", "Search notes by a specific tag", "Tags"),
    "show-notes-by-tag": ("", "Show all notes grouped by tags", "Tags"),

    "export-book": ("[csv|json] [path]", "Export address book to CSV or JSON file", "Data"),
    "save": ("", "Save the address book to disk now", "Data"),
    "dump": ("", "Delete ALL contacts (asks for a confirmation phrase)", "Data"),
}
