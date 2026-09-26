"""
gather_job.py - the shape every job in this layer has, so that none of them can
quietly have a different one.

Four jobs go out. Every one of them, without exception:

    1  reads its mode off the command you typed
    2  asks the doorman, BEFORE anything opens
    3  opens the one window, and stops if you are not signed in
    4  does the work, counting as it goes, asking again before each action
    5  prints what happened, in the same words every time

WHY THIS IS A MODULE AND NOT A HABIT. Written out four times, the order survives
until the fourth job is written in a hurry, and then one job asks the doorman
after opening the window, or records an action before taking it, and nothing looks
wrong from outside. Written once, there is one place the order lives and one place
to read it. The tests point at this file for that reason.

THE THREE MODES

    --probe     read the page and write NOTHING. Reports what the page actually
                looks like. This is the first step for every job, every time.
    (default)   plan only. Works out exactly what it WOULD do and says so. Writes
                nothing outward.
    --commit    does it, one action at a time, each one asked for separately.

The reason probe exists at all is that a page you have not looked at is a page you
are guessing about. Every reading job in this layer inherits selectors from a
system where they were written and barely run, so the honest first move is to
open the page and see.

WHAT PROBE DOES NOT DO. It does not go around the doorman. Probe opens a page, and
opening a page is reaching outside, so the engine has to be on. What probe does not
need is the second switch: plan-only can stay on, because probe does nothing. If
probe refuses and you want to run it, turn `engine-on` on and leave `plan-only`
alone.

Needs: Python 3.8 or newer. The window needs Playwright.
"""

import sys
from contextlib import contextmanager
from pathlib import Path

# What a member types to start Python. A Mac has `python3` and no plain `python`; Windows
# keeps `python`, exactly as before.
PY = "python3" if sys.platform == "darwin" else "python"

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gather_settings as gs                                # noqa: E402
import gather_limits                                        # noqa: E402
import gather_record                                        # noqa: E402

PROBE = "probe"
PLAN = "plan"
COMMIT = "commit"


def mode_of(argv):
    """Which of the three modes was asked for. Plan is the default and always has
    been: a command typed with no flags must never act."""
    if "--probe" in argv:
        return PROBE
    if "--commit" in argv:
        return COMMIT
    return PLAN


def rule():
    print("-" * 62)


def banner(job, mode):
    print("")
    print("=" * 62)
    print("  %s   [%s]" % (job, {
        PROBE: "probe - reading the page, writing nothing",
        PLAN: "plan only - nothing is done, nothing is written",
        COMMIT: "commit - this one is real",
    }[mode]))
    print("=" * 62)


def doorman(action):
    """Ask before anything opens. Returns True to carry on.

    Asked first because the cheapest refusal is the one that happens before a
    browser starts. It is also the only order in which the reason you are given is
    about your settings rather than about a page that failed to load.
    """
    ok, why = gather_limits.can_act(action)
    if not ok:
        print("")
        print("  Not now: %s." % why)
        print("")
        print("  Nothing was opened and nothing was written. Run")
        print("      %s gather.py status" % PY)
        print("  to see every limit and which one stopped this.")
        print("")
    return ok


def outward_allowed():
    """The extra gate on the two jobs that do something to another person.

    Reading a page and writing to your own records are governed by the first switch.
    Sending a request, or taking one back, is governed by both, because that is the
    difference the second switch was put there to make.
    """
    armed, why = gs.armed()
    if not armed:
        print("")
        print("  Not now: %s." % why)
        print("")
        print("  This job acts on somebody else, so it needs both switches on.")
        print("  They live in %s under \"gather\"." % (gs.config_path()))
        print("")
    return armed


def records_ready():
    """Can anything found actually be recorded? Asked before the reading starts."""
    absent = gather_record.missing_parts()
    if absent:
        print("")
        print("  Your CRM is missing %s." % ", ".join(absent))
        print("  Everything this layer finds is written into your own records, so")
        print("  there is nowhere to put it. Nothing was opened.")
        print("")
        return False
    ok, why = gather_record.vocabulary_ready()
    if not ok:
        print("")
        print("  %s" % why)
        print("")
        return False
    return True


@contextmanager
def one_window(site="linkedin"):
    """The window Layer 1 built, opened on its ordinary front page first.

    Yields a page, or None if you are not signed in. Landing on the front page is
    not politeness: going straight to a deep address is the clearest sign there is
    that nobody human is driving, and the hop costs a couple of seconds.
    """
    import gather_browser as gb
    import gather_walk as walk

    with gb.window(site) as page:
        try:
            walk.open_page(page, gb.SITES[site]["home"])
        except Exception:                                   # noqa: BLE001
            pass
        if not gb.looks_signed_in(page, site):
            print("")
            print("  I cannot see your account on that page. Sign in once:")
            print("      %s gather.py login" % PY)
            print("")
            yield None
        else:
            yield page


class Tally:
    """The counts a job keeps while it runs, printed in the order they were added.

    Kept as it goes rather than worked out at the end, so a run stopped halfway --
    by the doorman, by a page that would not load, by you -- still reports what
    actually happened up to that point.
    """

    def __init__(self):
        self.rows = {}
        self.notes = []

    def add(self, key, n=1):
        self.rows[key] = self.rows.get(key, 0) + n
        return self.rows[key]

    def note(self, text):
        if text and text not in self.notes:
            self.notes.append(text)

    def get(self, key):
        return self.rows.get(key, 0)

    def show(self, title=None):
        print("")
        if title:
            print(title)
            rule()
        for key, n in self.rows.items():
            print("  %-28s %d" % (key, n))
        for text in self.notes:
            print("")
            print("  %s" % text)
