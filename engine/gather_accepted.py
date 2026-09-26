"""
gather_accepted.py - finding out who said yes.

    python gather.py accepted [--probe] [--commit]

Nobody tells you when a request is accepted in a form anything can read. What you
get instead is an absence: the request stops being on the list of ones nobody has
answered. So this reads that list and works out who has left it since last time.

THE ONE FREE READ, AND WHY IT IS ENOUGH. Reading your own outstanding requests
costs one page. Visiting every person you have ever asked, to see whether you can
now message them, costs one page each and is the most visible reading you could
possibly do. The absence is nearly always sufficient, so the cheap read is the
main path and the expensive one is asked for by hand.

LEAVING THE LIST HAS THREE CAUSES, AND ONLY ONE OF THEM IS GOOD NEWS

  * they accepted
  * you took the request back
  * the platform let it expire

The second is not a guess here, because `undo` writes down every request it takes
back. That leaves accepted and expired, and those are told apart by age: a request
that left the list while it was still young was accepted, and one that left it
after a long wait might have expired. Anything that cannot be told apart is
reported as unclear and never written down as an acceptance. A wrong acceptance is
worse than a missed one: a miss shows up as somebody sitting in the wrong pile,
and a wrong one puts a stranger in front of you as a connection you never made.

THE TWO COMPARISONS ARE DELIBERATELY LOPSIDED

Deciding somebody is STILL WAITING is generous: a name written with a badge or a
qualification after it still counts as a match, because a wrong "still waiting"
costs one run's delay and nothing else.

Deciding somebody ACCEPTED is strict: the profile address has to match, or the
name has to match exactly. This is the comparison where being generous puts a
person in your records who was never there, and the same two surfaces spell the
same name differently often enough for that to happen on its own.

FREE IDENTITY, TAKEN WHILE WE ARE HERE. Every card on that list carries the
person's own profile address, which is the strongest identifier there is. It costs
nothing to read while the page is open, so it is read and recorded, and the next
comparison is made on an address rather than on two spellings of a name.

WHAT IS PROVEN AND WHAT IS NOT. The reasoning here is the part that has been paid
for elsewhere, by a system that matched people by name across two surfaces and
quietly built a pile of people it could never confirm. The page reading is
inherited and not proven. Run the probe first.

Needs: Python 3.8 or newer, plus Playwright.
"""

import re
import sys
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gather_settings as gs                                # noqa: E402
import gather_limits                                        # noqa: E402
import gather_walk as walk                                  # noqa: E402
import gather_job as job                                    # noqa: E402
import gather_pending as pending                            # noqa: E402
import gather_record as rec                                 # noqa: E402

try:
    import ledger
except ImportError:
    ledger = None


def stale_after():
    return int(gs.get().get("undo-after-days") or 21)


def loose_name(value):
    """A name reduced enough that decoration stops mattering.

    Used ONLY for deciding somebody is still waiting, never for deciding they
    accepted. Accents are folded, anything after a comma is dropped, and letters
    are the only characters kept.
    """
    if not value:
        return ""
    s = unicodedata.normalize("NFKD", str(value))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.split(",")[0]
    s = re.sub(r"[^A-Za-z ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def exact_name(value):
    """A name with its spacing tidied and nothing else touched."""
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def _days_since(when):
    try:
        stamp = str(when)[:10]
        return (date.today() - date.fromisoformat(stamp)).days
    except (TypeError, ValueError):
        return None


def asked_and_waiting():
    """Everybody you have asked, with what has happened to them since.

    One pass over your log. A request you took back is known here, which is what
    makes the difference between an acceptance and a disappearance readable at all.
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
        kind = ev.get("type")
        if kind not in (rec.REQUESTED, rec.WITHDRAWN, rec.CONNECTED):
            continue
        row = people.setdefault(key, {"link": link, "name": "", "asked": "",
                                      "withdrawn": "", "connected": False})
        if link and not row["link"]:
            row["link"] = link
        for i in idents:
            if i and "/" not in str(i) and "@" not in str(i) and not row["name"]:
                row["name"] = str(i)
        when = str(ev.get("ts") or "")
        if kind == rec.REQUESTED and (not row["asked"] or when > row["asked"]):
            row["asked"] = when
        elif kind == rec.WITHDRAWN and when > row["withdrawn"]:
            row["withdrawn"] = when
        elif kind == rec.CONNECTED:
            row["connected"] = True

    out = []
    for row in people.values():
        if not row["asked"] or row["connected"]:
            continue
        if row["withdrawn"] and row["withdrawn"] >= row["asked"]:
            continue                    # you took it back; it left the list for that
        out.append(row)
    return out


def sort_them_out(waiting, cards):
    """Who is still waiting, who accepted, and who cannot be told apart.

    Returns three lists. The generous comparison decides the first; the strict one
    decides the second; anything left is the third and is never written down.
    """
    links = set()
    loose = set()
    exact = set()
    for card in cards:
        link = rec.clean_link(card.get("link"))
        if link:
            links.add(link)
        if card.get("name"):
            loose.add(loose_name(card["name"]))
            exact.add(exact_name(card["name"]))

    still, accepted, unclear = [], [], []
    limit = stale_after()
    for row in waiting:
        link = rec.clean_link(row.get("link"))
        # generous: any of the three ways of matching keeps them waiting
        if (link and link in links) or (row.get("name")
                                        and loose_name(row["name"]) in loose):
            still.append(row)
            continue
        # strict: they have to be identifiable at all to be called an acceptance
        identifiable = bool(link) or (row.get("name") and exact_name(row["name"]) in exact)
        age = _days_since(row.get("asked"))
        if not link and not identifiable:
            unclear.append(dict(row, why="nothing strong enough to match on"))
        elif age is None:
            unclear.append(dict(row, why="the date it was asked cannot be read"))
        elif age >= limit:
            unclear.append(dict(row, why="waited %d days, so it may have expired" % age))
        else:
            accepted.append(dict(row, waited=age))
    return still, accepted, unclear


def confirm_on_page(page, row):
    """Open one profile and read whether you can now message them.

    The expensive answer, asked for by hand with `--confirm`. Being able to message
    somebody is what being connected to them looks like from a page.
    """
    link = rec.clean_link(row.get("link"))
    if not link:
        return None
    walk.open_page(page, link)
    try:
        return bool(page.evaluate(
            "() => { const b = [...document.querySelectorAll('button, a[role=\"button\"]')];"
            " return b.some(x => /^message /i.test(x.getAttribute('aria-label') || '')); }"))
    except Exception:                                       # noqa: BLE001
        return None


def run(argv):
    mode = job.mode_of(argv)
    confirming = "--confirm" in argv
    job.banner("accepted", mode)

    if not job.records_ready():
        return 1
    if not job.doorman("look"):
        return 1

    tally = job.Tally()
    recorder = rec.Recorder(plan=(mode != job.COMMIT), source="gather:accepted")

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
                print("")
                print("  This job never clicks anything at all. It reads that list,")
                print("  compares it with what your log says you asked for, and")
                print("  writes the difference into your log. Nothing was written.")
                return 0

            pending.load_whole_list(page, say=print)
            cards = pending.read_cards(page)
            waiting = asked_and_waiting()

            tally.add("still on the list", len(cards))
            tally.add("you asked, still open", len(waiting))

            still, accepted, unclear = sort_them_out(waiting, cards)
            tally.add("still waiting", len(still))
            tally.add("accepted", len(accepted))
            tally.add("cannot be told apart", len(unclear))

            if accepted:
                print("")
                print("  accepted")
                job.rule()
                for row in accepted[:20]:
                    print("  %-28s waited %d days"
                          % ((row.get("name") or row.get("link") or "?")[:28],
                             row.get("waited", 0)))
                if len(accepted) > 20:
                    print("  ... and %d more" % (len(accepted) - 20))

            if unclear:
                print("")
                print("  cannot be told apart")
                job.rule()
                for row in unclear[:10]:
                    print("  %-28s %s"
                          % ((row.get("name") or row.get("link") or "?")[:28],
                             row.get("why", "")))
                if len(unclear) > 10:
                    print("  ... and %d more" % (len(unclear) - 10))
                print("")
                print("  None of these is written down as an acceptance. To settle")
                print("  them by opening each profile, which costs one page read")
                print("  each, add --confirm.")

            if confirming and unclear:
                for row in list(unclear):
                    ok, why = gather_limits.can_act("profile")
                    if not ok:
                        tally.note("Stopped confirming: %s." % why)
                        break
                    verdict = confirm_on_page(page, row)
                    gather_limits.record("profile")
                    tally.add("profiles read to confirm")
                    if verdict is True:
                        accepted.append(dict(row, waited=_days_since(row.get("asked")) or 0))
                        tally.add("confirmed by looking")
                    walk.pause()

            if mode == job.COMMIT:
                for row in accepted:
                    link = rec.clean_link(row.get("link"))
                    recorder.add(
                        rec.CONNECTED,
                        rec.fp_connected(link or exact_name(row.get("name"))),
                        rec.identifiers(link=link, name=row.get("name")),
                        payload={"how": "a request you sent was accepted"},
                        ts=datetime.now(timezone.utc).isoformat(timespec="seconds"))
            else:
                print("")
                print("  Plan only. Nothing was written into your records.")
        except KeyboardInterrupt:
            print("")
            print("  Stopped by you.")

    recorder.close()
    if mode == job.COMMIT:
        recorder.show()
    tally.show("what happened")
    return 0
