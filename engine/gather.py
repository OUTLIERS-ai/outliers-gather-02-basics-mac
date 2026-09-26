"""
gather.py - the one command you type. Layer 2 gives it four more to do.

    python gather.py status                     what is set, and what is allowed
    python gather.py login                      sign in by hand, once

    python gather.py find <source> [--probe] [--commit]
    python gather.py undo   [--probe] [--commit]
    python gather.py ask    [--probe] [--commit]
    python gather.py accepted [--probe] [--commit]

Run it from the `_engine` folder inside your CRM, which is where the installer put
it, alongside the tools your earlier layers installed.

THIS FILE REPLACES THE ONE LAYER 1 INSTALLED, and keeps both of its commands
exactly as they were. `status` gained one line, for the monthly search allowance,
which is the only limit in the series that nothing else can count for you.

THE ORDER TO RUN THEM IN, THE FIRST TIME

    find export <file.csv>    nothing leaves your machine
    undo --probe              look at a page, click nothing
    undo --commit             the safest live action there is: your own requests
    find connections --probe  then --commit
    ask --probe               look at one profile, click nothing
    ask --commit              the first action that reaches another person
    accepted                  once requests have had time to be answered

Every one of them refuses unless the doorman says yes, and the doorman arrives
saying no to everything.

Needs: Python 3.8 or newer. Everything except `status` and `find export` needs
Playwright - see the README.
"""

import sys
from datetime import datetime
from pathlib import Path

# What a member types to start Python. A Mac has `python3` and no plain `python`; Windows
# keeps `python`, exactly as before.
PY = "python3" if sys.platform == "darwin" else "python"

sys.path.insert(0, str(Path(__file__).resolve().parent))

import crm_paths                                            # noqa: E402
import gather_settings as gs                                # noqa: E402
import gather_limits                                        # noqa: E402


def _rule():
    print("-" * 62)


def cmd_status():
    cfg = gs.get()
    now = datetime.now()

    print("")
    print("YOUR SETTINGS")
    _rule()
    print("  records system      %s" % crm_paths.vault())
    print("  working days        %s" % ", ".join(cfg["days"]))
    print("  working hours       %s to %s" % (cfg["hours"].get("from"), cfg["hours"].get("to")))
    print("  browser session     %s" % gs.session_dir())
    print("  stale after         %s days" % cfg.get("undo-after-days", 21))
    print("  one run's worth     %s people" % cfg.get("collect-max", 300))

    saved, note = (False, "")
    try:
        import gather_browser
        saved, note = gather_browser.session_status()
    except Exception:                                       # noqa: BLE001
        note = "could not be read"
    print("  signed in           %s" % ("yes" if saved else "not yet - run: %s gather.py login" % PY))

    print("")
    print("THE TWO SWITCHES")
    _rule()
    print("  engine-on           %s" % ("ON" if cfg.get("engine-on") else "off"))
    print("  plan-only           %s" % ("ON" if cfg.get("plan-only") else "off"))
    armed, why = gs.armed()
    print("  so right now        %s" % ("armed - actions are real" if armed else why))

    frac = gs.ramp_fraction()
    print("")
    print("TODAY, BY KIND OF ACTION")
    _rule()
    if frac < 1:
        print("  the ramp is still opening: %d%% of your chosen ceiling today" % int(frac * 100))
    print("  %-10s %-12s %-14s %s" % ("action", "today", "this week", "allowed right now?"))
    for row in gather_limits.report(now):
        ok, reason = row["verdict"]
        week = ("%d of %d" % (row["week"], row["weekly_cap"])) if row["weekly_cap"] else "%d" % row["week"]
        print("  %-10s %-12s %-14s %s"
              % (row["action"], "%d of %d" % (row["today"], row["cap"]), week,
                 "yes" if ok else "blocked"))
        if not ok:
            print("  %-38s %s" % ("", reason))

    # The one allowance nothing else counts. The platform does not publish it and
    # does not warn you, so the count kept here is an estimate that is worth
    # reading before a search rather than after one.
    try:
        import gather_find
        state = gather_find.allowance()
        ok, reason = gather_find.allowance_check()
        print("")
        print("THE MONTHLY SEARCH ALLOWANCE")
        _rule()
        print("  used this month     %d of about %d"
              % (state["used"], gather_find.allowance_size()))
        print("  another search now  %s" % ("yes" if ok else reason))
        if state.get("stopped"):
            print("  a run watched the results collapse, so nothing will search")
            print("  again until the allowance comes back at the start of the month")
    except Exception:                                       # noqa: BLE001
        pass

    print("")
    if not armed:
        print("Everything is refused because %s." % why)
        print("That is the state it arrives in. Turn the switches on in")
        print("  %s" % (crm_paths.vault() / "_layers" / "config.json"))
        print("under \"gather\", when you are ready.")
    print("")
    return 0


def cmd_login(argv):
    site = argv[2] if len(argv) > 2 else "linkedin"
    import gather_browser
    return gather_browser.sign_in(site)


USAGE = """gather - Layer 2, going out and bringing people back

  %(py)s gather.py status              what is set, and what is allowed right now
  %(py)s gather.py login [site]        sign in by hand, once (default: linkedin)

  %(py)s gather.py find <source> [--probe] [--commit]
  %(py)s gather.py undo     [--probe] [--commit]
  %(py)s gather.py ask      [--probe] [--commit]
  %(py)s gather.py accepted [--probe] [--commit] [--confirm]

  sources for find:
    export <file.csv>      a file already on your machine, nothing goes outside
    connections            the people you are already connected to
    search "<terms>"       one broad search, read deep
    reactions <post-url>   everyone who reacted to one post

  every job has the same three modes:
    --probe      read the page, write nothing, change nothing
    (nothing)    plan only: say exactly what it would do
    --commit     do it, one action at a time, each one asked for first

Run this from the _engine folder inside your CRM.
""" % {"py": PY}


def main(argv):
    cmd = (argv[1] if len(argv) > 1 else "status").strip().lower()
    if cmd in ("status", "st"):
        return cmd_status()
    if cmd == "login":
        return cmd_login(argv)
    if cmd == "find":
        import gather_find
        return gather_find.run(argv)
    if cmd == "undo":
        import gather_undo
        return gather_undo.run(argv)
    if cmd == "ask":
        import gather_ask
        return gather_ask.run(argv)
    if cmd == "accepted":
        import gather_accepted
        return gather_accepted.run(argv)
    if cmd in ("help", "-h", "--help"):
        print(USAGE)
        return 0
    print("I do not know the command %r." % cmd)
    print("")
    print(USAGE)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
