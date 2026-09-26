"""
gather_pending.py - the list of requests you have sent that nobody has answered.

Two jobs need this page and neither of them owns it. `undo` reads it to find the
requests old enough to take back. `accepted` reads it to find out who is no longer
on it, because leaving the list is how you learn somebody said yes.

ONE READER, TWO JOBS. If each job read the page its own way, the two reads would
disagree about the same list -- one tolerant of a name written with a badge on it,
one not -- and the disagreement would show up as a person who is somehow both
still pending and already accepted. The page is read here, once, in one way.

WHAT THIS PAGE IS WORTH BEYOND THE LIST. Every card on it carries the person's own
profile link. That link is the strongest identifier there is, and it is free to
read while you are here. So this reads it, and the jobs above stamp it on the
person, because a person you only hold a display name for is a person you cannot
match later without comparing strings that two pages spell differently.

READING IS NOT FREE. This is your own list about your own requests, which makes it
one of the quieter pages to read, and it is still a page read: it goes through the
doorman, it lands on an ordinary page first, and it waits like a person waits.

HONESTY ABOUT WHERE THIS CAME FROM. The way this page is loaded, and the way the
age is read off a card, come from a working system where they ran often enough to
be trusted. The exact selectors below still have to be confirmed against your own
account, because a page can be laid out differently for different people. Run the
probe first.

Needs: Python 3.8 or newer, plus Playwright.
"""

import random
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gather_walk as walk                                  # noqa: E402

SENT_PAGE = "https://www.linkedin.com/mynetwork/invitation-manager/sent/"

# The control that takes a request back. Its label carries the person's own name,
# which is what makes it safe to click: there is one per person and it cannot be
# confused with a control belonging to somebody else on the same page.
WITHDRAW_LABEL = 'a[aria-label^="Withdraw invitation sent to"]'

_AGE = re.compile(r"(today|yesterday|(\d+)\s*(minute|hour|day|week|month|year))", re.I)

_UNITS = {"minute": 0, "hour": 0, "day": 1, "week": 7, "month": 30, "year": 365}


def age_in_days(text):
    """How old a request is, read off the card, or None if the card does not say.

    Anchored to the "Sent ... ago" clause rather than to the first number on the
    card. A headline reading "20 years of experience" sits on the same card, and a
    reader that takes the first number it sees decides that request is twenty
    years old and takes it back.
    """
    text = text or ""
    m = re.search(r"Sent\s+(.{1,24}?)\s+ago", text, re.I)
    if m:
        basis = m.group(1)
    else:
        m2 = re.search(r"Sent\s+(today|yesterday)", text, re.I)
        basis = m2.group(1) if m2 else ""
    found = _AGE.search(basis)
    if not found:
        return None
    word = found.group(1).lower()
    if word == "today":
        return 0
    if word == "yesterday":
        return 1
    try:
        n = int(found.group(2))
    except (TypeError, ValueError):
        return None
    return n * _UNITS.get(found.group(3).lower(), 1)


# One pass in the page collects every card that has loaded. Asking the page about
# one card at a time is a round trip per person, and there can be hundreds.
READ_CARDS = r"""() => {
  const tidy = s => (s || '').replace(/\s+/g, ' ').trim();
  const out = [];
  for (const card of document.querySelectorAll('[role="listitem"]')) {
    const control = card.querySelector('a[aria-label^="Withdraw invitation sent to"]');
    if (!control) continue;
    const link = card.querySelector('a[href*="/in/"]');
    const label = control.getAttribute('aria-label') || '';
    out.push({
      label: label,
      name: label.replace(/^Withdraw invitation sent to\s*/i, '').trim() || null,
      link: link ? link.href.split('?')[0] : null,
      text: tidy(card.textContent).slice(0, 400),
    });
  }
  return out;
}"""


# What the probe reports: enough to tell you whether the reader above is looking at
# the right page, without collecting anybody.
PROBE_PAGE = r"""() => {
  const tidy = s => (s || '').replace(/\s+/g, ' ').trim();
  const cards = document.querySelectorAll('[role="listitem"]');
  const controls = document.querySelectorAll('a[aria-label^="Withdraw invitation sent to"]');
  const first = cards[0] ? tidy(cards[0].textContent).slice(0, 220) : '';
  return {
    address: location.href,
    heading: tidy((document.querySelector('h1') || {}).textContent || '').slice(0, 90),
    cards: cards.length,
    controls: controls.length,
    firstCard: first,
    links: document.querySelectorAll('[role="listitem"] a[href*="/in/"]').length,
  };
}"""


def open_list(page):
    """Land on the sent-requests page the ordinary way."""
    walk.open_page(page, SENT_PAGE)
    try:
        page.wait_for_selector(WITHDRAW_LABEL, timeout=20_000)
    except Exception:                                       # noqa: BLE001
        pass                                                # an empty list is a fine answer
    return page


def load_whole_list(page, rounds=200, say=None):
    """Bring every card into the page, not only the first screen of them.

    The list sits in its own scrolling area, so turning the wheel on the window
    does nothing at all. What does work is pulling the LAST card that exists into
    view, which makes the area fetch the next batch.

    Patience is the point. The oldest requests -- the ones worth taking back -- are
    at the BOTTOM, so a reader that gives up early reads the wrong end of the list
    and reports there is nothing to do. One slow batch must not read as finished,
    so this only stops after a run of rounds with no growth at all.
    """
    cards = page.locator('[role="listitem"]')
    last, still = 0, 0
    for i in range(rounds):
        try:
            n = cards.count()
        except Exception:                                   # noqa: BLE001
            break
        if n != last:
            last, still = n, 0
        else:
            still += 1
            try:
                more = page.get_by_role(
                    "button", name=re.compile(r"show more|load more|more results", re.I))
                if more.count() and more.first.is_visible():
                    more.first.click()
                    time.sleep(2.0)
                    still = 0
            except Exception:                               # noqa: BLE001
                pass
            if still >= 12:
                break
        try:
            cards.nth(max(n - 1, 0)).scroll_into_view_if_needed(timeout=5_000)
        except Exception:                                   # noqa: BLE001
            try:
                page.mouse.wheel(0, 2400)
            except Exception:                               # noqa: BLE001
                break
        time.sleep(random.uniform(0.8, 1.4))
        if say and i and i % 15 == 0:
            say("  ...%d so far" % last)
    return last


def read_cards(page):
    """Every loaded card, with its age worked out here rather than in the page."""
    try:
        rows = page.evaluate(READ_CARDS)
    except Exception:                                       # noqa: BLE001
        return []
    for row in rows:
        row["age_days"] = age_in_days(row.get("text"))
    return rows


def probe_report(page):
    """What the page looks like, with nobody collected and nothing written."""
    try:
        return page.evaluate(PROBE_PAGE)
    except Exception as err:                                # noqa: BLE001
        return {"error": str(err)[:200]}
