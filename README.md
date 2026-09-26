**This is the Mac version.** On Windows, use [outliers-gather-02-basics](https://github.com/OUTLIERS-ai/outliers-gather-02-basics).

# Outliers Gather — Layer 2 — Going out and bringing people back

Four jobs that find people and put them into the records you already keep.

Layer 1 gave you a browser that can go outside and a doorman standing at a door nobody had
walked through. This layer walks through it. Nothing in it writes to a person and nothing in it
sends a message — a connection request carries none of your words, and that is where this layer
stops on purpose.

---

## Before you start

| | What | How to check |
|---|---|---|
| 1 | **Python 3.8 or newer** | `python3 --version` |
| 2 | **Your CRM**, with its log, resolver, collectors and safety layer | the folder has `_engine/ledger.py`, `_engine/identity.py`, `_engine/collect.py` and `_engine/limits.py` inside it |
| 3 | **Layer 1 of Gather** | the folder has `_engine/gather_limits.py` inside it |
| 4 | **Playwright**, for anything that opens a page | it is in the private Python folder Layer 1 made, `~/outliers-gather-python` |

The installer refuses, by name, if any of the first three is absent. Nothing here costs money.

---

## Install

The `source` line switches Terminal into the private Python folder Layer 1 made, so the installer
finds Playwright:

```
git clone https://github.com/OUTLIERS-ai/outliers-gather-02-basics-mac
cd outliers-gather-02-basics-mac
source ~/outliers-gather-python/bin/activate
python3 install.py
```

It finds your CRM, checks the parts this layer stands on, asks three questions, and copies the
layer into `_engine` inside it.

**Nothing reaches the outside world during installation**, and **both switches are left exactly
as you set them**. An installer that turns something on is an installer you cannot trust with
the next layer.

### The three questions

| Question | What it changes |
|---|---|
| After how many days is an unanswered request stale? | When `undo` will take one back. |
| How many searches a month should it assume you have? | Where `search` stops, rather than finding out by running out. |
| At most, how many people should one reading run bring back? | The size of one sitting. |

### What the installer does that you should know about

- It **replaces the `gather.py` Layer 1 installed**, keeping both of its commands unchanged and
  adding four. If you ever re-run Layer 1's installer, run this one again afterwards.
- It **teaches your log three new words**, written into your own `_engine/settings.json`
  alongside any you wrote: `person_found`, `request_sent`, `request_withdrawn`. Your log refuses
  a word it has never heard of, which is what stops one occurrence ending up with six names, so
  the words go where your own words live rather than being smuggled past the check.

---

## The four jobs

Open Terminal, switch it into the private Python folder, and go into `_engine` inside your CRM (if
your CRM is not at `~/CRM`, put your own folder in the `cd` line):

```
source ~/outliers-gather-python/bin/activate
cd ~/CRM/_engine
```

Then, in that window:

```
python3 gather.py find <source> [--probe] [--commit]
python3 gather.py undo          [--probe] [--commit]
python3 gather.py ask           [--probe] [--commit]
python3 gather.py accepted      [--probe] [--commit]
```

| Job | What it does |
|---|---|
| **find** | Goes out and brings people back, four ways. |
| **undo** | Takes back requests nobody has answered. |
| **ask** | Asks somebody to connect. The only outward action in the layer. |
| **accepted** | Works out who said yes, and records it. |

### The four sources for `find`

| Source | Risk | What it is |
|---|---|---|
| `find export <file.csv>` | none | A file already on your machine. Handed straight to your CRM's own collector. |
| `find connections` | low | The people you are already connected to, read off your own page. |
| `find search "<terms>"` | spends something | One broad search, read deep. Costs one of a monthly allowance you cannot get back. |
| `find reactions <post-url>` | highest | Everyone who reacted to one post. A lot of reading about a lot of strangers in one sitting. |

---

## The three modes, on every job, no exceptions

| Mode | What happens |
|---|---|
| `--probe` | Reads the page and **writes nothing**. Reports what the page actually looks like. |
| *(nothing)* | **Plan only.** Says exactly what it would do. Nothing is done and nothing is written outward. |
| `--commit` | Does it, one action at a time, each one asked for separately. |

**Probe does not go around the doorman.** Opening a page is reaching outside, so `engine-on` has
to be on for a probe to run. What probe does *not* need is the second switch: leave `plan-only`
on and probe still works, because probe does nothing.

**One probe is not free.** `find search --probe` runs a search, and the monthly allowance counts
the search rather than the reading. So that one is asked for and counted exactly like a real
run, and says so when it does. Reporting it as free would make the count wrong for every run
after it.

**`--commit` on the two outward jobs needs both switches.** `ask` and `undo` act on somebody
else, so they need `engine-on` on and `plan-only` off. `find` and `accepted` only write into
your own records, which the first switch already governs.

---

## The order to run them in, the first time

In a Terminal window switched into the private Python folder, in `_engine`:

```
python3 gather.py status                          everything says blocked, as it should
python3 gather.py find export <file.csv>          nothing leaves your machine
python3 gather.py find export <file.csv> --commit

python3 gather.py undo --probe                    look at a page, click nothing
python3 gather.py undo                            see which would be taken back
python3 gather.py undo --commit                   the safest live action there is

python3 gather.py find connections --probe
python3 gather.py find connections --commit

python3 gather.py ask --probe                     look at one profile, click nothing
python3 gather.py ask                             see who is next
python3 gather.py ask --commit                    the first action that reaches a person

python3 gather.py accepted                        once requests have had time to be answered
python3 gather.py accepted --commit
```

`undo` is deliberately the first job you run for real. Everything it does is to your own
requests: nobody is contacted and the only person affected is you. If the controls on your
account are spelled differently to the ones assumed here, that is where you want to find out.

---

## What is proven, and what is not

This matters more than anything else in this README, so it is not at the bottom.

**The export path is proven.** It is your CRM's own collector, which your CRM's own tests cover.

**The three page-reading paths are not.** They are inherited from a working system where
`search`, `reactions` and `connections` were **written but barely run** — somewhere between two
and eleven runs each, ever — and where the page selectors were left marked as best guesses that
were never confirmed against a live account. This layer inherits that state exactly. The
reasoning behind them has been paid for; the selectors have not.

So:

- `--probe` is the **documented first step for each one**. Run it, read what it says the page
  looks like, and only then trust the reader.
- If a probe reports zero profile links or zero cards, the reader is looking at the wrong part
  of the page. The selectors are at the top of the module and are meant to be changed.
- Nothing here claims these are proven, and you should not treat a run that appears to work as
  proof either. One run that worked is one run that worked.

**What has been paid for elsewhere, and is worth having:** the pattern of reading a list while
scrolling rather than at the end; reading the age of a request off the clause that states it;
matching a person by their profile address rather than by two spellings of their name; and
never clicking a control that does not carry the address of the person you meant.

---

## Where everything ends up

Everything found is written into **your CRM's own event log**, through **your CRM's own
resolver**. Not a file of this layer's own, not a second list of people.

- Somebody your records already have is attached to them.
- Somebody they do not have gets a provisional record in `_staging/`, written by your own
  collector, and **nothing is merged into anybody**. A merge is a decision about which history
  is right, and it stays yours.
- Somebody nothing can identify is still recorded, with the raw identifiers kept. A person the
  log cannot attach is a gap worth looking at, not something to throw away.

Running any job twice is safe. Every person carries a fingerprint built from what was seen, so
the same export, the same post and the same search can be run again and only what is new lands.
The fingerprint for a connection is deliberately the same shape your own collector writes, so
importing an export and reading the page do not both land the same person.

---

## The three limits that are not yours to set

| Limit | What happens | What this does |
|---|---|---|
| **The monthly search allowance** | Roughly 250–350 searches, spent by *searching* and not by what comes back. Past it, results collapse to about three per query until it resets at the start of the next month. | Refuses to start a search when the count is spent, and stops the moment it watches results collapse. `status` shows how much is left. |
| **The ceiling on one post's reactions** | Around 1,218 people per post. Past that, the list hands nothing else back however long you scroll. | Stops there. |
| **The ceiling on outstanding requests** | Once you are at it, new requests fail whatever your own limits say. | `undo` is what keeps room. |

The first one is why `search` is one broad query read deep, never many narrow ones. The
allowance counts the search, not the results.

---

## What is in here

| File | What it is |
|---|---|
| `engine/gather_job.py` | The shape every job has: mode, doorman, window, counting, report |
| `engine/gather_record.py` | The bridge into your CRM's log and resolver |
| `engine/gather_pending.py` | The list of unanswered requests, read once, used by two jobs |
| `engine/gather_find.py` | The four sources |
| `engine/gather_ask.py` | The one outward action |
| `engine/gather_undo.py` | Taking requests back |
| `engine/gather_accepted.py` | Telling an acceptance from a disappearance |
| `engine/gather.py` | The command you type. Replaces Layer 1's and keeps both of its commands |
| `tests/test_jobs.py` | The proof |

---

## The tests are the proof

```
python3 tests/test_jobs.py
```

| Exit code | What it means |
|---|---|
| **0** | Everything passed. |
| **1** | Something failed. The line that failed says what. |
| **2** | Your CRM was not found, so the tests stopped rather than run a shorter version of themselves. Not a fault in this layer — install your CRM and run it again. |

They find your CRM the same way the installer does, and never by a path relative to this
folder. A test that reaches back into the folder it was written in passes for its author and
fails for everybody who clones it.

If your CRM is somewhere unusual, point at it:

```
OUTLIERS_CRM=/path/to/your/CRM python3 tests/test_jobs.py
```

No browser and no network: everything happens in a throwaway CRM built for the run, and your
real records are read to borrow the modules this layer stands on and never written to.

What they check, and why each one is there:

- **Every job stops with the engine off, having opened nothing.** A job that asks the doorman
  after opening a browser has already reached the outside world before anybody said it could.
  These checks would pass on a machine with no browser installed, which is the point.
- **Nothing in the layer can type into a page.** The promise that a request carries none of your
  words is worth nothing if nobody checks it, so the tests read the layer's own source.
- **Only `ask` and `undo` can act on a person**, and every click elsewhere is one that moves
  around a page you are already reading.
- **The doorman is asked before the count is written**, in every job, in the source.
- **A person found by two paths is one connection**, not two.
- **The two ceilings hold** — the reactions reader is given a list that never runs out and still
  stops at 1,218.
- **A spent search allowance stops the run before a page is opened**, rather than being
  discovered by spending the last one.

---

## What this layer leaves unsolved

You can now find people, ask them, clear the ones who never answered, and know who said yes.
What you cannot do is say anything to any of them, and that is the next problem rather than an
oversight. Reaching out and speaking are separate switches on purpose, and the second one is
worth turning on slowly.

**Next: Layer 3 — Saying something.**

This repo is made automatically from outliers-gather-02-basics@d4840c8. To report a problem or suggest a change, use that repo, not this one.
