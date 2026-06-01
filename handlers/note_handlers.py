from decorators import input_error
from models import AddressBook
from rich.table import Table
from rich.markup import escape
from handlers.display import show_paginated_table
from handlers.shared import (
    _require_record,
    _choose_from,
    _choose_many,
    _get_optional_tags,
)
from handlers.exceptions import FinishContactInput

_HIGHLIGHT = "black on yellow"


def _highlight(text, query):
    # Wrap every case-insensitive occurrence of query in rich highlight markup so
    # search results show *where* the match is. The rest of the text is escaped so
    # any brackets in a note aren't parsed as markup.
    if not query:
        return escape(text)
    low = text.lower()
    q = query.lower()
    out = []
    i = 0
    while (j := low.find(q, i)) != -1:
        out.append(escape(text[i:j]))
        out.append(f"[{_HIGHLIGHT}]{escape(text[j:j + len(q)])}[/{_HIGHLIGHT}]")
        i = j + len(q)
    out.append(escape(text[i:]))
    return "".join(out)


def _next_note_id(book):
    # IDs are unique across the whole book (not per contact) so a note can be
    # referenced unambiguously; take max-so-far + 1 to avoid reusing a deleted id.
    all_ids = [note.id for record in book.data.values() for note in record.notes]
    return max(all_ids, default=0) + 1


def _parse_tags(raw):
    # Split a comma-separated entry so several tags can be added at once; trims
    # blanks (the model also de-dupes).
    return [tag.strip() for tag in raw.split(",") if tag.strip()]


def _resolve_note(book, args):
    # Resolve which note a command targets so edit/delete/tag commands share one
    # rule: a numeric arg is a note ID (searched across the whole book); anything
    # else is a contact name, and when that contact has several notes the user
    # picks one. Returns (record, note), or (None, None) if the user cancels the
    # pick. Raises ValueError (-> friendly message) when the id/name/notes are missing.
    token = " ".join(args).strip()
    if token.isdigit():
        note_id = int(token)
        for record in book.data.values():
            for note in record.notes:
                if note.id == note_id:
                    return record, note
        raise ValueError(f"No note with ID {note_id}.")

    record = _require_record(book, token)
    if not record.notes:
        raise ValueError(f"'{token}' has no notes.")
    if len(record.notes) == 1:
        return record, record.notes[0]

    note = _choose_from(
        record.notes,
        lambda n: f"#{n.id} {n.value}",
        "Which note (number): ",
    )
    if note is None:
        return None, None
    return record, note


@input_error
def add_note(args, book: AddressBook):
    if not args:
        return "Error: Usage: add-note [name] [text]"
    # Names may be several words, so match the longest leading run of args that is
    # an existing contact; whatever follows is the inline note text. The full arg
    # string is tried first so "add-note <full name>" resolves to the contact with
    # no inline text, which then triggers the guided prompts below.
    record, split_at = None, 0
    for i in range(len(args), 0, -1):
        found = book.find(" ".join(args[:i]))
        if found:
            record, split_at = found, i
            break
    if record is None:
        raise KeyError(args[0])

    text = " ".join(args[split_at:]).strip()
    if text:
        # Inline form ("add-note <name> <text>"): add it straight away, no prompts.
        note_id = _next_note_id(book)
        record.add_note(text, note_id)
        return f"Note #{note_id} added to '{record.name.value}'."

    # Name given without note text: guide the user through entering the note, then
    # offer tags, instead of erroring out. A blank/cancelled note aborts cleanly.
    text = input("Enter note text (or 'cancel' to stop): ").strip()
    if not text or text.lower() == "cancel":
        return "Operation cancelled."
    note_id = _next_note_id(book)
    record.add_note(text, note_id)
    note = record.notes[-1]

    # Tags are optional: 'cancel' here keeps the note already created, just untagged
    # (consistent with the optional-tags step of interactive add-contact).
    try:
        tags = _get_optional_tags()
    except FinishContactInput:
        tags = []
    for tag in tags:
        note.add_tag(tag)

    suffix = f" with tags: {', '.join(note.tags)}" if note.tags else ""
    return f"Note #{note_id} added to '{record.name.value}'{suffix}."


@input_error
def edit_note(args, book: AddressBook):
    if not args:
        return "Error: Usage: edit-note [contact name | note id]"
    record, note = _resolve_note(book, args)
    if note is None:
        return "Operation cancelled."
    # edit_text keeps the note's id and tags (a previous bug rebuilt the note and
    # dropped its tags); the empty-text check lives in the model.
    note.edit_text(input("Enter new text: ").strip())
    return f"Note #{note.id} updated."


@input_error
def delete_note(args, book: AddressBook):
    if not args:
        return "Error: Usage: delete-note [contact name | note id]"
    record, note = _resolve_note(book, args)
    if note is None:
        return "Operation cancelled."
    record.delete_note(note.id)
    return f"Note #{note.id} deleted."


@input_error
def add_tag(args, book: AddressBook):
    if not args:
        return "Error: Usage: add-tag [contact name | note id]"
    record, note = _resolve_note(book, args)
    if note is None:
        return "Operation cancelled."
    tags = _parse_tags(input("Enter tag(s), comma-separated: ").strip())
    if not tags:
        return "Error: No tags entered."
    for tag in tags:
        note.add_tag(tag)
    return f"Note #{note.id} tags: {', '.join(note.tags)}."


@input_error
def edit_tag(args, book: AddressBook):
    # Edit-tag replaces the whole tag list at once (not a single tag) so the user
    # can re-state a note's tags in one go.
    if not args:
        return "Error: Usage: edit-tag [contact name | note id]"
    record, note = _resolve_note(book, args)
    if note is None:
        return "Operation cancelled."
    current = ", ".join(note.tags) if note.tags else "—"
    print(f"Current tags for note #{note.id}: {current}")
    note.set_tags(_parse_tags(input("New tag list, comma-separated (blank to clear): ").strip()))
    updated = ", ".join(note.tags) if note.tags else "—"
    return f"Note #{note.id} tags updated to: {updated}."


@input_error
def delete_tag(args, book: AddressBook):
    # With one tag it's removed directly; with several the user can pick one or many.
    if not args:
        return "Error: Usage: delete-tag [contact name | note id]"
    record, note = _resolve_note(book, args)
    if note is None:
        return "Operation cancelled."
    if not note.tags:
        return f"Error: note #{note.id} has no tags."

    if len(note.tags) == 1:
        targets = [note.tags[0]]
    else:
        targets = _choose_many(
            note.tags, lambda t: t,
            "Which tag(s) to delete (numbers, comma-separated, or 'all'): ",
        )
        if not targets:
            return "Operation cancelled."

    for tag in targets:
        note.remove_tag(tag)
    return f"Removed {len(targets)} tag(s) from note #{note.id}."


@input_error
def show_notes(args, book: AddressBook):
    if not args:
        return "Error: Usage: show-notes [name]"
    name = " ".join(args)
    record = _require_record(book, name)
    if not record.notes:
        return f"No notes for '{name}'."

    table = Table(title=f"Notes: {name}", header_style="bold cyan")
    table.add_column("Note ID", style="dim", width=8)
    table.add_column("Note", style="white")
    table.add_column("Tags", style="yellow")

    for note in record.notes:
        tags_str = ", ".join(note.tags) if note.tags else "—"
        table.add_row(str(note.id), note.value, tags_str)
    return table


@input_error
def show_all_notes(args, book: AddressBook):
    rows = []
    for record in book.data.values():
        for note in record.notes:
            tags_str = ", ".join(note.tags) if note.tags else "—"
            rows.append((record.name.value, str(note.id), note.value, tags_str))

    if not rows:
        return "No notes saved."

    columns = [
        ("Contact", {"style": "green"}),
        ("Note ID", {"style": "dim", "width": 8}),
        ("Note", {"style": "white"}),
        ("Tags", {"style": "yellow"}),
    ]
    return show_paginated_table("All Notes", columns, rows)


@input_error
def find_notes(args, book: AddressBook):
    if not args:
        return "Error: Usage: find-notes [query]"
    query = " ".join(args).lower()
    results = []

    for record in book.data.values():
        for note in record.notes:
            # Match against both text and tags so a tag-only hit still surfaces the note.
            in_text = query in note.value.lower()
            in_tags = any(query == t.lower() for t in note.tags)

            if in_text or in_tags:
                results.append((record.name.value, note.id, note.value, note.tags))

    if not results:
        return f"No notes found for query '{query}'."

    columns = [
        ("Contact", {"style": "green"}),
        ("Note ID", {"style": "dim", "width": 8}),
        ("Note", {"style": "white"}),
        ("Tags", {"style": "yellow"}),
    ]
    # Highlight the query inside the note text and tags so the match stands out.
    rows = [
        (
            name,
            str(nid),
            _highlight(text, query),
            _highlight(", ".join(tags), query) if tags else "—",
        )
        for name, nid, text, tags in results
    ]
    return show_paginated_table(f"Notes matching '{query}'", columns, rows)


@input_error
def find_by_tag(args, book: AddressBook):
    if not args:
        return "Error: Usage: find-by-tag [tag]"
    tag_query = args[0].lower()
    results = []

    for record in book.data.values():
        for note in record.notes:
            if any(tag_query == t.lower() for t in note.tags):
                results.append((record.name.value, note.id, note.value, note.tags))

    if not results:
        return f"No notes found with tag '{tag_query}'."

    columns = [
        ("Contact", {"style": "green"}),
        ("Note ID", {"style": "dim", "width": 8}),
        ("Note", {"style": "white"}),
        ("Tags", {"style": "yellow"}),
    ]
    # Highlight the matching tag so it stands out, like find-notes does; escape the
    # note text so any brackets in it aren't parsed as markup.
    rows = [
        (
            name,
            str(nid),
            escape(text),
            _highlight(", ".join(tags), tag_query) if tags else "—",
        )
        for name, nid, text, tags in results
    ]
    return show_paginated_table(f"Notes with tag '{tag_query}'", columns, rows)


@input_error
def sort_by_tags(args, book: AddressBook):
    results = []
    for record in book.data.values():
        for note in record.notes:
            if note.tags:
                results.append((record.name.value, note.id, note.value, note.tags))

    if not results:
        return "No notes with tags found."

    # Order by the first tag (case-insensitive) so notes group under the same tag.
    results.sort(key=lambda x: x[3][0].lower())

    columns = [
        ("Contact", {"style": "green"}),
        ("Note ID", {"style": "dim", "width": 8}),
        ("Note", {"style": "white"}),
        ("Tags", {"style": "yellow"}),
    ]
    rows = [(name, str(nid), text, ", ".join(tags))
            for name, nid, text, tags in results]
    return show_paginated_table("Notes Sorted by Tags", columns, rows)
