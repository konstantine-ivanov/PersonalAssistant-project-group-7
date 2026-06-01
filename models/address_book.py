from collections import UserDict
from datetime import date, timedelta

from .fields import normalize_punctuation


def _occurrence(birthday, year):
    # Map a birthday onto a given year for the upcoming-birthday comparison.
    # Feb 29 has no counterpart in non-leap years, so fall back to Feb 28 instead
    # of crashing the whole command with a ValueError.
    try:
        return birthday.replace(year=year)
    except ValueError:
        return date(year, 2, 28)


class AddressBook(UserDict):
    # Records are keyed by the lower-cased name so find/delete stay O(1) dict
    # operations while remaining case-insensitive ("john" finds "John"). The
    # original casing is preserved on record.name for display. Names are unique
    # ignoring case, so the lower-cased name is a safe unique key.
    @staticmethod
    def _key(name):
        # Normalise smart punctuation before lower-casing so a lookup typed with a
        # curly apostrophe/dash matches a record stored with the ASCII form.
        return normalize_punctuation(name).lower()

    def add_record(self, record):
        self.data[self._key(record.name.value)] = record

    def find(self, name):
        return self.data.get(self._key(name))

    def delete(self, name):
        self.data.pop(self._key(name), None)

    def get_upcoming_birthdays(self, days=7):
        # Find contacts to congratulate within the next `days` days.
        # Accepts the look-ahead window in days. Returns a list of
        # {"name", "congratulation_date" (DD.MM.YYYY)} dicts, where birthdays
        # landing on a weekend are moved to the following Monday.
        today = date.today()
        upcoming = []

        for record in self.data.values():
            if not record.birthday:
                continue

            # Compare on this year's date so only month/day matter, not the year born.
            birthday_this_year = _occurrence(record.birthday.value, today.year)

            # Already passed this year -> the next occurrence is next year.
            if birthday_this_year < today:
                birthday_this_year = _occurrence(record.birthday.value, today.year + 1)

            days_until = (birthday_this_year - today).days

            if 0 <= days_until <= days:
                # Weekend birthdays are greeted on the next working day (Monday).
                if birthday_this_year.weekday() == 5:
                    congrats_date = birthday_this_year + timedelta(days=2)
                elif birthday_this_year.weekday() == 6:
                    congrats_date = birthday_this_year + timedelta(days=1)
                else:
                    congrats_date = birthday_this_year

                upcoming.append({
                    "name": record.name.value,
                    "congratulation_date": congrats_date.strftime("%d.%m.%Y"),
                })

        return upcoming
