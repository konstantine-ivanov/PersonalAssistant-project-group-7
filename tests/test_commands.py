"""
Model and handler tests, organised by command group.

Covers: Record model, AddressBook model, every registered command handler
(contacts / phones / emails / birthdays / addresses / notes / tags / display /
export), input parsing, persistence, and the command-metadata contract.

Interactive handlers read via input(); those prompts are mocked with
unittest.mock.patch("builtins.input", side_effect=[...]).
"""
import csv
import json
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from rich.table import Table
from prompt_toolkit.document import Document

from models.record import Record
from models.address_book import AddressBook
from commands.meta import COMMAND_META, GROUP_ORDER
from commands.hints import CommandCompleter
from commands.commands import commands as COMMANDS

from handlers.contact_handlers import (
    add_contact, delete_contact, find_contact, all_with_notes, _full_contact_rows,
    _SECRET_IDENTITIES, _unmask_identity,
)
from handlers.phone_handlers import change_contact, add_phone, remove_phone
from handlers.email_handlers import add_email, edit_email, delete_email
from handlers.birthday_handlers import add_birthday, edit_birthday, delete_birthday
from handlers.address_handlers import add_address, edit_address, delete_address
from handlers.display import (
    display_all, display_phone, display_birthday, display_birthdays,
    show_help, hello_message,
)
from handlers.note_handlers import (
    add_note, edit_note, delete_note, show_notes, show_all_notes,
    find_notes, add_tag, edit_tag, delete_tag,
    find_by_tag, sort_by_tags,
)
from handlers.export_handlers import (
    export_book, save_book, dump_book, DUMP_CONFIRMATION,
    _record_to_dict, _resolve_path, _export_json, _export_csv,
)
from handlers.utils import parse_input, save_data, load_data, get_validated_command


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_book(*contacts):
    """Build an AddressBook from (name, phone) pairs (one phone each)."""
    book = AddressBook()
    for name, phone in contacts:
        r = Record(name)
        r.add_phone(phone)
        book.add_record(r)
    return book


def _record(name, *phones):
    """A standalone Record with zero or more phones."""
    r = Record(name)
    for p in phones:
        r.add_phone(p)
    return r


def _birthday_in(offset_days, year=2000):
    """A DD.MM.YYYY birthday whose month/day is `offset_days` from today, in a
    past year — Birthday() rejects future dates, but get_upcoming_birthdays only
    compares month/day, so a past-year date still lands in the upcoming window."""
    target = date.today() + timedelta(days=offset_days)
    return date(year, target.month, target.day).strftime("%d.%m.%Y")


# =============================================================================
# Record model
# =============================================================================

class TestRecord:

    def test_add_and_find_phone(self):
        r = _record("Alice", "1234567890")
        assert r.find_phone("1234567890") is not None

    def test_multiple_phones_stored(self):
        r = _record("Alice", "1234567890", "0987654321")
        assert len(r.phones) == 2

    def test_remove_phone(self):
        r = _record("Alice", "1234567890")
        r.remove_phone("1234567890")
        assert r.find_phone("1234567890") is None

    def test_remove_nonexistent_phone_raises(self):
        with pytest.raises(ValueError):
            _record("Alice").remove_phone("1234567890")

    def test_edit_phone(self):
        r = _record("Alice", "1234567890")
        r.edit_phone("1234567890", "0987654321")
        assert r.find_phone("0987654321") is not None
        assert r.find_phone("1234567890") is None

    def test_edit_nonexistent_phone_raises(self):
        with pytest.raises(ValueError):
            _record("Alice").edit_phone("1234567890", "0987654321")

    def test_find_phone_missing_returns_none(self):
        assert _record("Alice").find_phone("1234567890") is None

    # --- birthday (single-valued) ---

    def test_add_birthday(self):
        r = _record("Alice")
        r.add_birthday("01.01.1990")
        assert str(r.birthday) == "01.01.1990"

    def test_remove_birthday(self):
        r = _record("Alice")
        r.add_birthday("01.01.1990")
        r.remove_birthday()
        assert r.birthday is None

    # --- emails (multi-valued, mirror phones) ---

    def test_add_and_find_email(self):
        r = _record("Alice")
        r.add_email("alice@example.com")
        assert r.find_email("alice@example.com") is not None

    def test_multiple_emails_stored(self):
        r = _record("Alice")
        r.add_email("a@example.com")
        r.add_email("b@example.com")
        assert len(r.emails) == 2

    def test_remove_email(self):
        r = _record("Alice")
        r.add_email("alice@example.com")
        r.remove_email("alice@example.com")
        assert r.find_email("alice@example.com") is None

    def test_remove_nonexistent_email_raises(self):
        with pytest.raises(ValueError):
            _record("Alice").remove_email("x@example.com")

    def test_edit_email(self):
        r = _record("Alice")
        r.add_email("old@example.com")
        r.edit_email("old@example.com", "new@example.com")
        assert r.find_email("new@example.com") is not None
        assert r.find_email("old@example.com") is None

    # --- address (single-valued) ---

    def test_add_address(self):
        r = _record("Alice")
        r.add_address("Kyiv, Main St 1")
        assert str(r.address) == "Kyiv, Main St 1"

    def test_remove_address(self):
        r = _record("Alice")
        r.add_address("Kyiv")
        r.remove_address()
        assert r.address is None

    # --- notes ---

    def test_add_note(self):
        r = _record("Alice")
        r.add_note("Buy milk", 1)
        assert r.notes[0].value == "Buy milk"

    def test_delete_note(self):
        r = _record("Alice")
        r.add_note("text", 1)
        r.delete_note(1)
        assert r.notes == []

    def test_delete_note_wrong_id_raises(self):
        with pytest.raises(IndexError):
            _record("Alice").delete_note(99)

    # --- __str__ ---

    def test_str_includes_name_and_phone(self):
        r = _record("Alice", "1234567890")
        s = str(r)
        assert "Alice" in s
        assert "1234567890" in s

    def test_str_no_phones_shows_label(self):
        assert "No phones" in str(_record("Alice"))


# =============================================================================
# AddressBook model
# =============================================================================

class TestAddressBook:

    def test_add_and_find_record(self):
        book = AddressBook()
        r = _record("Bob")
        book.add_record(r)
        assert book.find("Bob") is r

    def test_find_is_case_insensitive(self):
        book = _make_book(("Bob", "1234567890"))
        assert book.find("bob") is book.find("BOB")

    def test_find_missing_returns_none(self):
        assert AddressBook().find("Nobody") is None

    def test_delete_record(self):
        book = _make_book(("Alice", "1234567890"))
        book.delete("Alice")
        assert book.find("Alice") is None

    def test_delete_is_case_insensitive(self):
        book = _make_book(("Alice", "1234567890"))
        book.delete("alice")
        assert book.find("Alice") is None

    def test_delete_missing_is_silent(self):
        AddressBook().delete("Nobody")  # must not raise

    def test_multiple_records_stored(self):
        book = _make_book(("Alice", "1111111111"), ("Bob", "2222222222"))
        assert len(book.data) == 2

    # --- internal keying: records are stored under a lower-cased key for O(1)
    #     case-insensitive lookup, while record.name keeps its display casing ---

    def test_record_keyed_by_lowercase_name(self):
        book = _make_book(("Alice Johnson", "1234567890"))
        assert "alice johnson" in book.data
        assert book.data["alice johnson"].name.value == "Alice Johnson"

    def test_find_preserves_display_casing(self):
        book = _make_book(("Alice Johnson", "1234567890"))
        assert book.find("ALICE JOHNSON").name.value == "Alice Johnson"

    def test_key_helper_lowercases(self):
        assert AddressBook._key("O'Brien") == "o'brien"

    # --- get_upcoming_birthdays ---

    def _book_with_birthday(self, offset_days):
        book = AddressBook()
        r = _record("Alice")
        r.add_birthday(_birthday_in(offset_days))
        book.add_record(r)
        return book

    def test_birthday_inside_default_window_included(self):
        book = self._book_with_birthday(3)
        assert any(e["name"] == "Alice" for e in book.get_upcoming_birthdays())

    def test_birthday_outside_window_excluded(self):
        book = self._book_with_birthday(10)
        assert book.get_upcoming_birthdays() == []

    def test_birthday_today_included(self):
        book = self._book_with_birthday(0)
        assert any(e["name"] == "Alice" for e in book.get_upcoming_birthdays())

    def test_no_birthday_excluded(self):
        assert _make_book(("Alice", "1234567890")).get_upcoming_birthdays() == []

    def test_custom_window(self):
        book = self._book_with_birthday(14)
        assert book.get_upcoming_birthdays(days=7) == []
        assert book.get_upcoming_birthdays(days=14)

    def test_feb29_birthday_does_not_crash_in_non_leap_year(self, monkeypatch):
        # Pin "today" to a non-leap year so Feb 29 has no direct counterpart.
        import models.address_book as ab

        class _FixedDate(date):
            @classmethod
            def today(cls):
                return cls(2025, 1, 10)

        monkeypatch.setattr(ab, "date", _FixedDate)
        book = AddressBook()
        r = _record("Leap")
        r.add_birthday("29.02.2000")
        book.add_record(r)
        result = book.get_upcoming_birthdays(days=400)  # must not raise
        assert result[0]["name"] == "Leap"

    def test_saturday_birthday_shifted_to_monday(self):
        today = date.today()
        days_to_sat = (5 - today.weekday()) % 7 or 7
        if days_to_sat > 7:
            pytest.skip("Next Saturday falls outside the 7-day window today.")
        saturday = today + timedelta(days=days_to_sat)
        book = AddressBook()
        r = _record("Alice")
        # Past-year birthday with Saturday's month/day (a current-year date would
        # be in the future and rejected by Birthday()).
        r.add_birthday(date(2000, saturday.month, saturday.day).strftime("%d.%m.%Y"))
        book.add_record(r)
        result = book.get_upcoming_birthdays()
        expected = (saturday + timedelta(days=2)).strftime("%d.%m.%Y")
        assert result[0]["congratulation_date"] == expected


# =============================================================================
# add command  (quick one-liner + guided interactive entry)
# =============================================================================

class TestAddContactQuick:

    def test_name_only_creates_contact(self):
        book = AddressBook()
        result = add_contact(["Alice"], book)
        assert book.find("Alice") is not None
        assert "created" in result

    def test_name_and_phone_creates_contact(self):
        book = AddressBook()
        result = add_contact(["John", "1234567890"], book)
        assert book.find("John").find_phone("1234567890") is not None
        assert "1234567890" in result

    def test_multi_word_name_title_cased(self):
        book = AddressBook()
        add_contact(["mary", "jane"], book)
        assert book.find("Mary Jane") is not None

    def test_existing_name_rejected(self):
        book = _make_book(("Alice", "1234567890"))
        assert "already exists" in add_contact(["Alice"], book)

    def test_invalid_name_rejected(self):
        book = AddressBook()
        assert "Error" in add_contact(["Alice123"], book)
        assert book.find("Alice123") is None


# =============================================================================
# Easter egg: superhero secret-identity unmasking on quick-add (hidden feature)
# =============================================================================

class TestSecretIdentityEasterEgg:

    def test_alias_filed_under_real_name(self):
        book = AddressBook()
        result = add_contact(["batman"], book)
        # Stored under the real name, not the alias.
        assert book.find("Bruce Wayne") is not None
        assert book.find("Batman") is None
        assert "Bruce Wayne" in result

    def test_message_mentions_anonymization(self):
        book = AddressBook()
        result = add_contact(["superman"], book)
        assert "anonymization" in result.lower()
        assert "Clark Kent" in result

    def test_alias_is_case_insensitive(self):
        book = AddressBook()
        add_contact(["SPIDERMAN"], book)
        assert book.find("Peter Parker") is not None

    def test_multi_word_alias_resolves(self):
        # "iron man" (two tokens) must unmask the same as "ironman".
        book = AddressBook()
        add_contact(["iron", "man"], book)
        assert book.find("Tony Stark") is not None

    def test_alias_with_phone_keeps_phone(self):
        book = AddressBook()
        result = add_contact(["batman", "0991234567"], book)
        assert book.find("Bruce Wayne").find_phone("0991234567") is not None
        assert "0991234567" in result

    def test_alias_recorded_as_aka_note(self):
        # The hero alias is filed as an "aka <alias>" note on the real-name contact.
        book = AddressBook()
        add_contact(["batman"], book)
        notes = book.find("Bruce Wayne").notes
        assert [n.value for n in notes] == ["aka Batman"]

    def test_multi_word_alias_aka_note_uses_typed_name(self):
        book = AddressBook()
        add_contact(["iron", "man"], book)
        assert book.find("Tony Stark").notes[0].value == "aka Iron Man"

    def test_real_name_has_no_aka_note(self):
        # A normal contact gets no easter-egg note.
        book = AddressBook()
        add_contact(["Alice"], book)
        assert book.find("Alice").notes == []

    def test_real_name_has_no_easter_egg_note(self):
        # A normal contact must not get the unmasking note appended.
        book = AddressBook()
        result = add_contact(["Alice"], book)
        assert "anonymization" not in result.lower()

    def test_unmask_helper_space_and_case_insensitive(self):
        assert _unmask_identity("Wonder Woman") == "Diana Prince"
        assert _unmask_identity("WONDERWOMAN") == "Diana Prince"
        assert _unmask_identity("Alice") is None

    def test_every_real_name_passes_name_validation(self):
        # Each mapped real name must itself be a valid Name (so the egg can't
        # produce an uncreatable contact). Black Panther -> T'Challa relies on
        # the apostrophe being allowed in names.
        from models import Record
        for real_name in _SECRET_IDENTITIES.values():
            Record(real_name)  # raises ValueError if invalid


class TestAddContactInteractive:

    def test_new_contact_created(self):
        book = AddressBook()
        # name, phone, email(skip), birthday(skip), address? n, note(skip)
        with patch("builtins.input", side_effect=["Alice", "1234567890", "", "", "n", ""]):
            result = add_contact([], book)
        assert book.find("Alice") is not None
        assert "Error" not in result

    def test_new_contact_with_optional_fields(self):
        book = AddressBook()
        inputs = ["John", "0987654321", "john@example.com", "15.06.1990", "n", ""]
        with patch("builtins.input", side_effect=inputs):
            add_contact([], book)
        r = book.find("John")
        assert r.find_email("john@example.com") is not None
        assert str(r.birthday) == "15.06.1990"

    def test_multi_word_name_accepted(self):
        book = AddressBook()
        with patch("builtins.input", side_effect=["mary jane", "1234567890", "", "", "n", ""]):
            add_contact([], book)
        assert book.find("Mary Jane") is not None

    def test_existing_contact_add_phone(self):
        book = _make_book(("Alice", "1234567890"))
        # name, phone, choice=1 (add new), email, birthday, address? n, note
        with patch("builtins.input", side_effect=["Alice", "0987654321", "1", "", "", "n", ""]):
            add_contact([], book)
        assert book.find("Alice").find_phone("0987654321") is not None

    def test_existing_contact_cancel(self):
        book = _make_book(("Alice", "1234567890"))
        with patch("builtins.input", side_effect=["Alice", "0987654321", "3"]):
            result = add_contact([], book)
        assert "cancel" in result.lower()
        assert book.find("Alice").find_phone("0987654321") is None

    def test_mandatory_name_cancel_aborts(self):
        book = AddressBook()
        with patch("builtins.input", side_effect=["cancel"]):
            result = add_contact([], book)
        assert "cancel" in result.lower()
        assert len(book.data) == 0

    def test_mandatory_phone_cancel_aborts(self):
        book = AddressBook()
        with patch("builtins.input", side_effect=["Alice", "cancel"]):
            result = add_contact([], book)
        assert "cancel" in result.lower()
        assert book.find("Alice") is None


# =============================================================================
# edit-phone / add-phone / delete-phone
# =============================================================================

class TestPhoneCommands:

    def test_edit_phone_single(self):
        book = _make_book(("Bob", "1234567890"))
        with patch("builtins.input", side_effect=["0987654321"]):
            result = change_contact(["Bob"], book)
        assert "0987654321" in result
        assert book.find("Bob").find_phone("0987654321") is not None

    def test_edit_phone_reprompts_on_invalid_then_accepts(self):
        book = _make_book(("Bob", "1234567890"))
        with patch("builtins.input", side_effect=["bad", "0987654321"]):
            change_contact(["Bob"], book)
        assert book.find("Bob").find_phone("0987654321") is not None

    def test_edit_phone_choose_among_several(self):
        book = AddressBook()
        book.add_record(_record("Bob", "1111111111", "2222222222"))
        # choose entry [1], then enter the new number
        with patch("builtins.input", side_effect=["1", "3333333333"]):
            change_contact(["Bob"], book)
        assert book.find("Bob").find_phone("3333333333") is not None

    def test_edit_phone_cancel(self):
        book = _make_book(("Bob", "1234567890"))
        with patch("builtins.input", side_effect=["cancel"]):
            assert "cancel" in change_contact(["Bob"], book).lower()
        assert book.find("Bob").find_phone("1234567890") is not None

    def test_add_phone_prompted_cancel(self):
        book = _make_book(("Alice", "1234567890"))
        with patch("builtins.input", side_effect=["cancel"]):
            assert "cancel" in add_phone(["Alice"], book).lower()
        assert len(book.find("Alice").phones) == 1

    def test_edit_phone_contact_not_found(self):
        assert "Error" in change_contact(["Ghost"], AddressBook())

    def test_edit_phone_no_phones(self):
        book = AddressBook()
        book.add_record(_record("Bob"))
        assert "Error" in change_contact(["Bob"], book)

    def test_add_phone_inline(self):
        book = _make_book(("Alice", "1234567890"))
        result = add_phone(["Alice", "0987654321"], book)
        assert book.find("Alice").find_phone("0987654321") is not None
        assert "0987654321" in result

    def test_add_phone_prompted(self):
        book = _make_book(("Alice", "1234567890"))
        with patch("builtins.input", side_effect=["0987654321"]):
            add_phone(["Alice"], book)
        assert book.find("Alice").find_phone("0987654321") is not None

    def test_add_phone_invalid_inline(self):
        book = _make_book(("Alice", "1234567890"))
        assert "Error" in add_phone(["Alice", "123"], book)

    def test_add_phone_contact_not_found(self):
        assert "Error" in add_phone(["Ghost", "1234567890"], AddressBook())

    def test_remove_phone_inline(self):
        book = _make_book(("Dave", "1234567890"))
        result = remove_phone(["Dave", "1234567890"], book)
        assert "removed" in result.lower()
        assert book.find("Dave").find_phone("1234567890") is None

    def test_remove_phone_by_name_single(self):
        book = _make_book(("Dave", "1234567890"))
        result = remove_phone(["Dave"], book)
        assert "1" in result
        assert book.find("Dave").phones == []

    def test_remove_phone_choose_all(self):
        book = AddressBook()
        book.add_record(_record("Dave", "1111111111", "2222222222"))
        with patch("builtins.input", side_effect=["all"]):
            remove_phone(["Dave"], book)
        assert book.find("Dave").phones == []

    def test_remove_phone_contact_not_found(self):
        assert "Error" in remove_phone(["Ghost", "1234567890"], AddressBook())

    def test_remove_phone_wrong_number(self):
        book = _make_book(("Dave", "1234567890"))
        assert "Error" in remove_phone(["Dave", "0000000000"], book)

    def test_remove_phone_no_phones(self):
        book = AddressBook()
        book.add_record(_record("Dave"))
        assert "Error" in remove_phone(["Dave"], book)


# =============================================================================
# add-email / edit-email / delete-email
# =============================================================================

class TestEmailCommands:

    def _book_with_email(self, *emails):
        book = _make_book(("Eve", "1234567890"))
        for e in emails:
            book.find("Eve").add_email(e)
        return book

    def test_add_email_inline(self):
        book = _make_book(("Eve", "1234567890"))
        result = add_email(["Eve", "eve@example.com"], book)
        assert "eve@example.com" in result
        assert book.find("Eve").find_email("eve@example.com") is not None

    def test_add_email_prompted(self):
        book = _make_book(("Eve", "1234567890"))
        with patch("builtins.input", side_effect=["eve@example.com"]):
            add_email(["Eve"], book)
        assert book.find("Eve").find_email("eve@example.com") is not None

    def test_add_email_duplicate_rejected(self):
        book = self._book_with_email("eve@example.com")
        assert "already has email" in add_email(["Eve", "eve@example.com"], book)

    def test_add_email_invalid_format(self):
        book = _make_book(("Eve", "1234567890"))
        assert "Error" in add_email(["Eve", "not-an-email"], book)

    def test_add_email_contact_not_found(self):
        assert "Error" in add_email(["Ghost", "x@example.com"], AddressBook())

    def test_add_email_prompted_cancel(self):
        book = _make_book(("Eve", "1234567890"))
        with patch("builtins.input", side_effect=["cancel"]):
            assert "cancel" in add_email(["Eve"], book).lower()
        assert book.find("Eve").emails == []

    def test_edit_email_cancel(self):
        book = self._book_with_email("old@example.com")
        with patch("builtins.input", side_effect=["cancel"]):
            assert "cancel" in edit_email(["Eve"], book).lower()
        assert book.find("Eve").find_email("old@example.com") is not None

    def test_edit_email_single(self):
        book = self._book_with_email("old@example.com")
        with patch("builtins.input", side_effect=["new@example.com"]):
            edit_email(["Eve"], book)
        assert book.find("Eve").find_email("new@example.com") is not None

    def test_edit_email_choose_among_several(self):
        book = self._book_with_email("a@example.com", "b@example.com")
        with patch("builtins.input", side_effect=["1", "new@example.com"]):
            edit_email(["Eve"], book)
        assert book.find("Eve").find_email("new@example.com") is not None

    def test_edit_email_no_emails(self):
        book = _make_book(("Eve", "1234567890"))
        assert "Error" in edit_email(["Eve"], book)

    def test_delete_email_inline(self):
        book = self._book_with_email("eve@example.com")
        result = delete_email(["Eve", "eve@example.com"], book)
        assert "removed" in result.lower()
        assert book.find("Eve").emails == []

    def test_delete_email_by_name_single(self):
        book = self._book_with_email("eve@example.com")
        delete_email(["Eve"], book)
        assert book.find("Eve").emails == []

    def test_delete_email_choose_all(self):
        book = self._book_with_email("a@example.com", "b@example.com")
        with patch("builtins.input", side_effect=["all"]):
            delete_email(["Eve"], book)
        assert book.find("Eve").emails == []

    def test_delete_email_no_emails(self):
        book = _make_book(("Eve", "1234567890"))
        assert "Error" in delete_email(["Eve"], book)


# =============================================================================
# add-birthday / edit-birthday / delete-birthday / show-birthday / upcoming
# =============================================================================

class TestBirthdayCommands:

    def test_add_birthday_inline(self):
        book = _make_book(("Frank", "1234567890"))
        result = add_birthday(["Frank", "01.01.1990"], book)
        assert "01.01.1990" in result
        assert str(book.find("Frank").birthday) == "01.01.1990"

    def test_add_birthday_prompted(self):
        book = _make_book(("Frank", "1234567890"))
        with patch("builtins.input", side_effect=["01.01.1990"]):
            add_birthday(["Frank"], book)
        assert str(book.find("Frank").birthday) == "01.01.1990"

    def test_add_birthday_refuses_to_overwrite(self):
        book = _make_book(("Frank", "1234567890"))
        add_birthday(["Frank", "01.01.1990"], book)
        assert "already has a birthday" in add_birthday(["Frank", "20.07.1991"], book)
        assert str(book.find("Frank").birthday) == "01.01.1990"

    def test_add_birthday_invalid_format(self):
        book = _make_book(("Frank", "1234567890"))
        assert "Error" in add_birthday(["Frank", "1990-01-01"], book)

    def test_add_birthday_impossible_date(self):
        book = _make_book(("Frank", "1234567890"))
        assert "Error" in add_birthday(["Frank", "30.02.2000"], book)

    def test_add_birthday_contact_not_found(self):
        assert "Error" in add_birthday(["Ghost", "01.01.1990"], AddressBook())

    def test_edit_birthday(self):
        book = _make_book(("Frank", "1234567890"))
        add_birthday(["Frank", "01.01.1990"], book)
        edit_birthday(["Frank", "20.07.1991"], book)
        assert str(book.find("Frank").birthday) == "20.07.1991"

    def test_edit_birthday_when_none(self):
        book = _make_book(("Frank", "1234567890"))
        assert "Error" in edit_birthday(["Frank", "01.01.1990"], book)

    def test_delete_birthday(self):
        book = _make_book(("Frank", "1234567890"))
        add_birthday(["Frank", "01.01.1990"], book)
        delete_birthday(["Frank"], book)
        assert book.find("Frank").birthday is None

    def test_delete_birthday_when_none(self):
        book = _make_book(("Frank", "1234567890"))
        assert "Error" in delete_birthday(["Frank"], book)


# =============================================================================
# add-address / edit-address / delete-address  (guided, interactive)
# =============================================================================

class TestAddressCommands:

    def _book_with_address(self):
        book = _make_book(("Carl", "1234567890"))
        book.find("Carl").add_address("Ukraine, Kyiv")
        return book

    def test_add_address_success(self):
        book = _make_book(("Carl", "1234567890"))
        # country, city, street, house, apt(skip), zip(skip)
        with patch("builtins.input", side_effect=["Ukraine", "Kyiv", "Main St", "1", "", ""]):
            result = add_address(["Carl"], book)
        assert "added" in result.lower()
        assert "Ukraine" in str(book.find("Carl").address)

    def test_add_address_cancel(self):
        book = _make_book(("Carl", "1234567890"))
        with patch("builtins.input", side_effect=["cancel"]):
            result = add_address(["Carl"], book)
        assert "cancel" in result.lower()
        assert book.find("Carl").address is None

    def test_add_address_refuses_to_overwrite(self):
        book = self._book_with_address()
        assert "already has an address" in add_address(["Carl"], book)

    def test_add_address_contact_not_found(self):
        assert "Error" in add_address(["Ghost"], AddressBook())

    def test_edit_address_success(self):
        book = self._book_with_address()
        with patch("builtins.input", side_effect=["Poland", "Warsaw", "Main St", "5", "", ""]):
            edit_address(["Carl"], book)
        assert "Poland" in str(book.find("Carl").address)

    def test_edit_address_when_none(self):
        book = _make_book(("Carl", "1234567890"))
        assert "Error" in edit_address(["Carl"], book)

    def test_delete_address(self):
        book = self._book_with_address()
        delete_address(["Carl"], book)
        assert book.find("Carl").address is None

    def test_delete_address_when_none(self):
        book = _make_book(("Carl", "1234567890"))
        assert "Error" in delete_address(["Carl"], book)


# =============================================================================
# Notes
# =============================================================================

class TestNoteCommands:

    def test_add_note_success(self):
        book = _make_book(("Grace", "1234567890"))
        result = add_note(["Grace", "Buy", "groceries"], book)
        assert "added" in result
        assert book.find("Grace").notes[0].value == "Buy groceries"

    def test_add_note_contact_not_found(self):
        assert "Error" in add_note(["Ghost", "text"], AddressBook())

    def test_add_note_multi_word_name(self):
        book = AddressBook()
        book.add_record(_record("Mary Jane", "1234567890"))
        result = add_note(["Mary", "Jane", "Buy", "milk"], book)
        assert "added" in result
        assert book.find("Mary Jane").notes[0].value == "Buy milk"

    def test_add_note_missing_text_prompts_for_note_and_tags(self):
        # Name with no inline text starts a guided flow: prompt for the note text,
        # then for tags. Both are applied to the new note.
        book = _make_book(("Grace", "1234567890"))
        with patch("builtins.input", side_effect=["Buy milk", "shopping, urgent"]):
            result = add_note(["Grace"], book)
        note = book.find("Grace").notes[0]
        assert "added" in result
        assert note.value == "Buy milk"
        assert note.tags == ["shopping", "urgent"]

    def test_add_note_missing_text_cancel_aborts(self):
        # Cancelling at the note prompt adds nothing.
        book = _make_book(("Grace", "1234567890"))
        with patch("builtins.input", side_effect=["cancel"]):
            result = add_note(["Grace"], book)
        assert "cancelled" in result.lower()
        assert book.find("Grace").notes == []

    def test_add_note_missing_text_blank_tags_keeps_note(self):
        # Empty tag entry still saves the note, just without tags.
        book = _make_book(("Grace", "1234567890"))
        with patch("builtins.input", side_effect=["Buy milk", ""]):
            result = add_note(["Grace"], book)
        note = book.find("Grace").notes[0]
        assert "added" in result
        assert note.value == "Buy milk"
        assert note.tags == []

    def test_add_note_missing_name(self):
        assert "Error" in add_note([], AddressBook())

    def test_note_ids_are_globally_unique(self):
        book = _make_book(("Grace", "1234567890"), ("Henry", "0987654321"))
        add_note(["Grace", "first"], book)
        add_note(["Henry", "second"], book)
        all_ids = [n.id for r in book.data.values() for n in r.notes]
        assert len(all_ids) == len(set(all_ids))

    def test_edit_note_by_contact(self):
        book = _make_book(("Grace", "1234567890"))
        add_note(["Grace", "original"], book)
        with patch("builtins.input", side_effect=["updated text"]):
            result = edit_note(["Grace"], book)
        assert "updated" in result
        assert book.find("Grace").notes[0].value == "updated text"

    def test_edit_note_by_id(self):
        book = _make_book(("Grace", "1234567890"))
        add_note(["Grace", "original"], book)
        note_id = book.find("Grace").notes[0].id
        with patch("builtins.input", side_effect=["updated via id"]):
            edit_note([str(note_id)], book)
        assert book.find("Grace").notes[0].value == "updated via id"

    def test_edit_note_preserves_tags(self):
        # edit_text keeps id + tags (previously a bug rebuilt the Note and lost them).
        book = _make_book(("Grace", "1234567890"))
        add_note(["Grace", "task"], book)
        with patch("builtins.input", side_effect=["work"]):
            add_tag(["Grace"], book)
        with patch("builtins.input", side_effect=["updated task"]):
            edit_note(["Grace"], book)
        assert book.find("Grace").notes[0].tags == ["work"]

    def test_edit_note_no_notes(self):
        book = _make_book(("Grace", "1234567890"))
        assert "Error" in edit_note(["Grace"], book)

    def test_delete_note_by_contact(self):
        book = _make_book(("Grace", "1234567890"))
        add_note(["Grace", "to delete"], book)
        result = delete_note(["Grace"], book)
        assert "deleted" in result
        assert book.find("Grace").notes == []

    def test_delete_note_by_id(self):
        book = _make_book(("Grace", "1234567890"))
        add_note(["Grace", "to delete"], book)
        note_id = book.find("Grace").notes[0].id
        delete_note([str(note_id)], book)
        assert book.find("Grace").notes == []

    def test_delete_note_unknown_id(self):
        book = _make_book(("Grace", "1234567890"))
        assert "Error" in delete_note(["999"], book)

    def test_show_notes_returns_table(self):
        book = _make_book(("Grace", "1234567890"))
        add_note(["Grace", "some note"], book)
        assert isinstance(show_notes(["Grace"], book), Table)

    def test_show_notes_contact_has_none(self):
        book = _make_book(("Grace", "1234567890"))
        assert "No notes" in show_notes(["Grace"], book)

    def test_show_all_notes_returns_table(self):
        book = _make_book(("Grace", "1234567890"))
        add_note(["Grace", "note"], book)
        assert isinstance(show_all_notes([], book), Table)

    def test_show_all_notes_empty_book(self):
        assert "No notes" in show_all_notes([], AddressBook())

    def test_find_notes_by_text(self):
        book = _make_book(("Grace", "1234567890"))
        add_note(["Grace", "buy milk"], book)
        assert isinstance(find_notes(["milk"], book), Table)

    def test_find_notes_no_match(self):
        book = _make_book(("Grace", "1234567890"))
        add_note(["Grace", "buy milk"], book)
        assert "No notes found" in find_notes(["coffee"], book)

    def test_find_notes_missing_query(self):
        assert "Error" in find_notes([], AddressBook())


# =============================================================================
# Tags
# =============================================================================

class TestTagCommands:

    def _book_with_tagged_note(self, name="Ivan", text="task", *tags):
        book = _make_book((name, "1234567890"))
        add_note([name, text], book)
        for tag in tags:
            book.find(name).notes[0].add_tag(tag)
        return book

    def test_add_tag_single(self):
        book = _make_book(("Ivan", "1234567890"))
        add_note(["Ivan", "work task"], book)
        with patch("builtins.input", side_effect=["work"]):
            result = add_tag(["Ivan"], book)
        assert "work" in result
        assert "work" in book.find("Ivan").notes[0].tags

    def test_add_tag_multiple_comma_separated(self):
        book = _make_book(("Ivan", "1234567890"))
        add_note(["Ivan", "task"], book)
        with patch("builtins.input", side_effect=["work, urgent"]):
            add_tag(["Ivan"], book)
        assert set(book.find("Ivan").notes[0].tags) == {"work", "urgent"}

    def test_add_tag_no_notes(self):
        book = _make_book(("Ivan", "1234567890"))
        assert "Error" in add_tag(["Ivan"], book)

    def test_add_tag_empty_input(self):
        book = _make_book(("Ivan", "1234567890"))
        add_note(["Ivan", "task"], book)
        with patch("builtins.input", side_effect=[""]):
            assert "Error" in add_tag(["Ivan"], book)

    def test_edit_tag_replaces_list(self):
        book = self._book_with_tagged_note("Ivan", "task", "old")
        with patch("builtins.input", side_effect=["work, urgent"]):
            edit_tag(["Ivan"], book)
        assert book.find("Ivan").notes[0].tags == ["work", "urgent"]

    def test_edit_tag_blank_clears(self):
        book = self._book_with_tagged_note("Ivan", "task", "old")
        with patch("builtins.input", side_effect=[""]):
            edit_tag(["Ivan"], book)
        assert book.find("Ivan").notes[0].tags == []

    def test_delete_tag_single(self):
        book = self._book_with_tagged_note("Ivan", "task", "work")
        delete_tag(["Ivan"], book)
        assert book.find("Ivan").notes[0].tags == []

    def test_delete_tag_choose_all(self):
        book = self._book_with_tagged_note("Ivan", "task", "work", "urgent")
        with patch("builtins.input", side_effect=["all"]):
            delete_tag(["Ivan"], book)
        assert book.find("Ivan").notes[0].tags == []

    def test_delete_tag_no_tags(self):
        book = self._book_with_tagged_note("Ivan", "task")
        assert "Error" in delete_tag(["Ivan"], book)

    def test_find_by_tag_returns_table(self):
        book = self._book_with_tagged_note("Ivan", "task", "urgent")
        assert isinstance(find_by_tag(["urgent"], book), Table)

    def test_find_by_tag_no_match(self):
        book = self._book_with_tagged_note("Ivan", "task", "work")
        assert "No notes found" in find_by_tag(["nonexistent"], book)

    def test_sort_by_tags_returns_table(self):
        book = self._book_with_tagged_note("Ivan", "task", "work")
        assert isinstance(sort_by_tags([], book), Table)

    def test_sort_by_tags_no_tagged_notes(self):
        assert "No notes" in sort_by_tags([], AddressBook())

    def test_find_notes_matches_by_exact_tag(self):
        # find-notes searches both note text and tags (exact tag match)
        book = self._book_with_tagged_note("Ivan", "my task", "work")
        assert isinstance(find_notes(["work"], book), Table)


# =============================================================================
# Display / search
# =============================================================================

class TestDisplayCommands:

    def test_display_all_empty_book(self):
        assert "No contacts" in display_all([], AddressBook())

    def test_display_all_returns_table(self):
        assert isinstance(display_all([], _make_book(("Alice", "1234567890"))), Table)

    def test_display_phone_returns_table(self):
        assert isinstance(display_phone(["Dave"], _make_book(("Dave", "1234567890"))), Table)

    def test_display_phone_contact_not_found(self):
        assert "Error" in display_phone(["Ghost"], AddressBook())

    def test_display_phone_missing_arg(self):
        assert "Error" in display_phone([], AddressBook())

    def test_find_contact_by_exact_name(self):
        book = _make_book(("Alice", "1234567890"))
        assert isinstance(find_contact(["Alice"], book), Table)

    def test_find_contact_partial_name_case_insensitive(self):
        book = _make_book(("Alice", "1234567890"), ("Albert", "0987654321"))
        assert isinstance(find_contact(["al"], book), Table)

    def test_find_contact_by_partial_phone(self):
        book = _make_book(("Alice", "1234567890"))
        assert isinstance(find_contact(["1234"], book), Table)

    def test_find_contact_no_results(self):
        assert "No contacts found" in find_contact(["xyz"], _make_book(("Alice", "1234567890")))

    def test_find_contact_missing_query(self):
        assert "Error" in find_contact([], AddressBook())

    def test_all_with_notes_empty_book(self):
        assert "No contacts" in all_with_notes([], AddressBook())

    def test_all_with_notes_returns_table(self):
        book = _make_book(("Alice", "1234567890"))
        add_note(["Alice", "test note"], book)
        assert isinstance(all_with_notes([], book), Table)


# =============================================================================
# _full_contact_rows  (shared row builder for find-contact / show-contacts-full)
# =============================================================================

class TestFullContactRows:

    def test_phone_rendered_with_mask(self):
        # Phones are stored as bare digits but must display in +38(0XX)... mask.
        book = _make_book(("Alice", "0991234567"))
        rows = _full_contact_rows(book.data.values())
        phones_cell = rows[0][1]
        assert phones_cell == "+38(099)123-45-67"
        assert "0991234567" not in phones_cell

    def test_multiple_phones_all_masked(self):
        book = AddressBook()
        book.add_record(_record("Alice", "0991234567", "0671112233"))
        phones_cell = _full_contact_rows(book.data.values())[0][1]
        assert "+38(099)123-45-67" in phones_cell
        assert "+38(067)111-22-33" in phones_cell

    def test_tags_aligned_per_note_not_flattened(self):
        # Tags belong to a note: each note's tags sit on their own line aligned
        # with the Notes column, instead of one flattened per-contact string.
        book = _make_book(("Alice", "0991234567"))
        add_note(["Alice", "first"], book)
        add_note(["Alice", "second"], book)
        alice = book.find("Alice")
        alice.notes[0].add_tag("work")
        alice.notes[1].add_tag("home")

        notes_cell, tags_cell = _full_contact_rows(book.data.values())[0][5:7]
        assert notes_cell.splitlines() == [
            f"[{alice.notes[0].id}] first",
            f"[{alice.notes[1].id}] second",
        ]
        assert tags_cell.splitlines() == ["work", "home"]

    def test_note_without_tags_shows_dash_on_its_line(self):
        book = _make_book(("Alice", "0991234567"))
        add_note(["Alice", "tagged"], book)
        add_note(["Alice", "untagged"], book)
        book.find("Alice").notes[0].add_tag("work")
        tags_cell = _full_contact_rows(book.data.values())[0][6]
        assert tags_cell.splitlines() == ["work", "—"]

    def test_empty_optional_fields_show_dash(self):
        book = _make_book(("Alice", "0991234567"))
        row = _full_contact_rows(book.data.values())[0]
        # email, birthday, address, notes, tags all empty -> dash
        assert row[2] == "—" and row[3] == "—" and row[4] == "—"
        assert row[5] == "—" and row[6] == "—"

    def test_display_birthday_returns_table(self):
        book = _make_book(("Alice", "1234567890"))
        add_birthday(["Alice", "01.01.1990"], book)
        assert isinstance(display_birthday(["Alice"], book), Table)

    def test_display_birthday_not_set(self):
        book = _make_book(("Alice", "1234567890"))
        assert "no birthday" in display_birthday(["Alice"], book)

    def test_display_birthday_contact_not_found(self):
        assert "Error" in display_birthday(["Ghost"], AddressBook())

    def test_display_birthdays_none_upcoming(self):
        assert "No birthdays" in display_birthdays([], _make_book(("Frank", "1234567890")))

    def test_display_birthdays_upcoming_returns_table(self):
        book = _make_book(("Frank", "1234567890"))
        add_birthday(["Frank", _birthday_in(2)], book)
        assert isinstance(display_birthdays([], book), Table)

    def test_display_birthdays_custom_window(self):
        book = _make_book(("Frank", "1234567890"))
        add_birthday(["Frank", _birthday_in(20)], book)
        assert "No birthdays" in display_birthdays([], book)          # default 7 days
        assert isinstance(display_birthdays(["30"], book), Table)     # 30-day window

    def test_show_help_returns_table(self):
        assert isinstance(show_help([], AddressBook()), Table)

    def test_show_help_row_count(self):
        # One group-header row per non-empty group + one row per command,
        # except "exit" which is folded into the "close" row.
        groups = {g for (_, _, g) in COMMAND_META.values()} & set(GROUP_ORDER)
        expected = len(groups) + (len(COMMAND_META) - 1)
        assert show_help([], AddressBook()).row_count == expected

    def test_show_help_contains_known_commands(self):
        from io import StringIO
        from rich.console import Console
        buf = StringIO()
        Console(file=buf, width=200, force_terminal=False).print(show_help([], AddressBook()))
        rendered = buf.getvalue()
        for cmd in ("add", "edit-phone", "find-contact", "add-note", "add-tag", "upcoming-birthdays"):
            assert cmd in rendered

    def test_hello_returns_non_empty_string(self):
        result = hello_message([], AddressBook())
        assert isinstance(result, str) and result


# =============================================================================
# Input parsing
# =============================================================================

class TestParseInput:

    def test_simple_command(self):
        assert parse_input("hello") == ("hello",)

    def test_command_with_args(self):
        cmd, *args = parse_input("add Alice 1234567890")
        assert cmd == "add"
        assert args == ["Alice", "1234567890"]

    def test_command_normalized_to_lowercase(self):
        cmd, *_ = parse_input("ADD Alice")
        assert cmd == "add"

    def test_leading_trailing_spaces_stripped(self):
        cmd, *args = parse_input("  add   Alice   1234567890  ")
        assert cmd == "add"
        assert args == ["Alice", "1234567890"]


# =============================================================================
# Command validation / suggestions
# =============================================================================

class TestGetValidatedCommand:

    def test_exact_match_returned(self):
        assert get_validated_command("add", ["add", "help"]) == "add"

    def test_typo_returns_none(self):
        # A close typo shows suggestions but does not auto-run a guess.
        assert get_validated_command("addd", ["add", "help"]) is None

    def test_unknown_returns_none(self):
        assert get_validated_command("zzzzz", ["add", "help"]) is None


# =============================================================================
# Persistence
# =============================================================================

class TestPersistence:

    def test_save_and_reload(self, tmp_path):
        path = str(tmp_path / "book.pkl")
        save_data(_make_book(("Alice", "1234567890")), path)
        loaded = load_data(path)
        assert loaded.find("Alice").find_phone("1234567890") is not None

    def test_load_missing_file_returns_empty_book(self, tmp_path):
        loaded = load_data(str(tmp_path / "nonexistent.pkl"))
        assert isinstance(loaded, AddressBook)
        assert len(loaded.data) == 0

    def test_persistence_preserves_all_fields(self, tmp_path):
        path = str(tmp_path / "book.pkl")
        book = _make_book(("Alice", "1234567890"))
        add_birthday(["Alice", "01.06.1990"], book)
        add_email(["Alice", "alice@example.com"], book)
        book.find("Alice").add_address("Kyiv")
        add_note(["Alice", "a note"], book)
        save_data(book, path)
        r = load_data(path).find("Alice")
        assert str(r.birthday) == "01.06.1990"
        assert r.find_email("alice@example.com") is not None
        assert str(r.address) == "Kyiv"
        assert r.notes[0].value == "a note"


# =============================================================================
# COMMAND_META / commands registry contract
# =============================================================================

class TestCommandMeta:

    def test_all_registered_commands_have_meta_entry(self):
        # Every dispatchable command must be documented in COMMAND_META so help
        # and tab-completion stay in sync.
        missing = set(COMMANDS.keys()) - set(COMMAND_META.keys())
        assert missing == set(), f"Commands missing from COMMAND_META: {missing}"

    def test_each_entry_is_three_string_tuple_with_valid_group(self):
        for cmd, value in COMMAND_META.items():
            assert isinstance(value, tuple) and len(value) == 3, \
                f"COMMAND_META['{cmd}'] should be a 3-tuple"
            args_hint, description, group = value
            assert isinstance(args_hint, str), f"args_hint for '{cmd}' must be str"
            assert isinstance(description, str) and description, \
                f"description for '{cmd}' must be a non-empty str"
            assert group in GROUP_ORDER, f"group '{group}' for '{cmd}' not in GROUP_ORDER"

    def test_close_and_exit_documented_but_not_dispatched(self):
        # close/exit are handled in the REPL loop, not the commands dict.
        assert {"close", "exit"} <= set(COMMAND_META.keys())
        assert "close" not in COMMANDS and "exit" not in COMMANDS


# =============================================================================
# CommandCompleter  (tab-completion logic)
# =============================================================================

class TestCommandCompleter:

    def _completions(self, text):
        doc = Document(text)
        return [c.text for c in CommandCompleter().get_completions(doc, None)]

    def test_empty_input_returns_all_commands(self):
        assert set(self._completions("")) == set(COMMAND_META.keys())

    def test_prefix_filters_matching_commands(self):
        result = self._completions("ad")
        assert all(c.startswith("ad") for c in result)
        assert "add" in result
        assert "add-note" in result
        assert "add-birthday" in result

    def test_exact_prefix_returns_itself_and_longer_matches(self):
        result = self._completions("add")
        assert "add" in result
        assert "add-note" in result

    def test_unmatched_prefix_returns_empty(self):
        assert self._completions("zzzzz") == []

    def test_input_with_space_returns_empty(self):
        assert self._completions("add ") == []
        assert self._completions("add Alice") == []

    def test_matching_is_case_insensitive(self):
        assert set(self._completions("add")) == set(self._completions("ADD"))

    def test_completion_display_meta_contains_description(self):
        completions = list(CommandCompleter().get_completions(Document("hello"), None))
        assert len(completions) == 1
        assert "Greet" in str(completions[0].display_meta)


# =============================================================================
# Export: _record_to_dict
# =============================================================================

class TestRecordToDict:

    def _full_record(self):
        r = _record("Alice", "1234567890", "0987654321")
        r.add_email("alice@example.com")
        r.add_birthday("15.06.1990")
        r.add_address("Kyiv, Main St 1")
        r.add_note("Buy milk", 1)
        r.notes[0].add_tag("personal")
        r.add_note("Work task", 2)
        return r

    def test_name_exported(self):
        assert _record_to_dict(_record("Alice"))["name"] == "Alice"

    def test_phones_exported_as_list(self):
        r = _record("Alice", "1234567890", "0987654321")
        assert _record_to_dict(r)["phones"] == ["1234567890", "0987654321"]

    def test_emails_exported_as_list(self):
        r = _record("Alice")
        r.add_email("a@example.com")
        r.add_email("b@example.com")
        assert _record_to_dict(r)["emails"] == ["a@example.com", "b@example.com"]

    def test_emails_empty_list_when_none(self):
        assert _record_to_dict(_record("Alice"))["emails"] == []

    def test_birthday_exported_as_string(self):
        r = _record("Alice")
        r.add_birthday("15.06.1990")
        assert _record_to_dict(r)["birthday"] == "15.06.1990"

    def test_birthday_empty_when_not_set(self):
        assert _record_to_dict(_record("Alice"))["birthday"] == ""

    def test_address_exported(self):
        r = _record("Alice")
        r.add_address("Kyiv, Main St 1")
        assert _record_to_dict(r)["address"] == "Kyiv, Main St 1"

    def test_notes_exported_with_id_text_tags(self):
        r = _record("Alice")
        r.add_note("Buy milk", 7)
        r.notes[0].add_tag("personal")
        notes = _record_to_dict(r)["notes"]
        assert notes == [{"id": 7, "text": "Buy milk", "tags": ["personal"]}]

    def test_notes_empty_list_when_none(self):
        assert _record_to_dict(_record("Alice"))["notes"] == []

    def test_full_record_all_fields_present(self):
        d = _record_to_dict(self._full_record())
        assert d["name"] == "Alice"
        assert len(d["phones"]) == 2
        assert d["emails"] == ["alice@example.com"]
        assert d["birthday"] == "15.06.1990"
        assert d["address"] == "Kyiv, Main St 1"
        assert len(d["notes"]) == 2


# =============================================================================
# Export: _resolve_path
# =============================================================================

class TestResolvePath:

    def test_relative_name_gets_extension_and_export_dir(self, tmp_path, monkeypatch):
        import handlers.export_handlers as eh
        monkeypatch.setattr(eh, "EXPORT_DIR", str(tmp_path))
        result = _resolve_path("myfile", "json")
        assert result.endswith(".json")
        assert str(tmp_path) in result

    def test_name_with_correct_extension_unchanged(self, tmp_path, monkeypatch):
        import handlers.export_handlers as eh
        monkeypatch.setattr(eh, "EXPORT_DIR", str(tmp_path))
        result = _resolve_path("myfile.json", "json")
        assert result.endswith("myfile.json")

    def test_absolute_path_returned_as_is(self, tmp_path):
        abs_path = str(tmp_path / "out.json")
        assert _resolve_path(abs_path, "json") == abs_path


# =============================================================================
# Export: JSON output
# =============================================================================

class TestExportJson:

    def _book(self):
        book = AddressBook()
        r = _record("Alice", "1234567890")
        r.add_email("alice@example.com")
        r.add_birthday("15.06.1990")
        r.add_note("Task one", 1)
        r.notes[0].add_tag("work")
        book.add_record(r)
        book.add_record(_record("Bob", "0987654321"))
        return book

    def test_creates_valid_json_list(self, tmp_path):
        path = str(tmp_path / "out.json")
        _export_json(self._book(), path)
        assert isinstance(json.loads(Path(path).read_text(encoding="utf-8")), list)

    def test_all_contacts_exported(self, tmp_path):
        path = str(tmp_path / "out.json")
        _export_json(self._book(), path)
        names = [r["name"] for r in json.loads(Path(path).read_text(encoding="utf-8"))]
        assert "Alice" in names and "Bob" in names

    def test_phones_and_emails_serialized_as_lists(self, tmp_path):
        path = str(tmp_path / "out.json")
        _export_json(self._book(), path)
        alice = next(r for r in json.loads(Path(path).read_text(encoding="utf-8")) if r["name"] == "Alice")
        assert alice["phones"] == ["1234567890"]
        assert alice["emails"] == ["alice@example.com"]

    def test_notes_with_tags_serialized(self, tmp_path):
        path = str(tmp_path / "out.json")
        _export_json(self._book(), path)
        alice = next(r for r in json.loads(Path(path).read_text(encoding="utf-8")) if r["name"] == "Alice")
        assert alice["notes"][0]["text"] == "Task one"
        assert alice["notes"][0]["tags"] == ["work"]

    def test_optional_fields_empty_when_not_set(self, tmp_path):
        path = str(tmp_path / "out.json")
        _export_json(self._book(), path)
        bob = next(r for r in json.loads(Path(path).read_text(encoding="utf-8")) if r["name"] == "Bob")
        assert bob["emails"] == []
        assert bob["birthday"] == ""

    def test_file_is_utf8_encoded(self, tmp_path):
        book = AddressBook()
        book.add_record(_record("Олексій", "1234567890"))
        path = str(tmp_path / "out.json")
        _export_json(book, path)
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        assert data[0]["name"] == "Олексій"


# =============================================================================
# Export: CSV output
# =============================================================================

class TestExportCsv:

    def _book_with_notes(self):
        book = AddressBook()
        r = _record("Alice", "1234567890", "0987654321")
        r.add_email("alice@example.com")
        r.add_note("Task one", 1)
        r.notes[0].add_tag("work")
        r.notes[0].add_tag("urgent")
        r.add_note("Task two", 2)
        book.add_record(r)
        book.add_record(_record("Bob", "1111111111"))
        return book

    def _read_csv(self, path):
        with open(path, encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))

    def test_creates_csv_with_correct_header(self, tmp_path):
        path = str(tmp_path / "out.csv")
        _export_csv(_make_book(("Alice", "1234567890")), path)
        with open(path, encoding="utf-8", newline="") as f:
            header = next(csv.reader(f))
        assert header == ["name", "phones", "email", "birthday", "address",
                          "note_id", "note_text", "note_tags"]

    def test_contact_without_notes_writes_one_row(self, tmp_path):
        path = str(tmp_path / "out.csv")
        _export_csv(_make_book(("Bob", "1111111111")), path)
        rows = self._read_csv(path)
        assert len(rows) == 1
        assert rows[0]["name"] == "Bob"
        assert rows[0]["note_text"] == ""

    def test_contact_with_two_notes_writes_two_rows(self, tmp_path):
        path = str(tmp_path / "out.csv")
        _export_csv(self._book_with_notes(), path)
        rows = [r for r in self._read_csv(path) if r["name"] == "Alice"]
        assert len(rows) == 2

    def test_multiple_phones_joined_in_one_cell(self, tmp_path):
        path = str(tmp_path / "out.csv")
        _export_csv(self._book_with_notes(), path)
        alice_row = next(r for r in self._read_csv(path) if r["name"] == "Alice")
        assert "1234567890" in alice_row["phones"]
        assert "0987654321" in alice_row["phones"]

    def test_note_tags_joined_in_one_cell(self, tmp_path):
        path = str(tmp_path / "out.csv")
        _export_csv(self._book_with_notes(), path)
        tagged = next(r for r in self._read_csv(path)
                      if r["name"] == "Alice" and r["note_text"] == "Task one")
        assert "work" in tagged["note_tags"]
        assert "urgent" in tagged["note_tags"]

    def test_note_without_tags_has_empty_tags_field(self, tmp_path):
        path = str(tmp_path / "out.csv")
        _export_csv(self._book_with_notes(), path)
        untagged = next(r for r in self._read_csv(path)
                        if r["name"] == "Alice" and r["note_text"] == "Task two")
        assert untagged["note_tags"] == ""


# =============================================================================
# Export: export-book command handler
# =============================================================================

class TestExportBookCommand:

    def test_empty_book_returns_message(self):
        assert "empty" in export_book(["json"], AddressBook()).lower()

    def test_missing_format_returns_error(self):
        assert "Error" in export_book([], _make_book(("Alice", "1234567890")))

    def test_invalid_format_returns_error(self):
        assert "Error" in export_book(["xml"], _make_book(("Alice", "1234567890")))

    def test_export_json_to_custom_path(self, tmp_path):
        path = str(tmp_path / "contacts.json")
        export_book(["json", path], _make_book(("Alice", "1234567890")))
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        assert any(r["name"] == "Alice" for r in data)

    def test_export_csv_to_custom_path(self, tmp_path):
        path = str(tmp_path / "contacts.csv")
        export_book(["csv", path], _make_book(("Alice", "1234567890")))
        rows = list(csv.DictReader(open(path, encoding="utf-8")))
        assert rows[0]["name"] == "Alice"

    def test_success_message_includes_contact_count(self, tmp_path):
        path = str(tmp_path / "out.json")
        result = export_book(["json", path], _make_book(("Alice", "1234567890"), ("Bob", "0987654321")))
        assert "2" in result

    def test_custom_path_without_extension_gets_extension_added(self, tmp_path):
        path_no_ext = str(tmp_path / "myexport")
        export_book(["json", path_no_ext], _make_book(("Alice", "1234567890")))
        assert Path(path_no_ext + ".json").exists()

    def test_export_json_produces_valid_structure(self, tmp_path):
        path = str(tmp_path / "out.json")
        export_book(["json", path], _make_book(("Alice", "1234567890")))
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert set(data[0].keys()) >= {"name", "phones", "emails", "birthday", "address", "notes"}


# =============================================================================
# save command  (persist on demand)
# =============================================================================

class TestSaveCommand:

    def _patch_save(self, monkeypatch):
        """Capture save_data calls so the real addressbook.pkl is never touched."""
        calls = []
        import handlers.export_handlers as eh
        monkeypatch.setattr(eh, "save_data", lambda book: calls.append(book))
        return calls

    def test_save_persists_and_reports_count(self, monkeypatch):
        calls = self._patch_save(monkeypatch)
        book = _make_book(("Alice", "1234567890"), ("Bob", "0987654321"))
        result = save_book([], book)
        assert calls == [book]                # save_data called once with the book
        assert "2" in result and "saved" in result.lower()

    def test_save_empty_book(self, monkeypatch):
        calls = self._patch_save(monkeypatch)
        result = save_book([], AddressBook())
        assert calls and "0" in result


# =============================================================================
# dump command  (two-step destructive wipe — needs an exact confirmation phrase)
# =============================================================================

class TestDumpCommand:

    def _patch_save(self, monkeypatch):
        saved = []
        import handlers.export_handlers as eh
        monkeypatch.setattr(eh, "save_data", lambda book: saved.append(len(book.data)))
        return saved

    def test_dump_already_empty_book(self, monkeypatch):
        self._patch_save(monkeypatch)
        assert "already empty" in dump_book([], AddressBook())

    def test_dump_wrong_phrase_aborts(self, monkeypatch):
        saved = self._patch_save(monkeypatch)
        book = _make_book(("Alice", "1234567890"), ("Bob", "0987654321"))
        with patch("builtins.input", return_value="yes"):
            result = dump_book([], book)
        assert "cancel" in result.lower()
        assert len(book.data) == 2            # nothing deleted
        assert saved == []                    # and nothing persisted

    def test_dump_empty_input_aborts(self, monkeypatch):
        self._patch_save(monkeypatch)
        book = _make_book(("Alice", "1234567890"))
        with patch("builtins.input", return_value=""):
            dump_book([], book)
        assert len(book.data) == 1

    def test_dump_almost_right_phrase_aborts(self, monkeypatch):
        # A near-miss (wrong casing / trailing text) must NOT trigger the wipe.
        self._patch_save(monkeypatch)
        book = _make_book(("Alice", "1234567890"))
        with patch("builtins.input", return_value=DUMP_CONFIRMATION.lower()):
            dump_book([], book)
        assert len(book.data) == 1

    def test_dump_exact_phrase_wipes_and_persists(self, monkeypatch):
        saved = self._patch_save(monkeypatch)
        book = _make_book(("Alice", "1234567890"), ("Bob", "0987654321"))
        with patch("builtins.input", return_value=DUMP_CONFIRMATION):
            result = dump_book([], book)
        assert len(book.data) == 0            # wiped
        assert saved == [0]                   # empty book persisted immediately
        assert "deleted" in result.lower()

    def test_dump_strips_surrounding_whitespace_on_confirmation(self, monkeypatch):
        # Handler .strip()s the answer, so padding around the exact phrase still works.
        self._patch_save(monkeypatch)
        book = _make_book(("Alice", "1234567890"))
        with patch("builtins.input", return_value=f"  {DUMP_CONFIRMATION}  "):
            dump_book([], book)
        assert len(book.data) == 0
