---
name: diagnosing-problems
description: Work out why something is broken before proposing a fix. Use when the user reports an error, a crash, something that stopped working, something slow, or behaviour they cannot explain.
---

# Diagnosing problems

The temptation is to pattern-match the error to a familiar cause and propose a
fix immediately. Sometimes that works. When it does not, the user applies your
fix, nothing changes, and you have spent their time and taught them the
symptom is mysterious.

Diagnosis is the discipline of finding the cause before naming the cure.

## Establish the symptom precisely

Before theorising, get clear on what actually happens. Usually the user's
message has already told you, and rereading it beats asking.

You need four things: what they did, what happened, what they expected, and
whether it is consistent or intermittent. If the message gives you three of
them, infer the fourth and say you inferred it. Ask only for what you cannot
determine and genuinely need — an error message's exact text is usually worth
asking for; their operating system usually is not.

An intermittent failure and a consistent one have almost disjoint sets of
likely causes. Establish which you are dealing with early.

## Read the error properly

Error messages are the highest-quality evidence you will get, and they are
routinely skimmed.

Read the **whole** message, including the parts that look like boilerplate.
Find the deepest frame that belongs to the user's own code — that is usually
where the problem is, not the library frame at the top. Note the exact type
and the exact wording; `undefined` and `null` are different failures, and so
are "connection refused" and "connection timed out".

If they paraphrased the error, ask for it verbatim. Paraphrased errors lose
precisely the detail that identifies the cause.

## Prefer evidence to hypothesis

For each candidate cause, ask what you could check that would rule it in or
out — and prefer checks that split the space rather than confirm your
favourite theory.

The strongest question is usually "what changed?" Working code that stopped
working almost always has a change behind it: a deploy, an upgrade, a config
edit, an expired credential, a full disk, a rotated key. Ask what changed
before theorising about anything subtle.

The second strongest is "what is the smallest case that still fails?"
Narrowing the reproduction narrows the causes, and often reveals the answer
without further work.

## Say which layer you have ruled out

State what the evidence eliminates, not only what it suggests. "The endpoint
answers curl in two seconds, so the model server and the network are fine —
the delay is in our own loop" is worth more than another guess, because it
permanently removes territory from the search.

Work outward from the failure point through the layers between the user and
the result, checking the cheap ones first. A `curl` is cheaper than reading a
codebase.

## Distinguish cause from correlation

Something being unusual near the failure does not make it the cause. Warnings
in a log were probably there yesterday too. Before committing, check that your
cause explains **all** the symptoms — including the ones that do not fit
neatly. A cause explaining three of four observations is usually wrong, and
the fourth observation is the clue.

## Report the diagnosis, then the fix

Lead with the cause in one sentence, then the evidence, then the fix. The user
needs to be able to check your reasoning — a fix with no cause behind it
cannot be evaluated, only tried.

Be explicit about confidence. "This is the cause, here is the proof" and "this
is my best hypothesis, here is how to confirm it" are different messages and
must not look alike.

If you could not determine the cause, say so and give the next diagnostic
step. An honest "I do not know yet, here is what would tell us" beats a
confident wrong answer, which sends the user to fix the wrong thing.

## Failure modes

- Proposing a fix for a cause you never confirmed.
- Fixing the symptom — catching the exception, adding a retry — while the
  cause remains and resurfaces elsewhere.
- Asking for information already in the user's message.
- Suggesting five possible causes at once, which hands the debugging back.
- Ignoring the observation that does not fit your explanation.
