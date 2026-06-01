"""
End-to-end happy-path scenario.

Simulates a complete user session against the real handlers and exercises
*every* user-facing action except the destructive `dump` wipe:
empty book → add contacts with all fields → edit/delete across every command
group → export → save → reload. State is asserted at every step, so a failure
pinpoints exactly where the lifecycle breaks.
"""
import json
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from rich.table import Table

from models.address_book import AddressBook
from models.record import Record
from commands.commands import commands as COMMANDS
from commands.meta import COMMAND_META
from handlers.contact_handlers import (
    add_contact, delete_contact, find_contact, all_with_notes,
)
from handlers.phone_handlers import change_contact, add_phone, remove_phone
from handlers.email_handlers import add_email, edit_email, delete_email
from handlers.birthday_handlers import add_birthday, edit_birthday, delete_birthday
from handlers.address_handlers import add_address, edit_address, delete_address
from handlers.display import (
    display_all, display_birthdays, display_phone, display_birthday,
    show_help, hello_message,
)
from handlers.note_handlers import (
    add_note, edit_note, delete_note, show_notes, show_all_notes,
    find_notes, add_tag, edit_tag, delete_tag, find_by_tag, sort_by_tags,
)
from handlers.export_handlers import export_book, save_book, dump_book
from handlers.utils import save_data, load_data


class TestHappyPath:
    """One linear scenario covering the full lifecycle in a single test."""

    def test_full_session(self, tmp_path):

        # ------------------------------------------------------------------
        # 1. App starts: empty address book
        # ------------------------------------------------------------------
        book = AddressBook()
        assert len(book.data) == 0

        # ------------------------------------------------------------------
        # 2. Add Alice (email + birthday) and Bob (phone only) interactively.
        #    Prompts: name, phone, email, birthday, "add address?" (n), note
        # ------------------------------------------------------------------
        with patch("builtins.input", side_effect=[
            "Alice", "1234567890", "alice@example.com", "15.06.1990", "n", ""
        ]):
            assert "Error" not in add_contact([], book)
        assert book.find("Alice") is not None

        with patch("builtins.input", side_effect=["Bob", "0987654321", "", "", "n", ""]):
            assert "Error" not in add_contact([], book)
        assert book.find("Bob") is not None
        assert len(book.data) == 2

        # ------------------------------------------------------------------
        # 3. Alice's optional fields persisted immediately
        # ------------------------------------------------------------------
        alice = book.find("Alice")
        assert alice.find_email("alice@example.com") is not None
        assert str(alice.birthday) == "15.06.1990"
        assert alice.find_phone("1234567890") is not None

        # ------------------------------------------------------------------
        # 4. edit-phone: replace Alice's only phone (interactive new number)
        # ------------------------------------------------------------------
        with patch("builtins.input", side_effect=["1111111111"]):
            assert "Error" not in change_contact(["Alice"], book)
        assert alice.find_phone("1111111111") is not None
        assert alice.find_phone("1234567890") is None

        # ------------------------------------------------------------------
        # 5. add-phone then delete-phone (inline)
        # ------------------------------------------------------------------
        add_phone(["Alice", "2222222222"], book)
        assert alice.find_phone("2222222222") is not None
        remove_phone(["Alice", "2222222222"], book)
        assert alice.find_phone("2222222222") is None

        # ------------------------------------------------------------------
        # 6. add-birthday and add-email to Bob (inline)
        # ------------------------------------------------------------------
        add_birthday(["Bob", "20.03.1985"], book)
        assert str(book.find("Bob").birthday) == "20.03.1985"
        add_email(["Bob", "bob@example.com"], book)
        assert book.find("Bob").find_email("bob@example.com") is not None

        # ------------------------------------------------------------------
        # 7. show-birthday / phone display tables (values verified in steps 3 & 6)
        # ------------------------------------------------------------------
        assert isinstance(display_birthday(["Alice"], book), Table)
        assert isinstance(display_birthday(["Bob"], book), Table)
        assert isinstance(display_phone(["Alice"], book), Table)

        # ------------------------------------------------------------------
        # 8. find-contact — partial name (case-insensitive) and by phone
        # ------------------------------------------------------------------
        assert isinstance(find_contact(["alice"], book), Table)
        assert isinstance(find_contact(["1111"], book), Table)
        assert "No contacts found" in find_contact(["zzz"], book)

        # ------------------------------------------------------------------
        # 9. add-note to both contacts (IDs globally unique)
        # ------------------------------------------------------------------
        add_note(["Alice", "Meeting", "on", "Monday"], book)
        add_note(["Alice", "Call", "the", "dentist"], book)
        add_note(["Bob", "Buy", "groceries"], book)

        # Alice holds multiple notes simultaneously (exercises multi-note display).
        assert len(alice.notes) == 2

        all_ids = [n.id for r in book.data.values() for n in r.notes]
        assert len(all_ids) == len(set(all_ids)), "Note IDs must be globally unique"

        alice_note_1_id = alice.notes[0].id
        alice_note_2_id = alice.notes[1].id
        bob_note_id = book.find("Bob").notes[0].id

        # ------------------------------------------------------------------
        # 10. add-tag to Alice's first note and Bob's note (by note id)
        # ------------------------------------------------------------------
        with patch("builtins.input", side_effect=["work"]):
            assert "work" in add_tag([str(alice_note_1_id)], book)
        assert "work" in alice.notes[0].tags

        with patch("builtins.input", side_effect=["personal"]):
            add_tag([str(bob_note_id)], book)
        assert "personal" in book.find("Bob").notes[0].tags

        # ------------------------------------------------------------------
        # 11. find-notes (text + exact-tag search)
        # ------------------------------------------------------------------
        assert isinstance(find_notes(["meeting"], book), Table)
        assert isinstance(find_notes(["work"], book), Table)      # tag exact-match
        assert "No notes found" in find_notes(["xyznotexist"], book)

        # ------------------------------------------------------------------
        # 12. find-by-tag and sort-by-tags
        # ------------------------------------------------------------------
        assert isinstance(find_by_tag(["work"], book), Table)
        assert isinstance(find_by_tag(["personal"], book), Table)
        assert "No notes found" in find_by_tag(["nonexistent"], book)
        assert isinstance(sort_by_tags([], book), Table)

        # ------------------------------------------------------------------
        # 13. Aggregate views
        # ------------------------------------------------------------------
        assert isinstance(display_all([], book), Table)
        assert isinstance(show_notes(["Alice"], book), Table)
        assert isinstance(show_all_notes([], book), Table)
        assert isinstance(all_with_notes([], book), Table)

        # ------------------------------------------------------------------
        # 14. upcoming-birthdays (must not crash regardless of today's date)
        # ------------------------------------------------------------------
        display_birthdays([], book)           # default 7-day window
        display_birthdays(["365"], book)      # one-year window

        imminent = AddressBook()
        r = Record("Soon")
        r.add_phone("5555555555")
        # Past-year birthday with tomorrow's month/day — Birthday() rejects future
        # dates, but get_upcoming_birthdays compares only month/day.
        tomorrow = date.today() + timedelta(days=1)
        r.add_birthday(date(2000, tomorrow.month, tomorrow.day).strftime("%d.%m.%Y"))
        imminent.add_record(r)
        assert isinstance(display_birthdays([], imminent), Table)

        # ------------------------------------------------------------------
        # 15. edit-note: update Alice's first note — tags must survive
        # ------------------------------------------------------------------
        with patch("builtins.input", side_effect=["Meeting moved to Friday"]):
            assert "updated" in edit_note([str(alice_note_1_id)], book)
        assert alice.notes[0].value == "Meeting moved to Friday"
        assert "work" in alice.notes[0].tags, "edit-note must preserve tags"

        # ------------------------------------------------------------------
        # 16. delete-note: remove Alice's second note (by id)
        # ------------------------------------------------------------------
        assert "deleted" in delete_note([str(alice_note_2_id)], book)
        assert len(alice.notes) == 1
        assert alice.notes[0].id == alice_note_1_id

        # ------------------------------------------------------------------
        # 17. Email lifecycle on Bob: add a 2nd email, edit it, delete it.
        #     (Bob already has bob@example.com from step 6.)
        # ------------------------------------------------------------------
        bob = book.find("Bob")
        add_email(["Bob", "bob.work@example.com"], book)
        assert len(bob.emails) == 2
        with patch("builtins.input", side_effect=["1", "bob.new@example.com"]):
            edit_email(["Bob"], book)              # choose entry [1], set new value
        assert bob.find_email("bob.new@example.com") is not None
        delete_email(["Bob", "bob.new@example.com"], book)
        assert bob.find_email("bob.new@example.com") is None
        assert len(bob.emails) == 1

        # ------------------------------------------------------------------
        # 18. Birthday edit then delete on Bob (set to 20.03.1985 in step 6).
        # ------------------------------------------------------------------
        edit_birthday(["Bob", "21.04.1986"], book)
        assert str(bob.birthday) == "21.04.1986"
        delete_birthday(["Bob"], book)
        assert bob.birthday is None

        # ------------------------------------------------------------------
        # 19. Address lifecycle on Alice: guided add, edit, delete.
        # ------------------------------------------------------------------
        # add: country, city, street, house, apt(skip), zip(skip)
        with patch("builtins.input", side_effect=["Ukraine", "Kyiv", "Main St", "1", "", ""]):
            assert "added" in add_address(["Alice"], book).lower()
        assert "Ukraine" in str(alice.address)
        with patch("builtins.input", side_effect=["Poland", "Warsaw", "Rynek", "5", "", ""]):
            edit_address(["Alice"], book)
        assert "Poland" in str(alice.address)
        delete_address(["Alice"], book)
        assert alice.address is None

        # ------------------------------------------------------------------
        # 20. Multiple phones on Alice: two coexist, both render with the mask,
        #     and the multi-value flows (edit choose-among-several, delete all)
        #     are exercised. Alice currently has the single phone 1111111111.
        # ------------------------------------------------------------------
        add_phone(["Alice", "0991234567"], book)
        assert len(alice.phones) == 2, "both phones must coexist on the contact"
        assert alice.find_phone("1111111111") is not None
        assert alice.find_phone("0991234567") is not None

        # Both numbers, stored as bare digits, must render in +38(0XX)... form.
        from io import StringIO
        from rich.console import Console
        buf = StringIO()
        Console(file=buf, width=200, force_terminal=False).print(find_contact(["Alice"], book))
        rendered = buf.getvalue()
        assert "+38(111)111-11-11" in rendered, "first phone must render with the mask"
        assert "+38(099)123-45-67" in rendered, "second phone must render with the mask"
        assert "0991234567" not in rendered, "raw digits must not leak into the table"

        # edit-phone with several present: pick entry [1] and replace it.
        with patch("builtins.input", side_effect=["1", "3333333333"]):
            change_contact(["Alice"], book)
        assert alice.find_phone("3333333333") is not None
        assert len(alice.phones) == 2

        # delete-phone with no number given + several present: choose "all".
        with patch("builtins.input", side_effect=["all"]):
            remove_phone(["Alice"], book)
        assert alice.phones == []

        # Restore the single phone 1111111111 so the reload round-trip (step 25)
        # still finds it.
        add_phone(["Alice", "1111111111"], book)
        assert alice.find_phone("1111111111") is not None
        assert len(alice.phones) == 1

        # ------------------------------------------------------------------
        # 21. Tag lifecycle on Alice's note: replace the whole list, then delete.
        #     (Note currently carries the "work" tag from step 10.)
        # ------------------------------------------------------------------
        with patch("builtins.input", side_effect=["work, urgent"]):
            edit_tag([str(alice_note_1_id)], book)
        assert alice.notes[0].tags == ["work", "urgent"]
        with patch("builtins.input", side_effect=["all"]):
            delete_tag([str(alice_note_1_id)], book)
        assert alice.notes[0].tags == []
        # Re-add "work" so the persistence round-trip (step 24) still asserts it.
        with patch("builtins.input", side_effect=["work"]):
            add_tag([str(alice_note_1_id)], book)
        assert alice.notes[0].tags == ["work"]

        # ------------------------------------------------------------------
        # 22. Stateless/help commands: hello, help, and every command in the
        #     registry is documented (help/completion stay in sync).
        # ------------------------------------------------------------------
        assert isinstance(hello_message([], book), str) and hello_message([], book)
        assert isinstance(show_help([], book), Table)
        assert set(COMMANDS) - set(COMMAND_META) == set(), "every command needs meta"
        # `dump` exists but is intentionally NOT executed here (destructive wipe);
        # we only assert it's registered and documented.
        assert "dump" in COMMANDS and "dump" in COMMAND_META

        # ------------------------------------------------------------------
        # 23. export-book to JSON and CSV, plus the on-demand `save` command.
        # ------------------------------------------------------------------
        json_path = str(tmp_path / "export.json")
        assert "exported" in export_book(["json", json_path], book).lower()
        exported = json.loads(Path(json_path).read_text(encoding="utf-8"))
        assert any(r["name"] == "Alice" for r in exported)
        csv_path = str(tmp_path / "export.csv")
        export_book(["csv", csv_path], book)
        assert Path(csv_path).exists()
        # `save` persists to the default path; patch save_data so the real file is
        # never touched and we just confirm it was invoked with the live book.
        with patch("handlers.export_handlers.save_data") as mock_save:
            assert "saved" in save_book([], book).lower()
            mock_save.assert_called_once_with(book)

        # ------------------------------------------------------------------
        # 24. delete-contact: remove Bob entirely
        # ------------------------------------------------------------------
        assert "deleted" in delete_contact(["Bob"], book)
        assert book.find("Bob") is None
        assert len(book.data) == 1

        # ------------------------------------------------------------------
        # 25. Persist and reload — full state must survive a round-trip
        # ------------------------------------------------------------------
        save_path = str(tmp_path / "addressbook.pkl")
        save_data(book, save_path)

        reloaded_alice = load_data(save_path).find("Alice")
        assert reloaded_alice is not None
        assert reloaded_alice.find_phone("1111111111") is not None
        assert reloaded_alice.find_email("alice@example.com") is not None
        assert str(reloaded_alice.birthday) == "15.06.1990"
        assert len(reloaded_alice.notes) == 1
        assert reloaded_alice.notes[0].value == "Meeting moved to Friday"
        assert reloaded_alice.notes[0].tags == ["work"]
        assert load_data(save_path).find("Bob") is None
