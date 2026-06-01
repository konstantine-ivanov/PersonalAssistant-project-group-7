from decorators import input_error
from models import AddressBook, Record
from handlers.display import show_paginated_table
from handlers.exceptions import FinishContactInput, OperationCancelled
from handlers.shared import (
    _validate_name,
    _split_name_and_value,
    _require_record,
    _get_mandatory_name,
    _get_mandatory_phone,
    _get_optional_email,
    _get_optional_birthday,
    _get_optional_note,
    _get_optional_tags,
    _get_address_details,
)


def _handle_existing_contact(record, new_phone):
    # During interactive add a name collision isn't an error: let the user add
    # the number as a new phone, replace an existing one, or cancel.
    print(f"Contact '{record.name.value}' already exists.")

    if record.phones:
        print(f"  Current phones: {'; '.join(p.value for p in record.phones)}")

    print("1 - Add as new phone\n2 - Replace existing phone\n3 - Cancel")
    choice = input("Your choice: ").strip()

    if choice == "1":
        record.add_phone(new_phone)
        return "New phone added."
    elif choice == "2":
        if not record.phones:
            record.add_phone(new_phone)
            return "Phone added."

        print("Which phone to replace?")
        for i, p in enumerate(record.phones, 1):
            print(f"    [{i}] {p.value}")

        idx = input("Number: ").strip()
        try:
            old_phone = record.phones[int(idx) - 1].value
            record.edit_phone(old_phone, new_phone)
            return f"Phone {old_phone} replaced with {new_phone}."
        except (ValueError, IndexError):
            raise ValueError("Invalid choice. Phone update canceled.")

    return None


@input_error
def add_contact(args, book: AddressBook):
    # Two entry styles so users aren't forced through every prompt: passing a
    # name does a quick add, while a bare "add" keeps the guided interactive flow.
    if args:
        return _add_contact_quick(args, book)
    return _add_contact_interactive(book)


def _add_contact_quick(args, book: AddressBook):
    # One-line entry: a name alone registers someone to flesh out later, and an
    # optional trailing phone makes the contact immediately usable without the
    # full interactive flow.
    # args: tokens after "add"; book: the address book. Returns a status string.
    name_parts, phone = _split_name_and_value(args)
    full_name = " ".join(name_parts).title()

    error = _validate_name(full_name)
    if error:
        return error

    # An existing name is left untouched: quick-add only creates, so the user is
    # told it exists rather than silently mutating a contact they may not mean.
    if book.find(full_name):
        return f"Error: Contact '{full_name}' already exists."

    record = Record(full_name)
    if phone:
        # Validate the phone before storing the record so a bad number can't
        # leave an orphan empty contact behind.
        record.add_phone(phone)
    book.add_record(record)

    return (
        f"Contact '{full_name}' created with phone {phone}."
        if phone
        else f"Contact '{full_name}' created."
    )


def _add_contact_interactive(book: AddressBook):
    # "cancel" at any mandatory prompt aborts; "cancel" at optional prompts saves
    # what's already been entered (FinishContactInput) so data isn't lost.
    print("Type 'cancel' at any optional step to stop and save what's entered.")
    try:
        full_name = _get_mandatory_name()
        phone_input = _get_mandatory_phone()
    except (OperationCancelled, FinishContactInput):
        return "Operation cancelled."

    record = book.find(full_name)

    try:
        if not record:
            record = Record(full_name)
            record.add_phone(phone_input)
            book.add_record(record)
            message = f"Contact '{full_name}' created."
        else:
            phone_message = _handle_existing_contact(record, phone_input)
            if phone_message is None:
                return "Operation cancelled."
            message = f"Contact '{full_name}' updated. {phone_message}"

        email = _get_optional_email()
        if email:
            record.add_email(email)
        birthday = _get_optional_birthday()
        if birthday:
            record.add_birthday(birthday)

        add_address = input("Add address? (y/n, or 'cancel' to stop): ").strip().lower()
        if add_address in ["y", "yes"]:
            address_string = _get_address_details()
            if address_string:
                record.add_address(address_string)

        note_text = _get_optional_note()
        if note_text:
            from handlers.note_handlers import _next_note_id
            note_id = _next_note_id(book)
            record.add_note(note_text, note_id)
            tags = _get_optional_tags()
            for tag in tags:
                record.notes[-1].add_tag(tag)

    except FinishContactInput:
        return f"{message} Additional fields skipped."

    return f"{message} All details saved."


@input_error
def delete_contact(args, book: AddressBook):
    if not args:
        return "Error: Usage: delete-contact [name]"
    name = " ".join(args)
    record = _require_record(book, name)
    book.delete(record.name.value)
    return f"Contact '{name}' deleted."


# Columns shared by the two full-record views (find-contact and show-contacts-full):
# every contact field plus the contact's notes and tags.
_FULL_CONTACT_COLUMNS = [
    ("Name", {"style": "green"}),
    ("Phones", {}),
    ("Email", {}),
    ("Birthday", {}),
    ("Address", {}),
    ("Notes", {}),
    ("Tags", {"style": "yellow"}),
]


def _full_contact_rows(records):
    # Build the table rows for the full-record views so find-contact and
    # show-contacts-full render each contact identically (same fields, same order).
    rows = []
    for record in records:
        phones = "; ".join(str(p) for p in record.phones) or "—"
        email = "; ".join(e.value for e in record.emails) or "—"
        birthday = str(record.birthday) if record.birthday else "—"
        address = str(record.address) if record.address else "—"

        # Tags belong to a note, not the contact, so render them line-by-line
        # aligned with the Notes column: each note's tags sit on the same row as
        # the note itself, instead of being flattened into one per-contact string.
        notes_list = []
        tags_list = []
        for note in record.notes:
            notes_list.append(f"[{note.id}] {note.value}")
            tags_list.append(", ".join(note.tags) if note.tags else "—")
        notes_text = "\n".join(notes_list) or "—"
        tags_text = "\n".join(tags_list) or "—"

        rows.append((record.name.value, phones, email, birthday, address, notes_text, tags_text))
    return rows


@input_error
def find_contact(args, book: AddressBook):
    if not args:
        return "Error: Usage: find-contact [query]"
    query = " ".join(args).lower().strip()
    exact = []
    partial = []

    for record in book.data.values():
        name_lower = record.name.value.lower()
        # Exact = the query is the whole name or one of its parts (first/last name).
        if query == name_lower or query in name_lower.split():
            exact.append(record)
            continue
        # Partial = substring of the name or any phone number.
        if query in name_lower or any(query in p.value for p in record.phones):
            partial.append(record)

    # Prefer exact name/surname hits: searching "John" returns John, not Johnson.
    # Fall back to partial matches only when there's no exact one.
    found_records = exact or partial

    if not found_records:
        return "No contacts found."

    # Show the full record (notes + tags included) so search results carry the
    # same detail as show-contacts-full.
    return show_paginated_table(
        f"Search Results for '{' '.join(args)}'",
        _FULL_CONTACT_COLUMNS,
        _full_contact_rows(found_records),
    )


@input_error
def all_with_notes(args, book: AddressBook):
    if not book.data:
        return "No contacts saved."

    return show_paginated_table(
        "All Contacts",
        _FULL_CONTACT_COLUMNS,
        _full_contact_rows(book.data.values()),
    )
