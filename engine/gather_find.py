"""
gather_find.py - the job that goes out and brings people back, four ways.

    python gather.py find export <file.csv>       a file already on your machine
    python gather.py find connections             the people you are connected to
    python gather.py find search "<terms>"        one broad search, read deep
    python gather.py find reactions <post-url>    everyone who reacted to a post

They are in that order on purpose, and it is an order of risk, not of usefulness.

**export** touches nothing outside your machine. It hands the file straight to
your CRM's own collector, which already knows how to read an export, already
writes through the resolver, and already refuses to count the same row twice. This
layer adds nothing to that path, because there was nothing to add.

**connections** reads one page of your own account. Your own connections are the
dullest list you have and the one that makes everything else work, because it is
what gives most people a record at all.

**search** spends something you cannot get back. On an ordinary account there is a
monthly allowance of searches, somewhere around two hundred and fifty to three
hundred and fifty of them, and it is spent by SEARCHING, not by what comes back.
Past it, results collapse to about three per query until the allowance resets at
the start of the next month. So the shape that survives is ONE broad query read
deep, never many narrow ones, and this refuses to start a search when the
allowance is spent rather than spending the last of it to find out.

**reactions** is the most visible activity in the whole set. Reading who reacted to
a post is a lot of reading about a lot of strangers in a short space, which is
exactly the shape that gets noticed. There is also an observed ceiling of about
one thousand two hundred people per post; past it the list stops giving anything
back. This stops at that ceiling rather than pushing at it.

WHAT HAPPENS TO EVERYONE FOUND. They are recorded as events in your CRM's own log,
through your CRM's own resolver. Somebody your records do not have gets a
provisional record in `_staging/` and nothing is merged into anybody. See
gather_record.py.

WHAT IS PROVEN AND WHAT IS NOT. The export path is your CRM's, and your CRM's
tests cover it. The three page-reading paths are inherited from a system where
they were written and then run a handful of times, with the page selectors marked
as best guesses that were never confirmed against a live account. They are not
proven. That is why `--probe` exists and why it is the documented first step for
each one: run it, read what it says the page looks like, and only then trust the
reader.

Needs: Python 3.8 or newer. Everything except `export` needs Playwright.
"""

import csv
import random
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus

# What a member types to start Python. A Mac has `python3` and no plain `python`; Windows
# keeps `python`, exactly as before.
PY = "python3" if sys.platform == "darwin" else "python"

sys.path.insert(0, str(Path(__file__).resolve().parent))

import crm_paths                                            # noqa: E402
import safe_write                                           # noqa: E402
import gather_settings as gs                                # noqa: E402
import gather_limits                                        # noqa: E402
import gather_walk as walk                                  # noqa: E402
import gather_job as job                                    # noqa: E402
import gather_record as rec                                 # noqa: E402

try:
    import collect                                          # your CRM's collectors
except ImportError:
    collect = None


CONNECTIONS_PAGE = "https://www.linkedin.com/mynetwork/invite-connect/connections/"

# An observed ceiling, not a documented one. Past roughly this many, the list of
# people who reacted to a post stops handing anything else back however long you
# scroll. Written down so a run ends at a number somebody chose rather than in a
# loop that never finishes.
REACTION_CEILING = 1218

# The most one search can be paged out to on an ordinary account.
SEARCH_RESULT_CEILING = 1000


def collect_max():
    return int(gs.get().get("collect-max") or 300)


# ------------------------------------------------------------- the working file
# Everything read off a page is written to a file as it arrives, before anything
# is recorded. The file does three jobs at once: it is the place a run that stops
# halfway keeps what it already had, the record of what was on the page, and -- for
# connections -- the file your own collector reads. It is only ever appended to,
# so a run interrupted at any point can cost you the last row and never the file.

def sheet_path(name):
    return crm_paths.state_dir() / "gather" / (name + ".csv")


def sheet_seen(name, column="URL"):
    """The links already in a working file, so a second run skips them."""
    path = sheet_path(name)
    out = set()
    if not path.exists():
        return out
    try:
        with open(path, encoding="utf-8-sig", errors="replace", newline="") as fh:
            for row in csv.DictReader(fh):
                link = rec.clean_link((row.get(column) or "").strip())
                if link:
                    out.add(link)
    except OSError:
        pass
    return out


def sheet_append(name, header, rows):
    """Add rows to a working file, writing the header only when it is new."""
    if not rows:
        return 0
    path = sheet_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    fresh = not path.exists()
    with open(path, "a", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        if fresh:
            writer.writerow(header)
        for row in rows:
            writer.writerow(row)
        fh.flush()
    return len(rows)


# ---------------------------------------------------------- the search allowance
# Counted here because nothing else counts it. The platform does not tell you how
# much of it is left, and the moment you find out by running out is the moment it
# is gone for the rest of the month.

def allowance_path():
    return crm_paths.state_dir() / "gather_searches.json"


def _this_month(today=None):
    return (today or date.today()).isoformat()[:7]


def allowance():
    data = safe_write.read_json(allowance_path(), {})
    if not isinstance(data, dict):
        data = {}
    if data.get("month") != _this_month():
        return {"month": _this_month(), "used": 0, "stopped": False}
    return {"month": data.get("month"), "used": int(data.get("used") or 0),
            "stopped": bool(data.get("stopped"))}


def allowance_size():
    return int(gs.get().get("search-allowance") or 250)


def allowance_check():
    """May another search be run? -> (allowed, reason).

    Two ways to be out: the count kept here has reached the number you set, or a
    previous run watched the results collapse and wrote down that the allowance is
    spent. The second is the true one, because the count here is an estimate of a
    number nobody publishes.
    """
    state = allowance()
    if state["stopped"]:
        return False, ("a previous run saw the search allowance run out; it comes "
                       "back at the start of the next month")
    size = allowance_size()
    if state["used"] >= size:
        return False, ("the search allowance you set is spent, %d of %d this month"
                       % (state["used"], size))
    return True, "%d of %d used this month" % (state["used"], size)


def allowance_spend():
    state = allowance()
    state["used"] += 1
    safe_write.write_json(allowance_path(), state)
    return state["used"]


def allowance_stop():
    """Write down that the results collapsed, so nothing tries again this month."""
    state = allowance()
    state["stopped"] = True
    safe_write.write_json(allowance_path(), state)
    return state


# ------------------------------------------------------------- reading a page
# Every reader below is anchor-first: it finds people by the links to profiles,
# then reads the text around each one. It deliberately does not look for the
# platform's own class names, which are scrambled and change without notice.

PEOPLE_ON_PAGE = r"""(rootSelector) => {
  const tidy = s => (s || '').replace(/\s+/g, ' ').trim();
  const root = document.querySelector(rootSelector) || document.body;
  const links = [...root.querySelectorAll('a[href*="/in/"]')];

  // A card can hold links to OTHER people: the shared connections line reads
  // "Sam, Jo and 9 others you both know", and each of those names is a profile
  // link sitting inside somebody else's card. Left in, they arrive as people who
  // never appeared on the page and who inherit the headline of the card they sat
  // inside. So a short link inside a small "you both know" area is not a person.
  const isShared = a => {
    if (tidy(a.textContent).length >= 40) return false;
    let el = a.parentElement;
    for (let i = 0; i < 5 && el; i++) {
      const t = tidy(el.textContent);
      if (/mutual connection|you both know/i.test(t) && t.length < 140) return true;
      el = el.parentElement;
    }
    return false;
  };
  const inShared = (node, stop) => {
    let el = node.parentElement;
    for (let i = 0; i < 6 && el && el !== stop; i++) {
      const t = tidy(el.textContent);
      if (/mutual connection|you both know/i.test(t) && t.length < 140) return true;
      el = el.parentElement;
    }
    return false;
  };

  // Several links point at the same person: the whole card is one, the name is
  // another. Group them, keep the LONGEST for reading the card's text and the
  // SHORTEST for the person's name.
  const byPerson = {};
  for (const a of links) {
    if (isShared(a)) continue;
    const href = (a.getAttribute('href') || '');
    if (!href.includes('/in/')) continue;
    const id = href.split('?')[0].replace(/\/$/, '');
    const shown = tidy(a.textContent).split('View')[0].trim();
    if (!shown || shown.length < 2) continue;
    const g = byPerson[id] || (byPerson[id] = {id, href: href.split('?')[0],
                                               el: a, len: -1, name: ''});
    const len = tidy(a.textContent).length;
    if (len > g.len) { g.len = len; g.el = a; }
    if (!g.name || shown.length < g.name.length) g.name = shown;
  }

  const isDegree = t => /^[•·]?\s*(1st|2nd|3rd\+?)$/i.test(t);
  const isFurniture = t => t === '+' || t === '•'
    || /^View\b/i.test(t)
    || /^(Message|Connect|Follow|Following|Pending|Remove|More)$/i.test(t)
    || /^(Education|Current|Past|Status is|Premium)\b/i.test(t)
    || /mutual connection|you both know|followers|advanced filter/i.test(t);

  const out = [];
  for (const id in byPerson) {
    const g = byPerson[id];
    if (!g.name) continue;
    const parts = [];
    const walker = document.createTreeWalker(g.el, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      const t = tidy(node.nodeValue);
      if (!t || inShared(node, g.el)) continue;
      parts.push(t);
    }
    const fields = parts.filter(t => t !== g.name && !isDegree(t)
                                && !isFurniture(t) && /[a-z0-9]/i.test(t));
    out.push({
      id: id,
      name: g.name,
      link: g.href,
      headline: (fields[0] || '').slice(0, 120),
      place: (fields.slice(1).find(t => /,/.test(t)) || fields[1] || '').slice(0, 60),
    });
  }
  return out;
}"""


# What a probe reports about any of these pages: enough to tell you whether the
# reader above is looking at the right page, without collecting anybody.
PROBE_PAGE = r"""(rootSelector) => {
  const tidy = s => (s || '').replace(/\s+/g, ' ').trim();
  const root = document.querySelector(rootSelector) || document.body;
  return {
    address: location.href,
    heading: tidy((document.querySelector('h1') || {}).textContent || '').slice(0, 90),
    profileLinks: root.querySelectorAll('a[href*="/in/"]').length,
    listItems: root.querySelectorAll('[role="listitem"], li').length,
    sample: tidy(root.textContent).slice(0, 260),
  };
}"""


def _read_people(page, root="main"):
    try:
        return page.evaluate(PEOPLE_ON_PAGE, root)
    except Exception:                                       # noqa: BLE001
        return []


def _probe(page, root="main"):
    try:
        return page.evaluate(PROBE_PAGE, root)
    except Exception as err:                                # noqa: BLE001
        return {"error": str(err)[:200]}


def _show_probe(what, report):
    print("")
    print("  what the %s page looks like" % what)
    job.rule()
    for key in ("address", "heading", "profileLinks", "listItems", "cards",
                "controls", "error"):
        if key in report:
            print("  %-16s %s" % (key, report[key]))
    sample = report.get("sample") or report.get("firstCard")
    if sample:
        print("  %-16s %s" % ("first words", str(sample)[:180]))
    print("")
    print("  Nothing was collected and nothing was written. If the numbers above")
    print("  are zero, the reader is looking at the wrong part of the page and the")
    print("  selectors in this file need changing before you trust it.")


# ------------------------------------------------------------------- 1. export

def from_export(path, mode):
    """A file already on your machine, handed to your CRM's own collector.

    Nothing is parsed here. Your CRM reads exports already, and it reads them
    through the resolver, with the fingerprint that stops a row landing twice. A
    second reader for the same file shape would be a second answer to the same
    question, and the two would disagree the first time an export changed.

    There is no page to probe, so `--probe` reports what the file is and stops.
    """
    path = Path(str(path)).expanduser()
    if not path.exists():
        print("")
        print("  No such file: %s" % path)
        return 1
    if collect is None:
        print("")
        print("  Your CRM's collectors are not installed, so there is nothing to")
        print("  hand this file to.")
        return 1

    if mode == job.PROBE:
        try:
            with open(path, encoding="utf-8-sig", errors="replace") as fh:
                lines = [fh.readline().rstrip("\n") for _ in range(3)]
        except OSError as err:
            print("  could not read it: %s" % err)
            return 1
        print("")
        print("  %s" % path)
        job.rule()
        for line in lines:
            if line:
                print("  %s" % line[:150])
        print("")
        print("  Nothing was read into your records. This file never leaves your")
        print("  machine, so there is no page to look at and nothing to confirm.")
        return 0

    stats = collect.run("connections", path, dry_run=(mode != job.COMMIT))
    print("")
    print("  %s%s" % (path, "   (plan only, nothing written)" if mode != job.COMMIT else ""))
    job.rule()
    for key in ("read", "written", "already there", "new people", "staged",
                "nobody attached", "skipped"):
        print("  %-18s %d" % (key, stats.get(key, 0)))
    for why, n in (stats.get("_reasons") or {}).items():
        print("      skipped, %-22s %d" % (why, n))
    return 0


# -------------------------------------------------------------- 2. connections

def from_connections(page, mode, tally):
    """Your own first-degree connections, read off your own page.

    The list is virtualised, which means the page only holds the rows you can see
    and throws away the ones you have scrolled past. Reading the page once at the
    end therefore returns the last screenful and nothing else. So this reads AS it
    scrolls and keeps what it has seen, which is the only shape that works on a
    list of this kind.

    Rows are appended to a working file as they arrive, in the same shape as a
    connections export, and on `--commit` that file is handed to your CRM's own
    collector. The reading is new; the landing is the one you already had.
    """
    walk.open_page(page, CONNECTIONS_PAGE)
    if mode == job.PROBE:
        _show_probe("connections", _probe(page, "main"))
        return 0

    ceiling = collect_max()
    already = sheet_seen("connections")
    seen, fresh_rows = {}, []
    still = 0

    for _round in range(400):
        ok, why = gather_limits.can_act("look")
        if not ok:
            tally.note("Stopped part way: %s. What was read is already in the "
                       "working file." % why)
            break
        gather_limits.record("look")

        rows = _read_people(page, "main")
        before = len(seen)
        batch = []
        for row in rows:
            link = rec.clean_link(row.get("link"))
            if not link or link in seen or link in already:
                continue
            seen[link] = row
            batch.append(row)
            if len(seen) >= ceiling:
                break
        if batch:
            sheet_append("connections",
                         ["First Name", "Last Name", "URL", "Company",
                          "Position", "Connected On"],
                         [_export_row(r) for r in batch])
            fresh_rows.extend(batch)
        grew = len(seen) - before
        tally.rows["people read"] = len(seen)

        if len(seen) >= ceiling:
            tally.note("Stopped at the %d you set as one run's worth." % ceiling)
            break
        moved = _scroll_list(page)
        time.sleep(random.uniform(0.9, 1.8))
        if not grew and not moved:
            still += 1
            if still >= 3:
                break
        else:
            still = 0

    print("")
    print("  read %d people, %d of them new to the working file" % (len(seen), len(fresh_rows)))
    print("  working file: %s" % sheet_path("connections"))

    if mode != job.COMMIT:
        print("")
        print("  Plan only. The working file was written, because a run that")
        print("  scrolls for ten minutes and keeps nothing has wasted the read.")
        print("  Nothing went into your records.")
        return 0

    if collect is None:
        print("  Your CRM's collectors are not installed, so the file stays where")
        print("  it is until they are.")
        return 1
    stats = collect.run("connections", sheet_path("connections"), dry_run=False)
    print("")
    for key in ("read", "written", "already there", "new people", "staged"):
        print("  %-18s %d" % (key, stats.get(key, 0)))
    return 0


def _split_name(full):
    parts = [p for p in str(full or "").split() if p]
    if not parts:
        return "", ""
    return parts[0], " ".join(parts[1:])


def _export_row(row):
    first, last = _split_name(row.get("name"))
    headline = row.get("headline") or ""
    company, position = "", headline
    if " at " in headline:
        position, company = headline.split(" at ", 1)
    return [first, last, rec.clean_link(row.get("link")), company.strip(),
            position.strip(), ""]


SCROLL_LIST = r"""() => {
  const scrollable = el => {
    const cs = getComputedStyle(el);
    return (cs.overflowY === 'auto' || cs.overflowY === 'scroll')
        && el.scrollHeight > el.clientHeight + 30;
  };
  const main = document.querySelector('main') || document.body;
  let box = null;
  for (const d of main.querySelectorAll('*')) { if (scrollable(d)) { box = d; break; } }
  if (box) {
    const was = box.scrollTop;
    box.scrollTop = Math.min(box.scrollHeight, was + Math.round(box.clientHeight * 0.85));
    if (box.scrollTop > was) return true;
  }
  const was = window.scrollY;
  window.scrollBy(0, Math.round(window.innerHeight * 0.85));
  return window.scrollY > was;
}"""


def _scroll_list(page):
    try:
        return bool(page.evaluate(SCROLL_LIST))
    except Exception:                                       # noqa: BLE001
        return False


# ------------------------------------------------------------------- 3. search

def search_address(terms):
    text = str(terms or "").strip()
    if text.startswith("http"):
        return text
    if text.startswith("/search/"):
        return "https://www.linkedin.com" + text
    return "https://www.linkedin.com/search/results/people/?keywords=" + quote_plus(text)


# Two signs the allowance has run out, and either one is enough: the page says so
# in as many words, or a query that should return a page of people returns three.
COLLAPSE_CHECK = r"""() => {
  const body = (document.body.innerText || '');
  return {
    told: /commercial use limit|you.{0,3}ve reached the (monthly|weekly|maximum) limit|upgrade to (premium|sales navigator) to (search|see)|reached the maximum number of/i.test(body),
    people: (document.querySelector('main') || document.body).querySelectorAll('a[href*="/in/"]').length,
  };
}"""


def _collapsed(page):
    try:
        seen = page.evaluate(COLLAPSE_CHECK)
    except Exception:                                       # noqa: BLE001
        return False
    return bool(seen.get("told")) and int(seen.get("people") or 99) <= 3


def _next_page(page):
    try:
        button = page.get_by_role("button", name=re.compile(r"^next$", re.I))
        if not button.count() or not button.first.is_enabled():
            return False
        button.first.scroll_into_view_if_needed(timeout=4_000)
        time.sleep(random.uniform(0.6, 1.2))
        button.first.click()
        time.sleep(random.uniform(2.5, 4.0))
        return True
    except Exception:                                       # noqa: BLE001
        return False


def from_search(page, terms, mode, tally, recorder):
    """One broad query, read as deep as it goes.

    The allowance counts SEARCHES, not results, so many narrow queries is the
    expensive shape and one broad query paged deep is the cheap one. This runs one
    query and pages it.

    It refuses BEFORE navigating if the allowance is already spent, because the
    only way to find out by trying is to spend one. If the results collapse part
    way through, it writes down that the allowance is gone and stops, rather than
    paging through a wall of three results at a time.
    """
    if not terms:
        print("")
        print("  Give it something to search for:")
        print("      %s gather.py find search \"operations manager manufacturing\"" % PY)
        return 2

    ok, why = allowance_check()
    if not ok:
        print("")
        print("  Not now: %s." % why)
        print("  Nothing was searched, so nothing was spent.")
        return 1

    # A probe on this source is the one probe that costs you something, because
    # the allowance counts the SEARCH and not the reading, and a probe searches.
    # So it is asked for and counted exactly like a real run. Reporting a probe
    # as free here would make the count wrong for every run after it.
    ok, why = gather_limits.can_act("search")
    if not ok:
        print("")
        print("  Not now: %s." % why)
        return 1

    walk.open_page(page, search_address(terms))
    gather_limits.record("search", note=str(terms)[:60])
    used = allowance_spend()
    print("")
    print("  searched once. %d of about %d this month by this count."
          % (used, allowance_size()))

    if mode == job.PROBE:
        report = _probe(page, "main")
        report["collapsed"] = _collapsed(page)
        _show_probe("search results", report)
        print("")
        print("  Nobody was collected and nothing went into your records. The one")
        print("  count above did change, because the search happened whether or")
        print("  not anything was read from it.")
        return 0

    if _collapsed(page):
        allowance_stop()
        print("")
        print("  The results collapsed to a handful, which is what happens when the")
        print("  monthly search allowance is spent. That is written down, and no")
        print("  further searches will be attempted until the next month.")
        return 1

    ceiling = min(collect_max(), SEARCH_RESULT_CEILING)
    seen = {}
    for _page_number in range(120):
        ok, why = gather_limits.can_act("look")
        if not ok:
            tally.note("Stopped part way: %s." % why)
            break
        gather_limits.record("look")

        try:
            page.wait_for_selector('main a[href*="/in/"]', timeout=15_000)
        except Exception:                                   # noqa: BLE001
            pass
        for _ in range(4):
            try:
                page.mouse.wheel(0, 1600)
            except Exception:                               # noqa: BLE001
                break
            time.sleep(random.uniform(0.6, 1.0))

        rows = _read_people(page, "main")
        batch = []
        for row in rows:
            link = rec.clean_link(row.get("link"))
            if not link or link in seen:
                continue
            seen[link] = row
            batch.append(row)
            if len(seen) >= ceiling:
                break
        if batch:
            sheet_append("search", ["Name", "URL", "Headline", "Place", "Terms"],
                         [[r.get("name"), rec.clean_link(r.get("link")),
                           r.get("headline"), r.get("place"), str(terms)[:80]]
                          for r in batch])
            _record_people(recorder, batch, rec.FOUND,
                           lambda r: rec.fp_found("search", rec.clean_link(r.get("link"))),
                           {"where": "search", "terms": str(terms)[:80]})
        tally.rows["people read"] = len(seen)
        if len(seen) >= ceiling:
            break
        if not _next_page(page):
            break
        walk.pause()

    print("")
    print("  read %d people" % len(seen))
    print("  working file: %s" % sheet_path("search"))
    return 0


# ---------------------------------------------------------------- 4. reactions

OPEN_REACTIONS = [
    'a:has-text("reaction")',
    'button:has-text("reaction")',
    'button[aria-label*="reaction" i]',
    'button[aria-label*="see who reacted" i]',
    '.social-details-social-counts__reactions button',
    '.social-details-social-counts__count-value',
]

READ_REACTORS = r"""() => {
  const tidy = s => (s || '').replace(/\s+/g, ' ').trim();
  const box = document.querySelector('[role="dialog"]') || document.body;
  const out = {};
  for (const a of box.querySelectorAll('a[href*="/in/"]')) {
    const href = a.getAttribute('href'); if (!href) continue;
    const id = href.split('?')[0].replace(/\/$/, '');
    const name = tidy(a.textContent);
    if (!name) continue;
    const row = a.closest('li') || a.closest('div[class*="entity"]') || a.parentElement;
    let headline = tidy(row ? row.textContent : '');
    if (headline.startsWith(name)) headline = tidy(headline.slice(name.length));
    headline = headline.replace(/^(•|·|\|)\s*/, '').slice(0, 120);
    if (!out[id] || name.length < out[id].name.length)
      out[id] = {id: id, name: name, link: href.split('?')[0], headline: headline, place: ''};
  }
  return Object.values(out);
}"""

SCROLL_REACTORS = r"""() => {
  const dlg = document.querySelector('[role="dialog"]');
  if (!dlg) return false;
  const scrollable = el => {
    const cs = getComputedStyle(el);
    return (cs.overflowY === 'auto' || cs.overflowY === 'scroll')
        && el.scrollHeight > el.clientHeight + 30;
  };
  let box = null;
  for (const d of dlg.querySelectorAll('*')) { if (scrollable(d)) { box = d; break; } }
  if (!box && scrollable(dlg)) box = dlg;
  if (!box) return false;
  const was = box.scrollTop;
  box.scrollTop = Math.min(box.scrollHeight, was + Math.round(box.clientHeight * 0.85));
  return box.scrollTop > was;
}"""


def _open_reactions(page):
    """Open the list of people who reacted. Returns True if it opened.

    Several spellings are tried because the control is a count with no label on
    some layouts and a labelled button on others. If none of them opens a list,
    that is reported as a fact about the page rather than treated as nobody having
    reacted.
    """
    for selector in OPEN_REACTIONS:
        try:
            found = page.locator(selector)
            if not found.count():
                continue
            control = found.first
            control.scroll_into_view_if_needed(timeout=3_000)
            time.sleep(random.uniform(0.5, 1.1))
            control.click(timeout=6_000)
            page.wait_for_selector('[role="dialog"] a[href*="/in/"]', timeout=12_000)
            return True
        except Exception:                                   # noqa: BLE001
            continue
    return False


def gather_reactors(page, ceiling=REACTION_CEILING, on_batch=None, pause=None,
                    allowed=None, rounds=600):
    """Collect the people in the reactions list as it scrolls.

    The list is virtualised: rows above and below what you can see are not in the
    page at all. Reading once at the end returns the last screenful and nothing
    else, which looks like a working reader that quietly loses ninety per cent of
    a post.

    `ceiling` is never exceeded. `pause` is how long to wait between reads and
    exists as a setting only so the tests can run without waiting hours; leave it
    alone and it waits like a person waits. `allowed` is asked before each read,
    which is how the doorman can stop a long scroll part way through.
    """
    ceiling = min(int(ceiling), REACTION_CEILING)
    seen = {}
    still = 0
    for _step in range(rounds):
        if allowed is not None and not allowed():
            break
        try:
            rows = page.evaluate(READ_REACTORS)
        except Exception:                                   # noqa: BLE001
            break
        before = len(seen)
        batch = []
        for row in rows:
            link = rec.clean_link(row.get("link"))
            if not link or link in seen:
                continue
            seen[link] = row
            batch.append(row)
            if len(seen) >= ceiling:
                break
        if batch and on_batch:
            on_batch(batch)
        if len(seen) >= ceiling:
            break
        try:
            moved = bool(page.evaluate(SCROLL_REACTORS))
        except Exception:                                   # noqa: BLE001
            moved = False
        if pause is None:
            time.sleep(random.uniform(0.7, 1.3))
        else:
            pause()
        if len(seen) == before and not moved:
            still += 1
            if still >= 3:
                break
        else:
            still = 0
    return list(seen.values())[:ceiling]


def from_reactions(page, post_url, mode, tally, recorder):
    """Everyone who reacted to one post.

    These people are the warmest strangers there are: they read something on the
    subject and put their name to it. They are also the most expensive to collect,
    because it is a lot of reading about a lot of people in one sitting, which is
    the shape most likely to be noticed. Treat it as the occasional job, not the
    daily one.
    """
    if not post_url:
        print("")
        print("  Give it the address of a post:")
        print("      %s gather.py find reactions https://www.linkedin.com/posts/..." % PY)
        return 2

    walk.open_page(page, str(post_url).split("?")[0])
    time.sleep(random.uniform(1.5, 3.0))
    walk.scroll(page)

    opened = _open_reactions(page)
    if mode == job.PROBE:
        report = _probe(page, '[role="dialog"]' if opened else "main")
        report["reactions list opened"] = opened
        _show_probe("post reactions", report)
        if not opened:
            print("")
            print("  The list did not open. Either nobody has reacted, or the")
            print("  control that opens it is spelled differently on your account")
            print("  and the list of spellings in this file needs one more.")
        return 0

    if not opened:
        print("")
        print("  Could not open the list of people who reacted. Run the probe.")
        return 1

    ceiling = min(collect_max(), REACTION_CEILING)

    def allowed():
        ok, why = gather_limits.can_act("look")
        if not ok:
            tally.note("Stopped part way: %s." % why)
            return False
        gather_limits.record("look")
        return True

    def landed(batch):
        sheet_append("reactions", ["Name", "URL", "Headline", "Post"],
                     [[r.get("name"), rec.clean_link(r.get("link")),
                       r.get("headline"), str(post_url)[:120]] for r in batch])
        _record_people(recorder, batch, rec.ENGAGED,
                       lambda r: rec.fp_engaged(post_url, rec.clean_link(r.get("link"))),
                       {"where": "reactions", "post": str(post_url)[:200]})

    rows = gather_reactors(page, ceiling=ceiling, on_batch=landed, allowed=allowed)
    tally.rows["people read"] = len(rows)
    print("")
    print("  read %d people" % len(rows))
    if len(rows) >= REACTION_CEILING:
        print("  That is the observed ceiling for one post. There is no more to read.")
    print("  working file: %s" % sheet_path("reactions"))
    return 0


# ---------------------------------------------------------------------- shared

def _record_people(recorder, rows, type_, fingerprint_of, payload):
    for row in rows:
        link = rec.clean_link(row.get("link"))
        body = dict(payload)
        if row.get("headline"):
            body["role"] = row["headline"]
        if row.get("place"):
            body["place"] = row["place"]
        recorder.add(type_, fingerprint_of(row),
                     rec.identifiers(link=link, name=row.get("name")),
                     payload=body,
                     ts=datetime.now(timezone.utc).isoformat(timespec="seconds"))


# ------------------------------------------------------------------------- run

SOURCES = ("export", "connections", "search", "reactions")


def run(argv):
    """`python gather.py find <source> [...] [--probe] [--commit]`"""
    mode = job.mode_of(argv)
    source = (argv[2].strip().lower() if len(argv) > 2 else "")
    argument = argv[3] if len(argv) > 3 and not argv[3].startswith("--") else ""

    if source not in SOURCES:
        print("")
        print("  Which source? One of: %s" % ", ".join(SOURCES))
        print("")
        print("      %s gather.py find export <file.csv>" % PY)
        print("      %s gather.py find connections" % PY)
        print("      %s gather.py find search \"<terms>\"" % PY)
        print("      %s gather.py find reactions <post-url>" % PY)
        print("")
        return 2

    job.banner("find %s" % source, mode)

    if not job.records_ready():
        return 1

    # READING A FILE ON YOUR OWN MACHINE IS NOT SOMETHING THE DOORMAN GOVERNS.
    #
    # He decides what may reach a website. An export sitting in your downloads
    # folder reaches none: no sign-in, no page, no allowance spent, nobody on the
    # other end. Gating it would mean the one step in this layer that genuinely
    # cannot go wrong gets refused because it is Sunday -- and it is the step every
    # member is told to start with.
    #
    # This is not an exception carved out of the gate. It is a job outside what the
    # gate is for, and the difference matters: every job that touches the outside
    # world still asks, without exception, and the answer is never negotiable.
    if source == "export":
        return from_export(argument, mode)

    if not job.doorman("look"):
        return 1

    tally = job.Tally()
    recorder = rec.Recorder(plan=(mode != job.COMMIT), source="gather:find " + source)
    code = 1
    with job.one_window() as page:
        if page is None:
            return 1
        try:
            if source == "connections":
                code = from_connections(page, mode, tally)
            elif source == "search":
                code = from_search(page, argument, mode, tally, recorder)
            elif source == "reactions":
                code = from_reactions(page, argument, mode, tally, recorder)
        except KeyboardInterrupt:
            print("")
            print("  Stopped by you. What was read is in the working file.")
    recorder.close()
    if source != "connections" and mode != job.PROBE:
        recorder.show()
    tally.show()
    if mode == job.COMMIT:
        print("")
        print("  Written into your own records. Nothing was sent to anybody, and")
        print("  nobody was contacted.")
    return code
