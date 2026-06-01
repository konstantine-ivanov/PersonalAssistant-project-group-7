"""Command registry: the single name -> handler dispatch table the REPL uses.

Imports are grouped by field module so it's easy to see which handler backs each
command, and the dict is grouped by the same sections as the help output
(see commands/meta.py GROUP_ORDER).
"""

from handlers.contact_handlers import (
    add_contact,
    delete_contact,
    find_contact,
    all_with_notes,
)
from handlers.phone_handlers import (
    change_contact,
    add_phone,
    remove_phone,
)
from handlers.email_handlers import (
    add_email,
    edit_email,
    delete_email,
)
from handlers.address_handlers import (
    add_address,
    edit_address,
    delete_address,
)
from handlers.birthday_handlers import (
    add_birthday,
    edit_birthday,
    delete_birthday,
)
from handlers.display import (
    display_all,
    display_phone,
    display_birthday,
    display_birthdays,
    show_help,
    hello_message,
)
from handlers.note_handlers import (
    add_note,
    edit_note,
    delete_note,
    show_notes,
    show_all_notes,
    find_notes,
    add_tag,
    edit_tag,
    delete_tag,
    find_by_tag,
    sort_by_tags,
)
from handlers.export_handlers import export_book, save_book, dump_book

commands = {
    # General
    "hello": hello_message,
    "help": show_help,

    # Contacts
    "add": add_contact,
    "show-contacts": display_all,
    "show-contacts-full": all_with_notes,
    "find-contact": find_contact,
    "delete-contact": delete_contact,

    # Phones
    "add-phone": add_phone,
    "edit-phone": change_contact,
    "show-phone": display_phone,
    "delete-phone": remove_phone,

    # Emails
    "add-email": add_email,
    "edit-email": edit_email,
    "delete-email": delete_email,

    # Birthdays
    "add-birthday": add_birthday,
    "edit-birthday": edit_birthday,
    "delete-birthday": delete_birthday,
    "show-birthday": display_birthday,
    "upcoming-birthdays": display_birthdays,

    # Addresses
    "add-address": add_address,
    "edit-address": edit_address,
    "delete-address": delete_address,

    # Notes
    "add-note": add_note,
    "edit-note": edit_note,
    "delete-note": delete_note,
    "show-notes": show_notes,
    "show-all-notes": show_all_notes,
    "find-notes": find_notes,

    # Tags
    "add-tag": add_tag,
    "edit-tag": edit_tag,
    "delete-tag": delete_tag,
    "find-by-tag": find_by_tag,
    "show-notes-by-tag": sort_by_tags,

    # Data
    "export-book": export_book,
    "save": save_book,
    "dump": dump_book,
}
