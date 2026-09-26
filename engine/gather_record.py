"""
gather_record.py - where everything a job finds ends up, and why it is not here.

Four jobs go out and bring people back. They need somewhere to put them, and the
somewhere is the event log your CRM already keeps. Not a file of this layer's own,
not a list of people beside the list you already have, not a second copy of
anybody. A second store starts life as a convenience and ends as two answers to
the same question, with nothing to say which one is right.

TWO BORROWED PARTS, NEITHER OF THEM COPIED HERE

**The resolver.** Deciding that a profile link, an email address and a bare name
belong to one person is the hardest part of any system like this, and your CRM
solved it once, in one place, on purpose. This asks that same resolver and takes
its answer, including the answer "I do not know, and I am not guessing".

**The log.** Events are appended through your CRM's own writer, so the append-only
contract, the closed vocabulary and the behaviour on a crash are the ones you have
already tested. Nothing here opens the log file directly.

THE VOCABULARY IS CLOSED, SO THIS LAYER ASKS RATHER THAN INVENTS

Your log refuses an event type it has never heard of. That refusal is what stops a
system ending up with six words for one occurrence and no question that returns
the whole answer. Three types are needed that your CRM had no reason to define,
and the installer writes them into your own settings file alongside the ones you
wrote, where you can read them and change them:

    person_found        a job went out and found them
    request_sent        you asked to connect, with nothing written on it
    request_withdrawn   you took back a request nobody had answered

Two more are reused exactly as they are, because your CRM already had the right
word: `connected` for a request that was accepted, and `they_engaged` for somebody
who reacted to a post.

RUNNING A JOB TWICE IS SAFE

Every person a job brings back carries a fingerprint built from what was seen, not
from when it was seen. A fingerprint already in the log is skipped. So the same
export, the same post and the same search can be run again, and only what is new
lands. This matters more than speed: a job that double-counts corrupts every
number taken from the log afterwards, and the numbers are the reason the log
exists.

Needs: Python 3.8 or newer, and your CRM's event log, resolver and collectors.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import crm_paths                                            # noqa: E402

try:
    import ledger                                           # your CRM's event log
except ImportError:
    ledger = None

try:
    import identity                                         # your CRM's resolver
except ImportError:
    identity = None

try:
    import collect                                          # your CRM's collectors
except ImportError:
    collect = None


FOUND = "person_found"
REQUESTED = "request_sent"
WITHDRAWN = "request_withdrawn"
CONNECTED = "connected"                # already in your CRM's own vocabulary
ENGAGED = "they_engaged"               # likewise


# What the installer writes into `_engine/settings.json` under "events". None of
# them count as contact: a request carries no words, and finding somebody is not
# something that happened between you and them.
ADDED_TYPES = {
    FOUND: {"means": "a job went out and found them",
            "counts_as_contact": False},
    REQUESTED: {"means": "you asked to connect, with nothing written on it",
                "counts_as_contact": False},
    WITHDRAWN: {"means": "you took back a request nobody had answered",
                "counts_as_contact": False},
}


def missing_parts():
    """Which parts of your CRM this layer needs and cannot find."""
    out = []
    if ledger is None:
        out.append("the event log (ledger.py)")
    if identity is None:
        out.append("the resolver (identity.py)")
    if collect is None:
        out.append("the collectors (collect.py)")
    return out


def vocabulary_ready():
    """Does your log know the three types this layer writes? -> (ready, reason).

    Asked before a job starts rather than at the moment of the first write. A job
    that reads two hundred people and then finds it cannot record them has wasted
    the read, and the read is the part that carries risk.
    """
    if ledger is None:
        return False, "your CRM's event log is not installed"
    try:
        known = ledger.types()
    except Exception:                                       # noqa: BLE001
        return False, "your CRM's event log could not be read"
    absent = [t for t in ADDED_TYPES if t not in known]
    if absent:
        return False, ("your log does not know these event types yet: %s. Run this "
                       "layer's installer, which writes them into your own settings "
                       "file." % ", ".join(sorted(absent)))
    return True, "ready"


# ------------------------------------------------------------------ identifiers

def clean_link(url):
    """A profile link reduced to one spelling, or "".

    The same person's link arrives with a regional prefix, tracking rubbish on the
    end, a trailing slash, or none of those. Reduced here so two spellings of one
    link are one key. The resolver does the same reduction on its own side; this
    exists so a job can compare two links it read off two pages without asking.
    """
    if not url:
        return ""
    s = str(url).strip().split("?")[0].split("#")[0].rstrip("/")
    if not s:
        return ""
    low = s.lower()
    if "/in/" not in low:
        return ""
    tail = s[low.index("/in/") + 4:]
    tail = tail.split("/")[0].strip().lower()
    return ("https://www.linkedin.com/in/" + tail) if tail else ""


def identifiers(link=None, name=None, email=None):
    """The identifiers to hand the resolver, strongest first.

    Order matters and is the resolver's own: a link is deterministic and survives
    a name change, a name is neither. Handing them over in the wrong order does
    not break anything, because the resolver re-orders, but keeping the same order
    everywhere means a log line reads the same way whichever job wrote it.
    """
    out = []
    for value in (clean_link(link), email, name):
        v = (str(value).strip() if value else "")
        if v and v not in out:
            out.append(v)
    return out


def _mint(idents):
    """The identity a provisional record made from these identifiers would have.

    This is your collectors' own answer, asked rather than reproduced. If it is not
    reachable the event is still written, carrying the raw identifiers and nobody
    named, which is what your log already does with anything it cannot attribute.
    """
    fn = getattr(collect, "_identity_of", None) if collect else None
    if not fn:
        return None
    try:
        return fn(idents)
    except Exception:                                       # noqa: BLE001
        return None


def _stage(idents, payload):
    """Write a provisional record for somebody your records do not have.

    Also your collectors' own, for the same reason: the shape of a staged record is
    a decision your CRM already made, and a second version of that file would drift
    from the first one without anybody noticing. It lands in `_staging/`, never in
    People, because a person invented from one row of a page is a suggestion. Which
    of them are real, and which are somebody you already have under another name,
    is your decision and stays yours.
    """
    fn = getattr(collect, "_staging_record", None) if collect else None
    if not fn:
        return None
    try:
        return fn(crm_paths.vault(), idents, payload or {})
    except Exception:                                       # noqa: BLE001
        return None


# ---------------------------------------------------------------------- writing

class Recorder:
    """One run's worth of writing into your log.

    Made once at the start of a job, not once per person. It reads every
    fingerprint already in the log a single time; asking the log per person would
    read the whole file per person, which is slow at a thousand people and slower
    every run after that.

    `plan` is the default and writes nothing at all. It still works out who is new,
    who is already there and who could not be identified, so a plan run tells you
    what a commit run would do rather than promising to tell you later.
    """

    def __init__(self, plan=True, source="gather"):
        self.plan = plan
        self.source = source
        self.seen = set()
        self.staged_any = False
        self.counts = {"found": 0, "written": 0, "already there": 0,
                       "new people": 0, "nobody attached": 0}
        if ledger is not None:
            try:
                for ev in ledger.events():
                    fp = (ev.get("payload") or {}).get("fingerprint")
                    if fp:
                        self.seen.add(fp)
            except Exception:                               # noqa: BLE001
                pass

    def add(self, type_, fingerprint, idents, payload=None, ts=None):
        """Record one occurrence. Returns what happened, as a word.

        -> "already there" | "would write" | "written" | "refused"
        """
        self.counts["found"] += 1
        if not fingerprint:
            return "refused"
        if fingerprint in self.seen:
            self.counts["already there"] += 1
            return "already there"

        person = None
        if identity is not None and idents:
            try:
                person = identity.resolve(*idents)
            except Exception:                               # noqa: BLE001
                person = None

        if not person:
            self.counts["new people"] += 1

        if self.plan:
            self.seen.add(fingerprint)
            return "would write"

        if not person:
            if _stage(idents, payload):
                self.staged_any = True
            person = _mint(idents)
            if not person:
                # Written anyway, with the raw identifiers kept. An occurrence
                # nobody can attach to a person is a gap worth looking at, not
                # something to throw away. Dropping it makes the log tidier and
                # makes every count taken from it wrong.
                self.counts["nobody attached"] += 1

        body = dict(payload or {})
        body["fingerprint"] = fingerprint
        try:
            ledger.emit(type_, person=person, source=self.source, ts=ts,
                        payload=body, identifiers=idents)
        except Exception as err:                            # noqa: BLE001
            print("  could not record one person: %s" % err)
            return "refused"
        self.seen.add(fingerprint)
        self.counts["written"] += 1
        return "written"

    def close(self):
        """Tell the resolver its picture has changed, so the next question is asked
        of what is on disk now rather than what was there when the run started."""
        if self.staged_any and identity is not None:
            try:
                identity.forget()
            except Exception:                               # noqa: BLE001
                pass

    def show(self):
        print("")
        for key in ("found", "written", "already there", "new people",
                    "nobody attached"):
            label = "would write" if (self.plan and key == "written") else key
            print("  %-18s %d" % (label, self.counts[key]))
        if self.staged_any:
            print("")
            print("  People your records did not have arrived in _staging/ with a")
            print("  provisional record each. Nothing was merged into anybody. Look")
            print("  at them and decide.")


# --------------------------------------------------------------- fingerprints
# Built from WHAT was seen, never from when. A fingerprint carrying the moment of
# the run makes every re-run a new occurrence, which is exactly the double-count
# the fingerprint exists to prevent.

def fp_found(where, link_or_name):
    return "found|%s|%s" % (where, str(link_or_name).lower())


def fp_connected(link_or_name):
    """Deliberately the same shape your own connections collector writes.

    Your CRM can already read a connections export. If this layer used a different
    shape for the same occurrence, importing the export and reading the page would
    each land the same person once, and the log would say you connected twice.
    """
    return "connected|%s" % str(link_or_name).lower()


def fp_engaged(post_url, link_or_name):
    return "reacted|%s|%s" % (str(post_url).split("?")[0].lower(),
                              str(link_or_name).lower())


def fp_request(link_or_name, day):
    return "request|%s|%s" % (str(link_or_name).lower(), day)


def fp_withdrawn(link_or_name, day):
    return "withdrawn|%s|%s" % (str(link_or_name).lower(), day)
