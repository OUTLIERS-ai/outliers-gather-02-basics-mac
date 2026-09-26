"""
Outliers Gather - Layer 2 - Going out and bringing people back

Layer 1 gave you a browser that can go outside and a doorman standing at a door
nobody had walked through. This layer walks through it: four jobs that find people
and put them into the records you already keep.

    python install.py

It finds your CRM, checks that the parts this layer stands on are actually there,
asks you three questions, and installs the layer into it.

Nothing here reaches the outside world. It writes files, asks the questions, and
stops. Both switches stay exactly as you left them, and if this is a fresh setup
they are still off.

Needs: Python 3.8 or newer. The jobs also need Playwright, which this installer
checks for and tells you how to get if it is missing.
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

# What a member types to start Python. A Mac has `python3` and no plain `python`; Windows
# keeps `python`, exactly as before.
PY = "python3" if sys.platform == "darwin" else "python"

# The 2 lines that get Playwright. On a Mac they go through `python3 -m`, because pip can put
# its own `pip` and `playwright` commands in a folder Terminal does not search.
if sys.platform == "darwin":
    PLAYWRIGHT_STEPS = ["python3 -m pip install playwright", "python3 -m playwright install chromium"]
else:
    PLAYWRIGHT_STEPS = ["pip install playwright", "playwright install chromium"]

LAYER = 2
LAYER_NAME = "Going out and bringing people back"
SERIES = "Gather"

HERE = Path(__file__).resolve().parent
ENGINE = HERE / "engine"

# Everything in this layer, plus `gather.py`, which REPLACES the one Layer 1
# installed and keeps both of its commands unchanged. It is listed here rather
# than quietly overwritten so that you know it happened.
MINE = ["gather_record.py", "gather_job.py", "gather_pending.py",
        "gather_find.py", "gather_ask.py", "gather_undo.py",
        "gather_accepted.py", "gather.py"]

# What this layer stands on. Each one is named with what to do about it, because
# "missing dependency" tells you nothing you can act on.
NEEDED = [
    ("limits.py", "your CRM's safety layer",
     "This layer asks that shared counter for room as its last check."),
    ("ledger.py", "your CRM's event log",
     "Everything found is written there, and nowhere else."),
    ("identity.py", "your CRM's resolver",
     "It is the single place that decides which person somebody is."),
    ("collect.py", "your CRM's collectors",
     "The export path hands your file straight to them rather than reading it twice."),
    ("gather_limits.py", "Layer 1 of Gather, the foundation",
     "Every job here asks its doorman before it does anything at all."),
]


# No colour codes anywhere. Plenty of terminals print them as literal gibberish and
# a member's first minute with this must not look broken.
def say(msg=""):
    print(msg, flush=True)


def ask(question, default=None, helptext=None):
    say()
    say(question)
    if helptext:
        say("  " + helptext)
    prompt = "  > " if default is None else "  [%s] > " % default
    try:
        answer = input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        say("\nStopped. Nothing was changed.")
        sys.exit(1)
    return answer or (default or "")


# ------------------------------------------------------------- finding your CRM

def config_path(home):
    return Path(home) / "_layers" / "config.json"


def looks_like_a_crm(home):
    try:
        return config_path(home).exists()
    except OSError:
        return False


def find_vault():
    """Find the CRM you built, by looking for its config file."""
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
    here = Path.cwd()
    tried.append(here)
    tried.extend(here.parents)

    for candidate in tried:
        if looks_like_a_crm(candidate):
            return Path(candidate)

    say()
    say("  Could not find your CRM automatically.")
    raw = ask("Where is it?", default=str(Path.home() / "CRM"),
              helptext="The folder your first layer built. It has a _layers folder inside it.")
    candidate = Path(raw.strip().strip('"').strip("'")).expanduser()
    return candidate if looks_like_a_crm(candidate) else None


def refuse(reason, fix=None):
    say()
    say("=" * 66)
    say("  Not yet.")
    say("=" * 66)
    say()
    say("  " + reason)
    if fix:
        say()
        say("  " + fix)
    say()
    sys.exit(1)


# ------------------------------------------------------------------- questions

def ask_stale_days():
    raw = ask("After how many days is an unanswered request stale?",
              default="21",
              helptext="Requests nobody has answered take up room, and somebody who "
                       "has not answered in that long is not about to. Taking them "
                       "back is the safest live action in the layer.")
    try:
        return max(3, min(int(raw), 120))
    except ValueError:
        return 21


def ask_search_allowance():
    raw = ask("How many searches a month should it assume you have?",
              default="250",
              helptext="On an ordinary account the allowance is somewhere around two "
                       "hundred and fifty to three hundred and fifty, and it is spent "
                       "by searching rather than by what comes back. Nobody publishes "
                       "the real number, so this is the number to stop at. Lower is safer.")
    try:
        return max(10, min(int(raw), 400))
    except ValueError:
        return 250


def ask_collect_max():
    raw = ask("At most, how many people should one reading run bring back?",
              default="300",
              helptext="A run that reads for an hour is a run that looks nothing like "
                       "somebody using the site. Several short runs beat one long one, "
                       "and what is already read is kept either way.")
    try:
        return max(20, min(int(raw), 1000))
    except ValueError:
        return 300


# --------------------------------------------------------------------- the work

def playwright_present():
    try:
        import playwright                                   # noqa: F401
        return True
    except ImportError:
        return False


def write_json_safely(path, data):
    """Write a file by building the new one beside it and swapping it in.

    Never opened for writing over the top of the old one. A crash halfway through
    that would leave your config file half-written is a crash that costs you every
    answer you have ever given the installers, and it is avoided by not doing it.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2, ensure_ascii=False)
    handle, temp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temp, str(path))
    finally:
        if os.path.exists(temp):
            os.remove(temp)


def read_json(path, fallback):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fallback


def install_modules(engine_dir):
    engine_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name in MINE:
        shutil.copy2(ENGINE / name, engine_dir / name)
        written.append(name)
    return written


def teach_the_log(engine_dir):
    """Add this layer's three event types to your CRM's own settings file.

    Your log refuses a type it has never heard of, which is the property that stops
    one occurrence ending up with six names. So the types are written where your
    own types live, in your own file, merged in beside anything already there and
    never over the top of it.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_gather_record_for_install", ENGINE / "gather_record.py")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(engine_dir))
    try:
        spec.loader.exec_module(module)
        added = module.ADDED_TYPES
    except Exception as err:                                # noqa: BLE001
        say()
        say("  Your log could not be taught this layer's event types: %s" % err)
        say("  The jobs will say so plainly and refuse rather than half-work.")
        return []
    finally:
        try:
            sys.path.remove(str(engine_dir))
        except ValueError:
            pass

    path = Path(engine_dir) / "settings.json"
    settings = read_json(path, {})
    if not isinstance(settings, dict):
        settings = {}
    events = dict(settings.get("events") or {})
    fresh = []
    for name, spec_body in added.items():
        if name not in events:
            events[name] = dict(spec_body)
            fresh.append(name)
    settings["events"] = events
    write_json_safely(path, settings)
    return fresh


def main():
    say()
    say("=" * 66)
    say("  Outliers %s - Layer %d - %s" % (SERIES, LAYER, LAYER_NAME))
    say("=" * 66)
    say()
    say("  This installs four jobs that go out and bring people back. Nothing")
    say("  in it writes to a person or sends a message: that is deliberately")
    say("  a later part of the series. Nothing here reaches the outside world.")

    home = find_vault()
    if not home:
        refuse("That folder does not look like your CRM - there is no _layers folder inside it.",
               "Install the first layer of your CRM before this one.")

    engine_dir = Path(home) / "_engine"
    for filename, what, why in NEEDED:
        if not (engine_dir / filename).exists():
            refuse("%s is not installed yet, and this layer stands on it. %s" % (what, why),
                   "Install it first, then run this again.")

    say()
    say("  Found your CRM: %s" % home)
    say("  Everything it needs is there.")

    stale = ask_stale_days()
    allowance = ask_search_allowance()
    per_run = ask_collect_max()

    written = install_modules(engine_dir)
    fresh_types = teach_the_log(engine_dir)

    cfg = read_json(config_path(home), {})
    if not isinstance(cfg, dict):
        cfg = {}
    mine = dict(cfg.get("gather") or {})

    # Your answers from Layer 1 are left exactly as they are, including both
    # switches. An installer that quietly turns something on is an installer
    # nobody can trust with the next layer.
    daily = dict(mine.get("daily") or {})
    daily.setdefault("look", 40)
    daily.setdefault("profile", 20)
    daily.setdefault("request", 8)
    daily.setdefault("undo", 15)
    daily.setdefault("search", 5)
    mine["daily"] = daily
    mine.setdefault("weekly", {"request": daily.get("request", 8) * 5})
    mine.setdefault("engine-on", False)
    mine.setdefault("plan-only", True)
    mine["undo-after-days"] = stale
    mine["search-allowance"] = allowance
    mine["collect-max"] = per_run
    cfg["gather"] = mine
    write_json_safely(config_path(home), cfg)

    say()
    say("-" * 66)
    say("  Installed.")
    say("-" * 66)
    say()
    say("  Written into %s:" % engine_dir)
    for n in written:
        if n == "gather.py":
            say("    %s (replaces Layer 1's, and keeps both of its commands)" % n)
        else:
            say("    %s" % n)
    if fresh_types:
        say()
        say("  Your log was taught %d new event types, written into" % len(fresh_types))
        say("  %s beside your own:" % (engine_dir / "settings.json"))
        for n in fresh_types:
            say("    %s" % n)
    say()
    say("  Your answers are in %s under \"gather\"." % config_path(home))
    say()
    say("  Both switches are exactly as you left them. Nothing was turned on.")

    if not playwright_present():
        say()
        say("  ONE MORE STEP before any job can open a page. The browser needs")
        say("  Playwright, which is not installed yet. In this same terminal, run:")
        say()
        for step in PLAYWRIGHT_STEPS:
            say("      " + step)
        say()
        say("  The second line downloads the browser itself, so it takes a minute.")

    say()
    say("  Now, in a terminal in that _engine folder:")
    say()
    say("      %s gather.py status" % PY)
    say()
    say("  Then the job that never leaves your machine:")
    say()
    say("      %s gather.py find export <file.csv> --commit" % PY)
    say()
    say("  Then look at a page without touching it:")
    say()
    say("      %s gather.py undo --probe" % PY)
    say()
    return 0


if __name__ == "__main__":
    sys.exit(main())
