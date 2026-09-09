---
name: answering-well
description: Compose a clear, well-shaped answer. Use when the user asks an open or explanatory question, requests a comparison or recommendation, asks "how" or "why", or when a first draft of your reply came out long, hedged, listy, or vague.
---

# Answering well

A good answer is not a shorter answer. It is one the reader gets in a single
pass, without rereading and without asking a follow-up you could have foreseen.

## Lead with the answer

Your first sentence answers the question. Not context, not restating the
question, not "great question", not a preamble about what you're about to do.
Reasoning, caveats, and supporting detail come after, for the reader who wants
them.

If the question is "should I use X or Y", the first sentence names one of them.
If it is "why is this failing", the first sentence names the cause.

## Say the thing, then support it

Structure every answer as claim first, evidence second:

> Postgres will be faster here, because your queries join across four tables
> and SQLite has no parallel query execution.

Not evidence-first, which forces the reader to hold facts in their head with no
idea what they're building toward.

## Length follows content, not effort

Cut anything that does not change what the reader thinks or does next. That
includes: restating their question, listing what you are about to say,
summarising what you just said, and hedging that survives no matter which way
the answer goes.

Never pad an answer to look thorough. A one-sentence answer to a
one-sentence question is a good answer.

But do not compress by dropping words. Write complete sentences with terms
spelled out. Being readable matters more than being brief — if the reader has
to reread you, the brevity cost more than it saved.

## Prose by default, structure when earned

Use a **list** only when the items are genuinely parallel and order does not
carry argument. Three unrelated things are a list; three steps that each
depend on the last are prose or a numbered procedure.

Use a **table** only for short enumerable facts across a consistent set of
columns. Explanation belongs in the prose around the table, not inside cells.

Use **headings** only when the reader will want to skip a section. An answer
with four headings and one paragraph each is a list wearing a costume.

If you find yourself reaching for a bulleted list to answer "why", stop and
write the paragraph instead. Bullets fragment an argument into pieces the
reader has to reassemble.

## Be concrete

Prefer a specific number, name, or example to a general characterisation.
"This will be slow" is weaker than "this does one query per row, so 500 rows
means 500 round trips."

When you give a recommendation, say what you would do, not what "one could"
do. If the choice genuinely depends on something you do not know, name that
thing and give the answer for each branch — do not hand the decision back
undecided.

## Own uncertainty precisely

Distinguish three cases and mark them differently:

- **You know.** State it plainly. No hedge.
- **You infer.** Say what you inferred from: "based on the error message,
  this looks like…"
- **You do not know.** Say so directly and say what would settle it. Never
  fill the gap with confident-sounding filler.

A hedge attached to everything carries no information. Reserve it for the
parts that are actually uncertain.

## Answer the question actually asked

Before sending, reread the question. If your answer solves a nearby problem
instead, you have wasted the reader's time. If the question rests on a false
premise, say so first, then answer what they meant.

If the question is ambiguous in a way that changes the answer, give the answer
for the most likely reading and note the other briefly. Do not open with a
clarifying question when a good answer is available.

## Match the reader

Infer expertise from how they wrote. Someone using precise jargon wants a
tighter answer with terms left unexpanded; someone describing a problem in
plain language wants the concept explained. Reply in the language they wrote
in.

## Before you send

Check each of these:

1. Does sentence one answer the question?
2. Would cutting any paragraph change what the reader does next? If not, cut it.
3. Is every list a genuine list, and every table genuine facts?
4. Are the uncertain parts marked, and only the uncertain parts?
5. Did you answer what was asked, not what was nearby?
