# What I stole

Nothing in this layer is original, and none of it cost anything. Naming where each idea came
from is the practice, not a courtesy — you should be able to do the same on your next build,
and knowing what already exists is most of the work.

This layer takes more from other people than Layer 1 did, because Layer 1 was mostly a set of
refusals and this one has to actually work against pages somebody else designed.

---

## Your own CRM — the log, the resolver, the collectors

Three separate borrowings, and all three replace code that would otherwise have been written
here.

**The resolver.** Deciding that a profile link, an email address and a bare name are one person
is the hardest part of any system of this kind, and it never stops being hard. Your CRM answers
that question in one place. This layer asks that place. A second resolver would answer
differently on some people, and the disagreement stays invisible until something goes wrong in
a way nobody can explain.

**The log.** Every event goes through your CRM's own writer, so the append-only contract, the
closed vocabulary and the behaviour on a crash are the ones you have already tested. Nothing
here opens that file directly.

**The collectors.** `find export` does not read your file. It hands it to your CRM's collector,
which already reads exports, already writes through the resolver, and already refuses to count
a row twice. Writing a second reader for the same file shape would have taken an afternoon and
produced two answers to one question, disagreeing the first time an export changed.

**The part worth noticing.** The single most useful decision in this layer is a decision not to
build three of them.

---

## Playwright — Microsoft, Apache 2.0

The browser control, exactly as Layer 1 uses it. It drives a genuine browser the way a person
drives one: clicking real controls, scrolling real lists.

**What was deliberately NOT taken**, again: the family of add-ons that disguise an automated
browser. This runs on your own machine, on your own connection, in a real browser, which is
already the most ordinary set of details a site can see. The honest fingerprint is the asset.

---

## The reading patterns — from a working outreach system, 2026

Four mechanisms, each of which exists because somebody paid for the lesson.

**Read a list AS you scroll, never at the end.** Long lists on these pages are virtualised: the
page holds the rows you can see and throws away the ones you have scrolled past. A reader that
scrolls to the bottom and then reads gets the last screenful and looks like it worked. This is
why `connections` and `reactions` accumulate as they go.

**Pull the last item into view to load more.** These lists sit in their own scrolling area, so
turning the wheel on the window does nothing at all. Bringing the last item that exists into
view is what makes the area fetch the next batch. The same mechanic drives every long list here.

**Read the age off the clause that states it.** A pending request says how long ago it was sent
and also carries the person's headline, which frequently contains a number of years. A reader
that takes the first number it sees decides a request is twenty years old and takes it back.
There is a test for this, with a card that contains both.

**Match a person by their address, never by their name.** In the system this came from, requests
were sent from a search row that never resolved a public profile, so an entire cohort of people
was held with no address at all — and the accept-detection that followed compared display names
across two pages that render names differently. Nothing was ever confirmed. The pile of people
it could not resolve grew from 2 to 142 and every run recomputed the same wrong answer.

That is why this layer reads the profile address off every card while the page is open — it is
free, and it is the strongest identifier there is — and why the two comparisons in `accepted`
are deliberately lopsided: generous about who is still waiting, strict about who accepted. A
wrong "still waiting" costs one run's delay. A wrong "accepted" puts a stranger in your records
as somebody you connected to.

---

## The limits that belong to the platform, not to you — published research, 2026

**The monthly search allowance.** Roughly 250 to 350 searches on an ordinary account, spent by
searching rather than by what comes back, collapsing to about three results per query until it
resets at the start of the next month. The consequence is the design: one broad query read
deep, never many narrow ones.

**The ceiling on one post's reactions.** Around 1,218 people. Observed rather than published, and
written down here so that a run ends at a number somebody chose rather than in a loop that never
finishes.

**The ceiling on outstanding requests.** Once you are at it, new requests fail whatever your own
limits say, which is the whole reason `undo` exists as a job rather than as tidying.

These are ranges reported by people who watched them, not figures any platform publishes. They
are treated as directional, and nothing here depends on one of them being exactly right.

---

## What was taken with its failures attached

The three page-reading paths — `search`, `connections` and `reactions` — come from a system where
they were **written and then barely run**: somewhere between two and eleven runs each, ever, with
the page selectors left marked as best guesses that were never confirmed against a live account.

They are taken anyway, because the reasoning in them is worth having and the selectors are the
cheap part to fix. What is not taken is the impression that they work. Every one of them carries
the same note in its own file, `--probe` is the documented first step for each, and the README
says it before it says anything else.

**The lesson underneath, which is the actual theft.** Code that was written but never run reads
exactly like code that runs every day. Nothing about it looks unfinished. The only difference is
whether somebody wrote down which of the two it is — so this layer writes it down.

---

## The safest live action first — from nothing in particular, and it should have been obvious

`undo` acts only on your own requests. Nobody is contacted and the only person affected is you.
That makes it the sensible action to run for real before any other, because it is the one where
being wrong costs least, and it exercises the same window, the same doorman and the same
recording path as everything else.

---

## What nothing here does

No paid service. No account with anybody. No key, token or subscription. No message to any
person: a connection request carries none of your words, and there is no place in this layer
where text is entered into a page. The tests check that rather than the README claiming it.
