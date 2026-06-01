import random
import re

from rich.table import Table
from rich.markup import escape
from decorators import input_error
from models import AddressBook
from rich.console import Console

# highlight=False disables rich's automatic repr-highlighter. We style everything
# explicitly (table column styles, [bold red] errors, the welcome banner), so the
# only thing auto-highlighting did was miscolour plain messages — e.g. a name in
# single quotes like 'Anne-Marie O'Connor' was painted as a string up to the
# apostrophe in O'Connor, splitting its colour mid-word.
console = Console(highlight=False)


# Our messages wrap contact names in single quotes. Colour the whole quoted name
# green — like rich's old auto-highlighter did — but, unlike it, keep the colour
# unbroken across an internal apostrophe (O'Connor): a quote followed by a letter
# is part of the name, only a quote NOT followed by a letter closes it.
_QUOTED_NAME = re.compile(r"'[^']*(?:'[A-Za-z][^']*)*'")


def _highlight_names(text):
    return _QUOTED_NAME.sub(lambda m: f"[green]{m.group(0)}[/green]", text)


def _print(result):
    # Highlight error strings in red, colour quoted names green in other messages,
    # and pass rich renderables (e.g. tables) through untouched so they keep their
    # own formatting.
    if isinstance(result, str) and result.startswith("Error"):
        # Escape the text so bracketed usage hints like "[name]" aren't swallowed
        # as rich markup; the [bold red] wrapper still applies.
        console.print(f"[bold red]{escape(result)}[/bold red]")
    elif isinstance(result, str):
        console.print(_highlight_names(result))
    else:
        console.print(result)


def paginate(items, page_size=15):
    # Yield successive page_size-sized chunks so large tables can be shown one
    # page at a time instead of flooding the console.
    for i in range(0, len(items), page_size):
        yield items[i:i + page_size]


def show_paginated_table(title, columns, rows, page_size=15):
    # Paginate only when needed: small results are returned as a Table for the
    # caller to print, while long lists are printed here page by page so they
    # don't scroll off-screen.
    # columns: list of (header, kwargs) for add_column; rows: list of string tuples.
    # Returns a Table when it fits on one page, or None when it paginated itself.
    if len(rows) <= page_size:
        table = Table(title=title, header_style="bold cyan")
        for header, kwargs in columns:
            table.add_column(header, **kwargs)
        for row in rows:
            table.add_row(*row)
        return table

    total_pages = (len(rows) + page_size - 1) // page_size
    for page_num, page_rows in enumerate(paginate(rows, page_size), 1):
        table = Table(
            title=f"{title} — page {page_num}/{total_pages}",
            header_style="bold cyan",
        )
        for header, kwargs in columns:
            table.add_column(header, **kwargs)
        for row in page_rows:
            table.add_row(*row)
        console.print(table)

        if page_num < total_pages:
            try:
                choice = input("Press Enter for next page, 'q' to quit: ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                break
            if choice == "q":
                break
    return None


@input_error
def display_all(args, book: AddressBook):
    if not book.data:
        return "No contacts saved."

    columns = [
        ("Name", {"style": "green"}),
        ("Phones", {}),
        ("Birthday", {}),
        ("Email", {}),
        ("Address", {}),
    ]
    rows = []
    for record in book.data.values():
        phones = "; ".join(str(p) for p in record.phones) or "—"
        birthday = str(record.birthday) if record.birthday else "—"
        email = "; ".join(e.value for e in record.emails) or "—"
        address = str(record.address) if record.address else "—"
        rows.append((record.name.value, phones, birthday, email, address))

    return show_paginated_table("Address Book", columns, rows)


@input_error
def display_phone(args, book: AddressBook):
    if not args:
        return "Error: Usage: show-phone [name]"
    name = " ".join(args)
    record = book.find(name)
    if not record:
        raise KeyError(name)

    table = Table(title=f"Phones: {name}", header_style="bold cyan")
    table.add_column("Name", style="green")
    table.add_column("Phones")

    phones = "; ".join(str(p) for p in record.phones) or "—"
    table.add_row(name, phones)

    return table


@input_error
def display_birthday(args, book: AddressBook):
    if not args:
        return "Error: Usage: show-birthday [name]"
    name = " ".join(args)
    record = book.find(name)
    if not record:
        raise KeyError(name)
    # Distinguish "no birthday" from "no such contact" with a clear message
    # instead of a table showing a bare dash.
    if not record.birthday:
        return f"'{name}' has no birthday set."

    table = Table(title=f"Birthday: {name}", header_style="bold cyan")
    table.add_column("Name", style="green")
    table.add_column("Birthday")
    table.add_row(name, str(record.birthday))

    return table


@input_error
def display_birthdays(args, book: AddressBook):
    days = int(args[0]) if args else 7
    # A negative window is meaningless (it would look into the past), so reject it.
    if days < 0:
        return "Error: Number of days cannot be negative."
    upcoming = book.get_upcoming_birthdays(days=days)
    if not upcoming:
        return f"No birthdays in the next {days} days."

    columns = [
        ("Name", {"style": "green"}),
        ("Congratulation Date", {}),
    ]
    rows = [(entry["name"], entry["congratulation_date"]) for entry in upcoming]
    return show_paginated_table(f"Upcoming Birthdays (next {days} days)", columns, rows)


_GREETINGS = [
    "Hi! How can I help you?",
    "Hello! What can I do for you?",
    "Hey there! What do you need?",
    "Greetings! How may I assist you?",
    "Hi! Ready to help. What's up?",
]

_REPEAT_GREETINGS = [
    "We already said hello, but hi again!",
    "Again? Well, hello once more!",
    "You greeted me already, but I don't mind — hello!",
    "Second hello? Why not — hi!",
]

_hello_count = 0


def hello_message(_args, _book):
    # Count greetings so a repeat "hello" gets a playful variant instead of the
    # same line again — a small touch of personality.
    global _hello_count
    _hello_count += 1
    if _hello_count > 1:
        return random.choice(_REPEAT_GREETINGS)
    return random.choice(_GREETINGS)


def show_help(_args, _book):
    # Imported lazily, not at module top: the commands package imports the
    # handlers, so a top-level import here would form a load-time cycle. By the
    # time help is invoked the metadata module is fully available.
    from commands.meta import COMMAND_META, GROUP_ORDER

    table = Table(
        title="Available commands", show_header=True, header_style="bold cyan"
    )
    table.add_column("Command", style="green")
    table.add_column("Description")

    # Group commands by the field/area they serve so related commands sit
    # together instead of in registration order, which reads as a jumble.
    grouped = {}
    for cmd, (args, desc, group) in COMMAND_META.items():
        grouped.setdefault(group, []).append((cmd, args, desc))

    first_section = True
    for group in GROUP_ORDER:
        rows = grouped.get(group)
        if not rows:
            continue
        if not first_section:
            table.add_section()
        first_section = False
        table.add_row(f"[bold yellow]{group}[/bold yellow]", "")

        for cmd, args, desc in rows:
            # "exit" is folded into the "close" row since they're aliases.
            if cmd == "exit":
                continue
            label = "close / exit" if cmd == "close" else cmd
            args_escaped = args.replace("[", "\\[")
            table.add_row(f"  {label} {args_escaped}".rstrip(), desc)

    return table


def command_suggestions_table(names):
    # After a typo we show the likely commands as a help-style table (syntax +
    # description) rather than a numbered picker, so the user reads the correct
    # usage and retypes it — picking a guess would run it with the wrong args.
    from commands.meta import COMMAND_META

    table = Table(
        title="Did you mean one of these?", show_header=True, header_style="bold cyan"
    )
    table.add_column("Command", style="green")
    table.add_column("Description")
    for name in names:
        meta = COMMAND_META.get(name)
        if not meta:
            continue
        args, desc, _group = meta
        args_escaped = args.replace("[", "\\[")
        table.add_row(f"{name} {args_escaped}".strip(), desc)
    return table
