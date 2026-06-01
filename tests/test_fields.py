"""
Field-level validation tests.
Each field class is tested in isolation — no handlers, no address book.

Mirrors the rules in models/fields.py:
  Name     — stripped, required, <= 50 chars, each part has a letter and uses
             only letters, hyphens and apostrophes
  Phone    — non-digits stripped, must end up exactly 10 digits
  Birthday — DD.MM.YYYY only, must be a real date, not in the future
  Email    — local@domain.tld with a letters-only TLD of length >= 2
  Address  — stripped, required, <= 100 chars
  Note     — stripped, non-empty; owns id + tag list helpers
"""
import pytest
from datetime import date

from models.fields import Phone, Birthday, Email, Note, Name, Address
from models.fields import MAX_NAME_LENGTH, MAX_ADDRESS_LENGTH


# =============================================================================
# Phone
# =============================================================================

class TestPhoneField:

    def test_stores_10_digits(self):
        assert Phone("1234567890").value == "1234567890"

    def test_all_zeros_accepted(self):
        assert Phone("0000000000").value == "0000000000"

    def test_str_display_format(self):
        assert str(Phone("1234567890")) == "+38(123)456-78-90"

    # --- formatting is stripped before the length check ---

    @pytest.mark.parametrize("value", [
        "123-456-78-90",
        "(123) 456 7890",
        "123.456.78.90",
        " 1234567890 ",
    ])
    def test_formatting_stripped_to_bare_digits(self, value):
        assert Phone(value).value == "1234567890"

    # --- wrong length ---

    @pytest.mark.parametrize("value", ["", "1", "123456789", "12345678901"])
    def test_wrong_length_raises(self, value):
        with pytest.raises(ValueError):
            Phone(value)

    # --- non-digit characters ---
    # Phone strips non-digits via re.sub(r"\D","") before the length check,
    # so these all end up with fewer than 10 digits and fail on length.

    @pytest.mark.parametrize("value", [
        "abcdefghij",    # 0 digits after strip
        "!@#$%^&*()",    # 0 digits after strip
        "123456789a",    # 9 digits after strip
        "123456789\n",   # 9 digits after strip
        "123-456-789",   # 9 digits after strip
    ])
    def test_non_digit_chars_insufficient_digits_raises(self, value):
        with pytest.raises(ValueError):
            Phone(value)

    @pytest.mark.xfail(
        reason="'+' is stripped by re.sub leaving 10 valid digits — raw format is not validated",
        strict=True,
    )
    def test_plus_prefix_rejected(self):
        with pytest.raises(ValueError):
            Phone("+1234567890")

    @pytest.mark.xfail(
        reason="re.sub(r'\\D') keeps Unicode digits; Phone should require ASCII digits only",
        strict=True,
    )
    def test_unicode_arabic_digits_rejected(self):
        with pytest.raises(ValueError):
            Phone("١٢٣٤٥٦٧٨٩٠")  # 10 Arabic-Indic digits survive the \D strip


# =============================================================================
# Birthday
# =============================================================================

class TestBirthdayField:

    def test_stores_date_object(self):
        assert Birthday("15.06.1990").value == date(1990, 6, 15)

    def test_leap_year_accepted(self):
        assert Birthday("29.02.2000").value == date(2000, 2, 29)

    def test_today_accepted(self):
        assert Birthday(date.today().strftime("%d.%m.%Y")).value == date.today()

    def test_str_roundtrip(self):
        assert str(Birthday("15.06.1990")) == "15.06.1990"

    # --- future dates are rejected ---

    def test_future_date_raises(self):
        future = f"01.01.{date.today().year + 1}"
        with pytest.raises(ValueError):
            Birthday(future)

    # --- wrong separators / order ---

    @pytest.mark.parametrize("value", [
        "2000-01-15",   # ISO format
        "15/01/2000",   # slash separator
        "15 01 2000",   # space separator
        "15012000",     # no separator
        "2000.01.15",   # year-first order
    ])
    def test_wrong_separator_raises(self, value):
        with pytest.raises(ValueError):
            Birthday(value)

    # --- impossible dates ---

    @pytest.mark.parametrize("value", [
        "30.02.2000",   # February 30 never exists
        "29.02.2001",   # February 29 on a non-leap year
        "31.04.2000",   # April has only 30 days
        "15.00.2000",   # month 0
        "15.13.2000",   # month 13
        "00.01.2000",   # day 0
        "32.01.2000",   # day 32
    ])
    def test_impossible_date_raises(self, value):
        with pytest.raises(ValueError):
            Birthday(value)

    # --- malformed input ---

    @pytest.mark.parametrize("value", ["", "ab.cd.efgh", "15.01", "15.01.2000.extra"])
    def test_malformed_input_raises(self, value):
        with pytest.raises(ValueError):
            Birthday(value)

    @pytest.mark.xfail(
        reason="strptime('%d.%m.%Y') accepts single-digit day/month; leading zeros are not enforced",
        strict=True,
    )
    def test_no_leading_zero_rejected(self):
        with pytest.raises(ValueError):
            Birthday("1.1.2000")


# =============================================================================
# Email
# =============================================================================

class TestEmailField:

    @pytest.mark.parametrize("value", [
        "user@example.com",
        "first.last@mail.org",
        "user+tag@example.com",
        "user@sub.domain.com",
        "a@b.co",
    ])
    def test_valid_formats_accepted(self, value):
        assert Email(value).value == value

    @pytest.mark.parametrize("value", [
        "userexample.com",    # missing @
        "user@",              # missing domain
        "@example.com",       # missing local part
        "user@example",       # missing TLD
        "user@example.c",     # TLD too short (needs >= 2)
        "",                   # empty string
        "user @example.com",  # space in local part
    ])
    def test_invalid_formats_raise(self, value):
        with pytest.raises(ValueError):
            Email(value)


# =============================================================================
# Name  (validated in the model: required, <=50 chars, letters-only parts)
# =============================================================================

class TestNameField:

    def test_stores_value(self):
        assert Name("Alice").value == "Alice"

    def test_stores_multiword_name(self):
        assert Name("Mary Jane").value == "Mary Jane"

    def test_surrounding_whitespace_stripped(self):
        assert Name("  Alice  ").value == "Alice"

    def test_max_length_accepted(self):
        value = "A" * MAX_NAME_LENGTH
        assert Name(value).value == value

    def test_empty_name_raises(self):
        with pytest.raises(ValueError):
            Name("")

    def test_whitespace_only_name_raises(self):
        with pytest.raises(ValueError):
            Name("   ")

    def test_too_long_name_raises(self):
        with pytest.raises(ValueError):
            Name("A" * (MAX_NAME_LENGTH + 1))

    @pytest.mark.parametrize("value", ["Alice123", "John_Doe", "Bob!", "123", "-", "'", "--"])
    def test_non_letter_name_raises(self, value):
        # Each part must hold a letter and use only letters/hyphens/apostrophes;
        # digits, underscores, other symbols and bare punctuation are rejected.
        with pytest.raises(ValueError):
            Name(value)

    @pytest.mark.parametrize(
        "value", ["O'Brien", "Anne-Marie", "Jean-Luc", "Mary-Jane Walker", "D'Angelo"]
    )
    def test_hyphen_and_apostrophe_names_allowed(self, value):
        # Real names with hyphens/apostrophes are accepted and stored unchanged.
        assert Name(value).value == value


# =============================================================================
# Address  (validated in the model: required, <=100 chars)
# =============================================================================

class TestAddressField:

    def test_stores_value(self):
        assert Address("Kyiv, Khreshchatyk 1").value == "Kyiv, Khreshchatyk 1"

    def test_surrounding_whitespace_stripped(self):
        assert Address("  Kyiv  ").value == "Kyiv"

    def test_max_length_accepted(self):
        value = "A" * MAX_ADDRESS_LENGTH
        assert Address(value).value == value

    def test_empty_address_raises(self):
        with pytest.raises(ValueError):
            Address("")

    def test_whitespace_only_address_raises(self):
        with pytest.raises(ValueError):
            Address("   ")

    def test_too_long_address_raises(self):
        with pytest.raises(ValueError):
            Address("A" * (MAX_ADDRESS_LENGTH + 1))


# =============================================================================
# Note
# =============================================================================

class TestNoteField:

    def test_stores_text_and_id(self):
        n = Note("Buy milk", 42)
        assert n.value == "Buy milk"
        assert n.id == 42

    def test_leading_and_trailing_whitespace_stripped(self):
        assert Note("  Buy milk  ", 1).value == "Buy milk"

    def test_str_returns_text(self):
        assert str(Note("hello", 5)) == "hello"

    @pytest.mark.parametrize("text", ["", "   "])
    def test_empty_or_whitespace_only_raises(self, text):
        with pytest.raises(ValueError):
            Note(text, 1)

    # --- edit_text keeps id + tags, re-applies the non-empty rule ---

    def test_edit_text_updates_value(self):
        n = Note("old", 1)
        n.edit_text("new")
        assert n.value == "new"

    def test_edit_text_strips_whitespace(self):
        n = Note("old", 1)
        n.edit_text("  new  ")
        assert n.value == "new"

    def test_edit_text_keeps_id_and_tags(self):
        n = Note("old", 7)
        n.add_tag("work")
        n.edit_text("new")
        assert n.id == 7
        assert n.tags == ["work"]

    @pytest.mark.parametrize("text", ["", "   "])
    def test_edit_text_empty_raises(self, text):
        n = Note("old", 1)
        with pytest.raises(ValueError):
            n.edit_text(text)

    # --- tags ---

    def test_add_tag(self):
        n = Note("Task", 1)
        n.add_tag("work")
        assert "work" in n.tags

    def test_duplicate_tag_ignored(self):
        n = Note("Task", 1)
        n.add_tag("work")
        n.add_tag("work")
        assert n.tags.count("work") == 1

    def test_multiple_different_tags(self):
        n = Note("Task", 1)
        n.add_tag("work")
        n.add_tag("urgent")
        assert set(n.tags) == {"work", "urgent"}

    def test_remove_tag(self):
        n = Note("Task", 1)
        n.add_tag("work")
        n.remove_tag("work")
        assert n.tags == []

    def test_remove_missing_tag_raises(self):
        n = Note("Task", 1)
        with pytest.raises(ValueError):
            n.remove_tag("nope")

    def test_set_tags_replaces_dedupes_and_drops_blanks(self):
        n = Note("Task", 1)
        n.add_tag("old")
        n.set_tags(["work", "  ", "urgent", "work"])
        assert n.tags == ["work", "urgent"]

    def test_set_tags_empty_clears(self):
        n = Note("Task", 1)
        n.add_tag("work")
        n.set_tags([])
        assert n.tags == []
