"""
gather_ask.py - asking somebody to connect, which is the only outward action in
this layer.

    python gather.py ask [--probe] [--commit]

A connection request carries none of your words. There is no note, no greeting and
no line about what you do, and that is a decision rather than an omission. A
request with a note is a message you have written to a stranger; a request without
one is a door you have knocked on. This layer knocks. Writing to people is a
separate job in a later part of the series, held back on purpose so that the part
that reaches out and the part that speaks are turned on separately.

WHERE THE QUEUE COMES FROM. Not a list of its own. It is read out of your CRM's
event log: everybody a `find` job brought back, minus everybody you are already
connected to, minus everybody you have already asked, minus anybody you have put
on hold. Your log already had the words `held` and `released` in it, so a person
you decided to leave alone is left alone by this without you telling it twice.

Oldest first. A queue that takes the newest first never reaches the bottom, and
the bottom is where the people you looked for on purpose ended up.

THREE CHECKS BEFORE ANY REQUEST, AND ALL THREE MATTER

  1  the doorman, for a profile read, then again for the request itself
  2  the page, read live, because your records can be out of date about whether
     you are already connected and the page never is
  3  the control, matched to THIS person's own address

The third one is the one that looks like fussiness and is not. A profile page
carries other people's connect controls in the sidebar under people you might
know. A reader that clicks the first control whose label says connect can send a
request to somebody who was never in the queue, and you will not find out. So the
control has to carry this person's own address, and if it does not, the person is
skipped and nothing is clicked.

NOTHING HERE TYPES. There is no place in this file where text is entered into a
page, which is what makes the promise at the top checkable rather than a claim.
The tests check it.

WHAT IS PROVEN AND WHAT IS NOT. The reasoning is inherited from a system where the
same lane ran often. The exact controls on your account still have to be
confirmed, which is what `--probe` is for. Run it on one person before you commit
to anything.

Needs: Python 3.8 or newer, plus Playwright.
"""

import random
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

# What a member types to start Python. A Mac has `python3` and no plain `python`; Windows
# keeps `python`, exactly as before.
PY = "python3" if sys.platform == "darwin" else "python"

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gather_limits                                        # noqa: E402
import gather_walk as walk                                  # noqa: E402
import gather_job as job                                    # noqa: E402
import gather_record as rec                                 # noqa: E402

try:
    import ledger
except ImportError:
    ledger = None


# What the page says about your relationship with this person. Read from the
# controls it offers, because the controls are what the page actually believes.
WHAT_THE_PAGE_OFFERS = r"""() => {
  const tidy = s => (s || '').replace(/\s+/g, ' ').trim();
  const h1 = document.querySelector('main h1') || document.querySelector('h1');
  const isAction = b => {
    const a = b.getAttribute('aria-label') || '';
    return /invite .* to connect|^message |^follow |more actions/i.test(a) || a === 'More';
  };
  // Climb from the person's name to the nearest area that holds their own
  // controls, so a Follow button beside somebody suggested in the sidebar is
  // never read as a control belonging to this person.
  let scope = h1;
  for (let i = 0; i < 7 && scope; i++) {
    if ([...scope.querySelectorAll('button, a[role="button"]')].some(isAction)) break;
    scope = scope.parentElement;
  }
  scope = scope || document;
  const controls = [...scope.querySelectorAll('button, a[role="button"]')];
  const has = re => controls.some(b => re.test(b.getAttribute('aria-label') || ''));
  return {
    name: tidy((h1 || {}).textContent || '').slice(0, 60),
    connect: has(/invite .* to connect/i),
    pending: has(/pending/i),
    message: has(/^message /i),
    follow: has(/^follow /i),
    more: has(/more actions/i)
        || controls.some(b => (b.getAttribute('aria-label') || '') === 'More'),
    labels: controls.map(b => (b.getAttribute('aria-label') || '').slice(0, 50))
                    .filter(Boolean).slice(0, 12),
  };
}"""


def _standing(offered):
    if offered.get("connect"):
        return "not connected"
    if offered.get("pending"):
        return "already asked"
    if offered.get("message"):
        return "already connected"
    if offered.get("follow"):
        return "follow only"
    return "unclear"


def _handle(link):
    """The last part of a profile address, which is what the control carries."""
    tail = str(link or "").split("/in/")[-1]
    return tail.split("/")[0].split("?")[0].strip().lower()


# ---------------------------------------------------------------- the queue

def queue():
    """Everybody worth asking, oldest first, read out of your own log.

    One pass over the log. Reading it once per person would read the whole file
    per person, which is slow at a thousand events and slower every run.
    """
    if ledger is None:
        return []
    people = {}
    for ev in ledger.events():
        idents = ev.get("identifiers") or []
        link = ""
        for i in idents:
            link = rec.clean_link(i)
            if link:
                break
        key = link or ev.get("person")
        if not key:
            continue
        row = people.setdefault(key, {"link": link, "name": "", "first_seen": "",
                                      "asked": False, "connected": False,
                                      "held": "", "released": "", "role": ""})
        if link and not row["link"]:
            row["link"] = link
        for i in idents:
            if i and "/" not in str(i) and "@" not in str(i) and not row["name"]:
                row["name"] = str(i)
        kind = ev.get("type")
        when = str(ev.get("ts") or "")
        if kind in (rec.FOUND, rec.ENGAGED):
            if not row["first_seen"] or when < row["first_seen"]:
                row["first_seen"] = when
            role = (ev.get("payload") or {}).get("role")
            if role and not row["role"]:
                row["role"] = role
        elif kind == rec.REQUESTED:
            row["asked"] = True
        elif kind == rec.CONNECTED:
            row["connected"] = True
        elif kind == "held":
            row["held"] = when
        elif kind == "released":
            row["released"] = when

    out = []
    for key, row in people.items():
        if not row["link"]:
            continue                    # no address, no page to open
        if row["connected"] or row["asked"]:
            continue
        if row["held"] and row["held"] > (row["released"] or ""):
            continue                    # you put them on hold; that stands
        if not row["first_seen"]:
            continue                    # nothing found them; they came from elsewhere
        out.append(row)
    out.sort(key=lambda r: r["first_seen"])
    return out


# --------------------------------------------------------------- one person

def look_at(page, person):
    """Open one profile and read what it offers. No clicks."""
    walk.open_page(page, person["link"])
    time.sleep(random.uniform(1.2, 2.6))
    walk.scroll(page)
    try:
        return page.evaluate(WHAT_THE_PAGE_OFFERS)
    except Exception as err:                                # noqa: BLE001
        return {"error": str(err)[:200]}


def send_request(page, person):
    """Ask this person to connect. Returns what happened, as a word.

    -> "sent" | "already connected" | "already asked" | "no control" | "refused"

    The control is matched on this person's own address. If no such control is on
    the page, nothing is clicked. A near-miss here sends a request to a stranger
    and there is no way to tell afterwards which of them was meant.
    """
    handle = _handle(person.get("link"))
    if not handle:
        return "no control"

    control = None
    try:
        found = page.locator('main a[href*="vanityName=%s"]' % handle)
        if found.count():
            control = found.first
    except Exception:                                       # noqa: BLE001
        control = None

    if control is None:
        # On some layouts the control sits under the profile's own More menu.
        # Opening that menu is safe: it holds this person's actions and nobody
        # else's, so a control found inside it cannot belong to a stranger.
        try:
            more = page.locator("main").get_by_role(
                "button", name=re.compile(r"^more$", re.I))
            if more.count():
                more.first.click(timeout=6_000)
                time.sleep(1.0)
                menu_text = _menu_text(page)
                if re.search(r"\bpending\b", menu_text, re.I):
                    return "already asked"
                if re.search(r"remove connection", menu_text, re.I):
                    return "already connected"
                inside = page.locator('.artdeco-dropdown__content--is-open, div[role="menu"]')
                if inside.count():
                    named = inside.first.get_by_role(
                        "button", name=re.compile(r"invite .* to connect|^connect$", re.I))
                    if named.count():
                        control = named.first
        except Exception:                                   # noqa: BLE001
            control = None

    if control is None:
        return "no control"

    def dialog_open():
        try:
            return page.locator('[role="dialog"], .artdeco-modal').count() > 0
        except Exception:                                   # noqa: BLE001
            return False

    try:
        control.click(timeout=8_000)
    except Exception:                                       # noqa: BLE001
        return "no control"
    time.sleep(1.3)
    if not dialog_open():
        # A click that moves focus without activating is a real behaviour on some
        # layouts, and it looks exactly like a control that is not there. Try the
        # keyboard before deciding nothing happened.
        try:
            control.press("Enter", timeout=3_000)
            time.sleep(1.3)
        except Exception:                                   # noqa: BLE001
            pass
    if not dialog_open():
        return "no control"

    box = page.locator('[role="dialog"], .artdeco-modal').first
    send = None
    for name in (r"send without a note", r"^send$", r"^send\b"):
        try:
            found = box.get_by_role("button", name=re.compile(name, re.I))
            if found.count():
                send = found.first
                break
        except Exception:                                   # noqa: BLE001
            continue
    if send is None:
        return "refused"
    try:
        send.click(timeout=6_000)
    except Exception:                                       # noqa: BLE001
        return "refused"
    time.sleep(1.2)

    said = _dialog_text(page)
    if re.search(r"weekly invitation limit|reached the (weekly )?limit|too many invitations",
                 said, re.I):
        return "refused"
    if re.search(r"email (address )?to (connect|invite)", said, re.I):
        return "refused"
    return "sent"


def _menu_text(page):
    try:
        return page.evaluate(
            "() => { const m = document.querySelector("
            "'.artdeco-dropdown__content--is-open, div[role=\"menu\"]');"
            " return m ? (m.innerText || '').replace(/\\s+/g, ' ') : ''; }") or ""
    except Exception:                                       # noqa: BLE001
        return ""


def _dialog_text(page):
    try:
        return page.evaluate(
            "() => { const d = document.querySelector('[role=\"dialog\"], .artdeco-modal');"
            " return d ? (d.innerText || '').replace(/\\s+/g, ' ').slice(0, 400) : ''; }") or ""
    except Exception:                                       # noqa: BLE001
        return ""


# ------------------------------------------------------------------------- run

def run(argv):
    mode = job.mode_of(argv)
    job.banner("ask", mode)

    if not job.records_ready():
        return 1
    if not job.doorman("profile"):
        return 1
    if mode == job.COMMIT and not job.outward_allowed():
        return 1

    waiting = queue()
    if not waiting:
        print("")
        print("  Nobody is waiting. Everybody your records know about is either")
        print("  connected to you, already asked, or on hold. Bring some people")
        print("  back first:")
        print("      %s gather.py find connections --commit" % PY)
        print("")
        return 0

    print("")
    print("  %d waiting, oldest first" % len(waiting))
    job.rule()
    for row in waiting[:10]:
        print("  %-28s %s" % ((row["name"] or "(no name yet)")[:28],
                              row["link"]))
    if len(waiting) > 10:
        print("  ... and %d more" % (len(waiting) - 10))

    if mode == job.PLAN:
        ok, why = gather_limits.can_act("request")
        print("")
        print("  The doorman on requests right now: %s" % ("yes, %s" % why if ok else why))
        print("")
        print("  Nothing was opened and nothing was sent. To look at the first")
        print("  person's page without touching anything:")
        print("      %s gather.py ask --probe" % PY)
        print("")
        return 0

    tally = job.Tally()
    recorder = rec.Recorder(plan=False, source="gather:ask")

    with job.one_window() as page:
        if page is None:
            return 1
        try:
            for person in waiting:
                ok, why = gather_limits.can_act("profile")
                if not ok:
                    tally.note("Stopped: %s." % why)
                    break

                offered = look_at(page, person)
                gather_limits.record("profile")
                tally.add("profiles read")

                if mode == job.PROBE:
                    print("")
                    print("  %s" % person["link"])
                    job.rule()
                    print("  name on the page    %s" % offered.get("name", ""))
                    print("  standing            %s" % _standing(offered))
                    print("  controls offered    %s" % ", ".join(offered.get("labels") or []))
                    print("")
                    print("  Nothing was clicked and nothing was written. If the")
                    print("  standing above is unclear, the labels tell you what the")
                    print("  page really offers and this file needs to know about it.")
                    break                       # one person is enough to look at

                standing = _standing(offered)
                if standing != "not connected":
                    tally.add("skipped, %s" % standing)
                    walk.pause()
                    continue

                ok, why = gather_limits.can_act("request")
                if not ok:
                    tally.note("Stopped before sending: %s." % why)
                    break

                outcome = send_request(page, person)
                tally.add(outcome)
                if outcome == "sent":
                    # Counted AFTER it happened, never before. Counting an
                    # intention means a run that stops halfway has spent an
                    # allowance it never used, and every run after it behaves as
                    # though it did.
                    gather_limits.record("request", note=person["link"])
                    recorder.add(
                        rec.REQUESTED,
                        rec.fp_request(person["link"], date.today().isoformat()),
                        rec.identifiers(link=person["link"], name=person.get("name")),
                        payload={"where": "gather ask"},
                        ts=datetime.now(timezone.utc).isoformat(timespec="seconds"))
                walk.pause()
        except KeyboardInterrupt:
            print("")
            print("  Stopped by you. Everything already sent is recorded.")

    recorder.close()
    tally.show("what happened")
    if mode == job.COMMIT:
        print("")
        print("  Every request went out with nothing written on it. Nobody was")
        print("  sent a message.")
    return 0
