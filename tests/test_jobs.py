"""
test_jobs.py - the four jobs, and the promises they make that you cannot see.

SHOULD: no job does anything before the doorman says yes; nothing in this layer
types at a person; only the two jobs that are supposed to act can click at all;
everything found lands in your CRM's own log through your CRM's own resolver, once
and only once; the two ceilings that cannot be argued with are respected.

DID (the reason each check below exists):

  * A job that asks the doorman AFTER opening a browser has already reached the
    outside world before anybody said it could. The checks below call each job with
    the engine switched off and watch it come straight back, having opened nothing.
    They would pass as happily on a machine with no browser installed at all, which
    is the point.
  * A connection request that carries your words is a message. The whole promise of
    this layer is that it knocks and never speaks, and a promise nobody checks is a
    preference. So this reads the layer's own source and fails if anything in it
    can type into a page.
  * Counting an action before taking it means a run that stops halfway has spent an
    allowance it never used. Every job here asks the doorman before it acts and
    records after, and the order is checked in the source rather than trusted.
  * A person who arrives from an export and again from a page read is one person and
    one occurrence. If the two paths fingerprint it differently, your log says you
    connected to them twice and every count taken from it afterwards is wrong.
  * The list of people who reacted to a post stops giving anything back at a certain
    number, and a reader with no ceiling scrolls at it forever.
  * A search allowance is spent by searching. A run that finds out it is empty by
    trying has spent the last one.

Run it:  python tests/test_jobs.py        (exit 0 = green)

No browser, no network, and it never touches your real records: everything happens
in a throwaway CRM built for the run. Your own CRM is READ, to borrow the modules
this layer stands on, and never written to.
"""

import json
import os
import shutil
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENGINE = HERE.parent / "engine"


def find_installed_crm():
    """Your CRM, found the same way the installer finds it.

    Deliberately NOT a path relative to this repository. A test that reaches back
    into the folder it was authored in passes for its author and fails for every
    person who clones it, which is the whole family of fault this series exists to
    avoid. It never prompts: a test that asks a question cannot be run unattended.
    """
    tried = []
    env = os.environ.get("OUTLIERS_CRM")
    if env:
        tried.append(Path(env).expanduser())
    pointer = Path.home() / ".outliers-crm"
    if pointer.exists():
        try:
            noted = pointer.read_text(encoding="utf-8").strip()
            if noted:
                tried.append(Path(noted))
        except OSError:
            pass
    tried.append(Path.home() / "CRM")
    cwd = Path.cwd()
    tried.append(cwd)
    tried.extend(cwd.parents)
    for candidate in tried:
        try:
            if (Path(candidate) / "_engine" / "limits.py").exists():
                return Path(candidate) / "_engine"
        except OSError:
            continue
    return None


BORROWED = ["crm_paths.py", "safe_write.py", "limits.py", "settings.py",
            "ledger.py", "identity.py", "collect.py",
            "gather_settings.py", "gather_limits.py", "gather_walk.py"]

CRM_ENGINE = find_installed_crm()


def stop_because(reason, detail):
    print("=" * 66)
    print("  %s" % reason)
    print("=" * 66)
    print()
    for line in detail:
        print("  %s" % line)
    print()
    print("  If your CRM is somewhere unusual, point at it:")
    print()
    print("      OUTLIERS_CRM=/path/to/your/CRM python tests/test_jobs.py")
    print()
    sys.exit(2)


if CRM_ENGINE is None:
    stop_because("Your CRM was not found, so the tests stop here.", [
        "This layer writes everything it finds into your CRM's own log, through",
        "your CRM's own resolver. Without them there is nothing to write to, so",
        "the checks that matter most cannot be run -- and a check that did not",
        "run is not a check that passed.",
        "",
        "This is not a fault in this layer. Install your CRM, then run this again.",
    ])

absent = [f for f in BORROWED if not (CRM_ENGINE / f).exists()]
if absent:
    stop_because("Your CRM is missing parts this layer stands on.", [
        "Not found in %s:" % CRM_ENGINE,
        "    " + ", ".join(absent),
        "",
        "gather_*.py come from Layer 1 of Gather. The rest come from your CRM.",
        "Install whichever is missing and run this again.",
    ])


# --- a throwaway CRM, with the real modules in it ----------------------------

root = Path(tempfile.mkdtemp(prefix="gather-layer2-"))
(root / "_layers").mkdir(parents=True, exist_ok=True)
(root / "_state").mkdir(parents=True, exist_ok=True)
(root / "_engine").mkdir(parents=True, exist_ok=True)
(root / "People").mkdir(parents=True, exist_ok=True)

for name in BORROWED:
    shutil.copy2(CRM_ENGINE / name, root / "_engine" / name)

sys.path.insert(0, str(root / "_engine"))
sys.path.insert(0, str(ENGINE))

import crm_paths                                            # noqa: E402
crm_paths.use_vault(root)

import gather_settings as gs                                # noqa: E402
import gather_limits                                        # noqa: E402
import ledger                                               # noqa: E402
import collect                                              # noqa: E402

FAILS = []


def check(name, ok, detail=""):
    print(("  PASS  " if ok else "  FAIL  ") + name + (" :: " + detail if detail else ""))
    if not ok:
        FAILS.append(name)


ASLEEP = {"engine-on": False, "plan-only": True,
          "hours": {"from": "09:00", "to": "17:30"},
          "days": ["mon", "tue", "wed", "thu", "fri"],
          "daily": {"look": 40, "profile": 20, "request": 8, "undo": 15, "search": 5},
          "weekly": {"request": 40}, "ramp-days": 14,
          "undo-after-days": 21, "search-allowance": 250, "collect-max": 300}

AWAKE = dict(ASLEEP)
AWAKE.update({"engine-on": True,
              "hours": {"from": "00:00", "to": "23:59"},
              "days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]})


def configure(settings):
    gs.put(dict(settings))


configure(ASLEEP)


# --- the log has to be taught the words before anything can be written -------

print("=== the log refuses a word it has never heard ===")

import gather_record as rec                                 # noqa: E402

ready, why = rec.vocabulary_ready()
check("a log that was never taught these types says so", not ready, why)

settings_file = root / "_engine" / "settings.json"
settings_file.write_text(json.dumps({"events": {
    name: dict(spec) for name, spec in rec.ADDED_TYPES.items()}}, indent=2),
    encoding="utf-8")

ready, why = rec.vocabulary_ready()
check("once the installer has written them, it is ready", ready, why)
check("and they are not counted as having been in touch with anybody",
      all(t not in ledger.contact_types() for t in rec.ADDED_TYPES),
      "a request carries no words, so it is not contact")


# --- writing goes through their log, once ------------------------------------

print()
print("=== everything found lands in your own log, once ===")

writer = rec.Recorder(plan=False, source="test")
link = "https://www.linkedin.com/in/rowan-ashdown"
first = writer.add(rec.FOUND, rec.fp_found("search", link),
                   rec.identifiers(link=link, name="Rowan Ashdown"),
                   payload={"where": "search"})
second = writer.add(rec.FOUND, rec.fp_found("search", link),
                    rec.identifiers(link=link, name="Rowan Ashdown"),
                    payload={"where": "search"})
check("the first time, it is written", first == "written", first)
check("the second time, it is already there", second == "already there", second)
check("and the log has exactly one line about them",
      sum(1 for e in ledger.events() if e.get("type") == rec.FOUND) == 1)
check("the line went into your CRM's log file, not a file of this layer's own",
      ledger.ledger_path().exists(), str(ledger.ledger_path()))

planner = rec.Recorder(plan=True, source="test")
other = "https://www.linkedin.com/in/casey-mireles"
check("a plan run writes nothing at all",
      planner.add(rec.FOUND, rec.fp_found("search", other),
                  rec.identifiers(link=other, name="Casey Mireles")) == "would write")
check("and the log did not grow",
      sum(1 for e in ledger.events() if e.get("type") == rec.FOUND) == 1)


# --- one person, one occurrence, whichever path found them -------------------

print()
print("=== a person found twice by two paths is not two connections ===")

export = root / "connections-export.csv"
export.write_text(
    "First Name,Last Name,URL,Company,Position,Connected On\n"
    "Sam,Okafor,https://www.linkedin.com/in/sam-okafor,Ardent,Operations,2026-01-04\n",
    encoding="utf-8")
stats = collect.run("connections", export, dry_run=False)
check("your CRM's own collector read the export", stats.get("written") == 1, str(stats))

again = rec.Recorder(plan=False, source="test")
same = again.add(rec.CONNECTED,
                 rec.fp_connected("https://www.linkedin.com/in/sam-okafor"),
                 rec.identifiers(link="https://www.linkedin.com/in/sam-okafor",
                                 name="Sam Okafor"))
check("and this layer will not record the same connection a second time",
      same == "already there",
      "the fingerprint is the same shape their collector writes")


# --- the doorman is asked before anything opens ------------------------------

print()
print("=== every job asks the doorman before it opens anything ===")

import gather_job as job                                    # noqa: E402
import gather_find                                          # noqa: E402
import gather_undo                                          # noqa: E402
import gather_ask                                           # noqa: E402
import gather_accepted                                      # noqa: E402

configure(ASLEEP)

for label, call in (
        ("find connections", lambda: gather_find.run(["gather.py", "find", "connections"])),
        ("undo", lambda: gather_undo.run(["gather.py", "undo"])),
        ("ask", lambda: gather_ask.run(["gather.py", "ask"])),
        ("accepted", lambda: gather_accepted.run(["gather.py", "accepted"]))):
    try:
        code = call()
        ok = code == 1
        detail = "came back with %r" % code
    except Exception as err:                                # noqa: BLE001
        ok, detail = False, "raised %s" % err
    check("%s stops with the engine off, having opened nothing" % label, ok, detail)

# READING A FILE IS NOT SOMETHING THE DOORMAN GOVERNS, and that is a ruling rather
# than an oversight. He decides what may reach a website; an export in your
# downloads folder reaches none. Gating it would refuse the one step that cannot go
# wrong because it happens to be Sunday -- and it is the step every member is told
# to start with. Both halves are pinned here: it must WORK with the engine off, and
# it must still open nothing while doing so.
try:
    code = gather_find.run(["gather.py", "find", "export", str(export)])
    ok, detail = code == 0, "came back with %r" % code
except Exception as err:                                    # noqa: BLE001
    ok, detail = False, "raised %s" % err
check("find export WORKS with the engine off, because it reaches nothing", ok, detail)

src_find = (ENGINE / "gather_find.py").read_text(encoding="utf-8")
export_block = src_find[src_find.find("if source == \"export\""):]
check("and it returns before any window is opened",
      "one_window" not in export_block.split("return from_export")[0],
      "the export path must not reach the browser")

check("and the engine being off is why",
      gather_limits.can_act("look")[1].find("switched off") >= 0,
      gather_limits.can_act("look")[1])

print()
print("=== the second switch guards the two jobs that act on somebody ===")
configure(AWAKE)                                            # engine on, plan-only still on
check("plan-only refuses an outward job", not job.outward_allowed())
armed, why = gs.armed()
check("and says which switch it is", "plan-only" in why, why)


print()
print("=== the queue is read out of your log, and nothing else ===")

names = [row["name"] or row["link"] for row in gather_ask.queue()]
check("somebody a job found is waiting to be asked",
      any("rowan-ashdown" in (row["link"] or "") for row in gather_ask.queue()),
      ", ".join(names))
check("and somebody you are already connected to is not",
      not any("sam-okafor" in (row["link"] or "") for row in gather_ask.queue()),
      ", ".join(names))

held = "https://www.linkedin.com/in/holly-mark"
ledger.emit(rec.FOUND, person=None, source="test",
            payload={"fingerprint": rec.fp_found("search", held)},
            identifiers=[held, "Holly Mark"])
ledger.emit("held", person=None, source="test", identifiers=[held, "Holly Mark"])
check("and somebody you put on hold is left alone, without saying so twice",
      not any("holly-mark" in (row["link"] or "") for row in gather_ask.queue()))

check("plan only says who is next and opens nothing",
      gather_ask.run(["gather.py", "ask"]) == 0)


# --- the modes ---------------------------------------------------------------

print()
print("=== three modes, and the default is the safe one ===")
check("nothing typed means plan only", job.mode_of(["gather.py", "ask"]) == job.PLAN)
check("--probe is probe", job.mode_of(["gather.py", "ask", "--probe"]) == job.PROBE)
check("--commit is commit", job.mode_of(["gather.py", "ask", "--commit"]) == job.COMMIT)


# --- what the source is not allowed to contain -------------------------------

print()
print("=== nothing in this layer types at a person ===")

MODULES = ["gather_record.py", "gather_job.py", "gather_pending.py",
           "gather_find.py", "gather_ask.py", "gather_undo.py",
           "gather_accepted.py", "gather.py"]
source = {name: (ENGINE / name).read_text(encoding="utf-8") for name in MODULES}

for typing in (".fill(", ".type(", "insert_text", "press_sequentially"):
    guilty = [n for n, text in source.items() if typing in text]
    check("no %s anywhere in the layer" % typing, not guilty, ", ".join(guilty))

print()
print("=== only the two jobs meant to act can act on a person ===")
acting = [n for n, text in source.items()
          if 'can_act("request")' in text or 'can_act("undo")' in text]
check("the two actions that reach a person live only in ask and undo",
      set(acting) == {"gather_ask.py", "gather_undo.py"}, ", ".join(acting))
check("and nothing else knows how to match a person's own invite control",
      [n for n, text in source.items() if "vanityName" in text] == ["gather_ask.py"])

# Reading a page still involves clicking: a "show more" button, a "next" button,
# the control that opens the list of people who reacted. Those are clicks on the
# page you are already reading, not on a person. Every click outside the two
# acting jobs has to be one of them, and this is where that is checked rather
# than assumed.
NAVIGATION = ("show more", "load more", "more results", "next", "reaction")
for name, text in source.items():
    if name in ("gather_ask.py", "gather_undo.py"):
        continue
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if ".click(" not in line:
            continue
        context = " ".join(lines[max(0, i - 12):i + 1]).lower()
        check("%s clicks only to move around a page (line %d)" % (name, i + 1),
              any(word in context for word in NAVIGATION), line.strip())

print()
print("=== the doorman is asked before the count is written ===")
for name in ("gather_find.py", "gather_ask.py", "gather_undo.py", "gather_accepted.py"):
    text = source[name]
    if "gather_limits.record(" not in text:
        continue
    # Asked either straight (can_act) or through the shared shape (job.doorman),
    # which is the same question with the refusal already worded for a person.
    asked = min(p for p in (text.find("can_act("), text.find("job.doorman(")) if p >= 0)
    counted = text.find("gather_limits.record(")
    check("%s asks before it counts" % name, 0 <= asked < counted,
          "asked at %d, counted at %d" % (asked, counted))

print()
print("=== the export path hands your file to your own collector ===")
import inspect                                              # noqa: E402
exporter = inspect.getsource(gather_find.from_export)
check("it calls your collector", "collect.run(" in exporter)
check("and does not read the file itself", "DictReader" not in exporter)


# --- the two ceilings --------------------------------------------------------

print()
print("=== the ceiling on one post's reactions is never pushed at ===")


class EndlessList:
    """A list of people that never runs out, so the only way the reader can stop
    is the ceiling. A real page runs out on its own and would hide a missing one."""

    def __init__(self):
        self.next = 0
        self.reads = 0

    def evaluate(self, script, *args):
        if "scrollTop" in script:
            return True
        self.reads += 1
        out = []
        for _ in range(50):
            self.next += 1
            out.append({"id": "/in/person-%d" % self.next,
                        "name": "Person %d" % self.next,
                        "link": "https://www.linkedin.com/in/person-%d" % self.next,
                        "headline": "", "place": ""})
        return out


page = EndlessList()
people = gather_find.gather_reactors(page, ceiling=99_999, pause=lambda: None)
check("it stops at the observed ceiling and not one past it",
      len(people) == gather_find.REACTION_CEILING,
      "collected %d, ceiling %d" % (len(people), gather_find.REACTION_CEILING))
check("and nobody was collected twice",
      len({p["link"] for p in people}) == len(people))

page = EndlessList()
few = gather_find.gather_reactors(page, ceiling=120, pause=lambda: None)
check("a smaller number of your own is respected too", len(few) == 120, "%d" % len(few))


print()
print("=== the search allowance is stopped at, not found out about ===")

import safe_write                                           # noqa: E402

safe_write.write_json(gather_find.allowance_path(),
                      {"month": gather_find.allowance()["month"], "used": 0,
                       "stopped": False})
ok, why = gather_find.allowance_check()
check("with none used, a search is allowed", ok, why)

safe_write.write_json(gather_find.allowance_path(),
                      {"month": gather_find.allowance()["month"], "used": 250,
                       "stopped": False})
ok, why = gather_find.allowance_check()
check("at the number you set, it refuses", not ok, why)

gather_find.allowance_stop()
ok, why = gather_find.allowance_check()
check("and once a run has watched the results collapse, it stays refused", not ok, why)


class Tripwire:
    """A page that fails the test if anything navigates it."""

    url = ""
    visits = 0

    def goto(self, *args, **kw):
        Tripwire.visits += 1
        raise AssertionError("a page was opened after the allowance was spent")


code = gather_find.from_search(Tripwire(), "operations manager", job.PLAN,
                               job.Tally(), rec.Recorder(plan=True))
check("a spent allowance stops the run before any page is opened",
      code == 1 and Tripwire.visits == 0, "came back with %r" % code)


# --- reading an age off a card ----------------------------------------------

print()
print("=== how old a request is, read off the part of the card that says so ===")

import gather_pending as pending                            # noqa: E402

check("today is nought days", pending.age_in_days("Sent today") == 0)
check("a week is seven", pending.age_in_days("Sent 1 week ago") == 7)
check("a month is thirty", pending.age_in_days("Sent 1 month ago") == 30)
check("a headline full of years is not an age",
      pending.age_in_days("Rowan Ashdown 20 years in manufacturing") is None,
      "nothing on that card says when it was sent")
check("and a headline beside a real age does not win",
      pending.age_in_days("Rowan Ashdown 20 years in manufacturing Sent 3 days ago") == 3)


# --- telling an acceptance from a disappearance ------------------------------

print()
print("=== leaving the list is not the same as saying yes ===")

today = date.today().isoformat() + "T09:00:00+00:00"
long_ago = "2025-01-01T09:00:00+00:00"

waiting = [
    {"link": "https://www.linkedin.com/in/still-here", "name": "Still Here",
     "asked": today, "withdrawn": "", "connected": False},
    {"link": "https://www.linkedin.com/in/said-yes", "name": "Said Yes",
     "asked": today, "withdrawn": "", "connected": False},
    {"link": "https://www.linkedin.com/in/waited-ages", "name": "Waited Ages",
     "asked": long_ago, "withdrawn": "", "connected": False},
]
cards = [{"link": "https://www.linkedin.com/in/still-here", "name": "Still Here • 3rd"}]
still, accepted, unclear = gather_accepted.sort_them_out(waiting, cards)
check("somebody on the list is still waiting, decoration on their name or not",
      [r["name"] for r in still] == ["Still Here"], str([r["name"] for r in still]))
check("somebody who left it while it was young accepted",
      [r["name"] for r in accepted] == ["Said Yes"], str([r["name"] for r in accepted]))
check("somebody who left it after a long wait cannot be told apart",
      [r["name"] for r in unclear] == ["Waited Ages"], str([r["name"] for r in unclear]))

gone = "https://www.linkedin.com/in/taken-back"
ledger.emit(rec.REQUESTED, person=None, source="test", ts=today,
            payload={"fingerprint": rec.fp_request(gone, "2026-01-01")},
            identifiers=[gone, "Taken Back"])
ledger.emit(rec.WITHDRAWN, person=None, source="test", ts=today,
            payload={"fingerprint": rec.fp_withdrawn(gone, "2026-01-02")},
            identifiers=[gone, "Taken Back"])
check("a request you took back yourself is never anybody's answer",
      not any("taken-back" in (r["link"] or "")
              for r in gather_accepted.asked_and_waiting()),
      "it left the list because you removed it")


print()
if FAILS:
    print("%d check(s) failed:" % len(FAILS))
    for f in FAILS:
        print("   - %s" % f)
    sys.exit(1)
print("all checks passed.")
sys.exit(0)
