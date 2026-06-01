import csv
import json
import os
from datetime import datetime
from decorators import input_error
from models import AddressBook
from handlers.utils import save_data

EXPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "exported_files")

# Typed verbatim to confirm a full wipe. Long and specific on purpose so it can't
# be entered by accident — a plain "yes" must never erase the whole book.
DUMP_CONFIRMATION = "Yes, I want to delete all the addressbook"


def _record_to_dict(record):
    return {
        "name": record.name.value,
        "phones": [p.value for p in record.phones],
        "emails": [e.value for e in record.emails],
        "birthday": str(record.birthday) if record.birthday else "",
        "address": str(record.address) if record.address else "",
        "notes": [
            {"id": note.id, "text": note.value, "tags": note.tags}
            for note in record.notes
        ],
    }


def _default_filename(fmt):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"address_book_{timestamp}.{fmt}"


def _resolve_path(filename, fmt):
    if not filename.endswith(f".{fmt}"):
        filename += f".{fmt}"
    # A bare filename goes into a dedicated EXPORT_DIR to keep the repo root tidy;
    # a path-like value is honoured as-is so users can export anywhere.
    if os.path.isabs(filename) or os.sep in filename or "/" in filename:
        return filename
    os.makedirs(EXPORT_DIR, exist_ok=True)
    return os.path.join(EXPORT_DIR, filename)


def _export_json(book, filepath):
    data = [_record_to_dict(r) for r in book.data.values()]
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _export_csv(book, filepath):
    # CSV is flat, so multi-valued fields are joined into one cell and a contact
    # with several notes becomes several rows (one per note) to avoid losing any.
    fieldnames = [
        "name", "phones", "email", "birthday",
        "address", "note_id", "note_text", "note_tags",
    ]
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for record in book.data.values():
            base = {
                "name": record.name.value,
                "phones": "; ".join(p.value for p in record.phones),
                "email": "; ".join(e.value for e in record.emails),
                "birthday": str(record.birthday) if record.birthday else "",
                "address": str(record.address) if record.address else "",
            }
            if record.notes:
                for note in record.notes:
                    writer.writerow({
                        **base,
                        "note_id": note.id,
                        "note_text": note.value,
                        "note_tags": "; ".join(note.tags),
                    })
            else:
                writer.writerow({**base, "note_id": "", "note_text": "", "note_tags": ""})


@input_error
def export_book(args, book: AddressBook):
    if not book.data:
        return "Address book is empty — nothing to export."

    fmt = args[0].lower() if args else ""
    if fmt not in ("csv", "json"):
        return "Error: Usage: export-book [csv|json] [optional: path/filename]"

    # Honour an explicit path/filename if given; otherwise fall back to a
    # timestamped name in EXPORT_DIR so repeated exports don't overwrite each other.
    custom_path = args[1] if len(args) > 1 else None
    if custom_path:
        filepath = custom_path if custom_path.endswith(f".{fmt}") else custom_path + f".{fmt}"
    else:
        filepath = _resolve_path(_default_filename(fmt), fmt)

    if fmt == "json":
        _export_json(book, filepath)
    else:
        _export_csv(book, filepath)

    return f"Address book exported to '{filepath}' ({len(book.data)} contacts)."


@input_error
def save_book(args, book: AddressBook):
    # Persist on demand so users aren't forced to close the app to keep changes;
    # the app still also saves on a clean exit (see main).
    save_data(book)
    return f"Address book saved ({len(book.data)} contacts)."


@input_error
def dump_book(args, book: AddressBook):
    # Wiping the whole book is destructive, so it's a two-step confirm: this
    # command only asks; the wipe happens only if the user then types the exact
    # confirmation phrase. Anything else (incl. an empty line) aborts untouched.
    if not book.data:
        return "Address book is already empty."

    answer = input(
        f"This will delete ALL {len(book.data)} contacts.\n"
        f'Type exactly  "{DUMP_CONFIRMATION}"  to confirm: '
    ).strip()

    if answer != DUMP_CONFIRMATION:
        return "Dump cancelled — address book left unchanged."

    book.data.clear()
    # Persist the empty book immediately so the wipe survives even if the app is
    # killed before a clean exit.
    save_data(book)
    return "Address book wiped — all contacts deleted."
