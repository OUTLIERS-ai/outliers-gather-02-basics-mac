"""
gather_undo.py - taking back requests nobody answered.

    python gather.py undo [--probe] [--commit]

THE SAFEST LIVE ACTION THERE IS, WHICH IS WHY IT GOES FIRST. Everything this job
does is to your own requests. Nobody is contacted, nobody is asked for anything,
and the only person affected is you. That makes it the sensible action to run for
real before any other, because it is the one where being wrong costs least. If the
controls on your account are spelled differently to the ones assumed here, this is
where you want to find out.

WHY TAKE THEM BACK AT ALL. Requests nobody has answered do not sit there for free.
There is a ceiling on how many can be outstanding at once, and once you are at it,
every new request fails whatever your own limits say. Old requests are also the
least likely to be accepted: somebody who has not answered in a month is not
about to. Clearing them is what keeps room to ask anybody new.

HOW OLD IS OLD. You chose the number when you installed this layer, and it lives
in your settings as `undo-after-days`. Nothing here has an opinion about it beyond
starting you somewhere unremarkable.

READING THE AGE OFF A CARD. The card says how long ago the request was sent, and it
also carries the person's headline, which frequently contains a number of years.
The age is read from the sent clause and nowhere else, because a reader that takes
the first number it sees decides a request is twenty years old and takes it back.

WHAT IS PROVEN AND WHAT IS NOT. The page and the way it is loaded are inherited
from a system where this ran regularly. The exact controls still have to be
confirmed against your own account. Run the probe first, read what it says, and
only then commit.

Needs: Python 3.8 or newer, plus Playwright.
"""

import random
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gather_settings as gs                                # noqa: E402
import gather_limits                                        # noqa: E402
import gather_walk as walk                                  # noqa: E402
import gather_job as job                                    # noqa: E402
import gather_pending as pending                            # noqa: E402
import gather_record as rec                                 # noqa: E402


def stale_after():
    return int(gs.get().get("undo-after-days") or 21)


def take_back(page, card):
    """Take back one request. Returns True only if it is gone afterwards.

    The control carries the person's own name, so there is one per person and it
    cannot be confused with anybody else's. After the click there is usually a
    dialog asking whether you meant it, and after that the control should no
    longer exist. That last check is the only honest way to know: a click that
    landed on nothing and a click that worked look identical from the outside.
    """
    label = card.get("label") or ""
    if not label:
        return False
    try:
        control = page.locator('a[aria-label="%s"]' % label.replace('"', '\\"'))
        if not control.count():
            return False
        control.first.scroll_into_view_if_needed(timeout=5_000)
        time.sleep(random.uniform(0.6, 1.4))
        control.first.click(timeout=8_000)
    except Exception:                                       # noqa: BLE001
        return False

    time.sleep(random.uniform(0.8, 1.6))
    try:
        confirm = page.get_by_role("button", name=re.compile(r"^withdraw$", re.I))
        if confirm.count():
            confirm.first.click(timeout=6_000)
    except Exception:                                       # noqa: BLE001
        pass

    for _ in range(3):
        time.sleep(random.uniform(0.7, 1.3))
        try:
            if page.locator('a[aria-label="%s"]' % label.replace('"', '\\"')).count() == 0:
                return True
        except Exception:                                   # noqa: BLE001
            return False
    return False


def run(argv):
    mode = job.mode_of(argv)
    job.banner("undo", mode)

    if not job.records_ready():
        return 1
    if not job.doorman("look"):
        return 1
    if mode == job.COMMIT and not job.outward_allowed():
        return 1

    days = stale_after()
    tally = job.Tally()
    recorder = rec.Recorder(plan=(mode != job.COMMIT), source="gather:undo")

    with job.one_window() as page:
        if page is None:
            return 1
        try:
            pending.open_list(page)
            gather_limits.record("look")

            if mode == job.PROBE:
                report = pending.probe_report(page)
                print("")
                print("  what the sent-requests page looks like")
                job.rule()
                for key in ("address", "heading", "cards", "controls", "links", "error"):
                    if key in report:
                        print("  %-16s %s" % (key, report[key]))
                if report.get("firstCard"):
                    print("  %-16s %s" % ("first card", report["firstCard"][:180]))
                sample = pending.read_cards(page)[:5]
                if sample:
                    print("")
                    print("  the first few, as this file reads them")
                    job.rule()
                    for row in sample:
                        print("  %-26s %-42s %s"
                              % ((row.get("name") or "?")[:26],
                                 (row.get("link") or "")[:42],
                                 "age unreadable" if row.get("age_days") is None
                                 else "%d days" % row["age_days"]))
                print("")
                print("  Nothing was clicked and nothing was written. If the ages")
                print("  above are unreadable, the sent clause on your account is")
                print("  worded differently and this file needs to know about it.")
                return 0

            total = pending.load_whole_list(page, say=print)
            cards = pending.read_cards(page)
            tally.add("requests outstanding", len(cards) or total)

            unreadable = [c for c in cards if c.get("age_days") is None]
            stale = [c for c in cards
                     if c.get("age_days") is not None and c["age_days"] >= days]
            tally.add("older than %d days" % days, len(stale))
            if unreadable:
                tally.add("age could not be read", len(unreadable))
                tally.note("Anything whose age could not be read is left alone. A "
                           "request of unknown age is not an old one.")

            if mode == job.PLAN:
                print("")
                print("  these would be taken back")
                job.rule()
                for row in stale[:20]:
                    print("  %-28s %d days" % ((row.get("name") or "?")[:28],
                                               row["age_days"]))
                if len(stale) > 20:
                    print("  ... and %d more" % (len(stale) - 20))
                print("")
                print("  Nothing was clicked. Nothing was written.")
            else:
                for row in stale:
                    ok, why = gather_limits.can_act("undo")
                    if not ok:
                        tally.note("Stopped: %s." % why)
                        break
                    if take_back(page, row):
                        gather_limits.record("undo", note=row.get("name"))
                        tally.add("taken back")
                        link = rec.clean_link(row.get("link"))
                        recorder.add(
                            rec.WITHDRAWN,
                            rec.fp_withdrawn(link or (row.get("name") or ""),
                                             date.today().isoformat()),
                            rec.identifiers(link=link, name=row.get("name")),
                            payload={"days waiting": row.get("age_days")},
                            ts=datetime.now(timezone.utc).isoformat(timespec="seconds"))
                    else:
                        tally.add("could not confirm it went")
                    walk.pause()
        except KeyboardInterrupt:
            print("")
            print("  Stopped by you. Everything already taken back is recorded.")

    recorder.close()
    tally.show("what happened")
    if mode == job.COMMIT:
        print("")
        print("  Each one is written into your own log as a request you took back,")
        print("  which is what lets the next job tell an accepted request from one")
        print("  that stopped being there for some other reason.")
    return 0
