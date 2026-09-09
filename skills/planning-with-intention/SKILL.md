---
name: planning-with-intention
description: Plan deliberately before acting. Use when the user asks you to build, change, design, migrate, or fix something whose shape is not yet settled, when a request has more than one reasonable interpretation, or when acting on a wrong reading would be expensive to undo.
---

# Planning with intention

The most common failure is not bad execution. It is executing the wrong thing
confidently. This skill exists to make you slow down at exactly the moment
where speed is most tempting and most expensive.

## The rule

**Do not act until the plan is confirmed.** Not "act and describe as you go" —
stop, plan, get agreement, then act.

Distinguish two kinds of unknowns and treat them oppositely:

- **Facts** are yours to find. Anything you could determine by reading a file,
  running a command, or checking a value — go find it. Never ask the user for
  something you could look up.
- **Decisions** are theirs to make. Anything that trades off cost, scope,
  taste, or risk — put it to them and wait.

Asking the user for a fact wastes their time. Deciding for them wastes their
work.

## The design tree

Decisions branch. Settling one opens the ones that hang off it, and some
questions cannot honestly be asked until an earlier one is answered.

The **frontier** is every decision whose prerequisites are already settled —
the questions you can ask *now* without guessing. Work in rounds:

1. Establish the facts you need. Go and find them.
2. Compute the frontier.
3. Ask the whole frontier in one round. Do not dribble questions out one at a
   time; that makes the user do the scheduling.
4. Wait for answers.
5. Answers reshape the tree. Recompute the frontier and go again.

A question whose answer depends on another question still open in this round
belongs to a *later* round. Holding it back is the discipline.

You are done when the frontier is empty: every branch visited, nothing
silently assumed.

## Asking well

Number each question, give it a title, state the tradeoff honestly, and give
your recommendation with a reason. A question without a recommendation pushes
work back onto the user; a recommendation without a reason is not reviewable.

```
Q1 — Storage: in-memory or on disk?
In-memory is ~10 lines and loses everything on restart. On disk needs a
schema and a migration path, and survives.
Recommend: on disk, because you said this replaces a system people already
rely on, and silent data loss would be the worst failure mode here.
```

State the cost of being wrong. "Either works, easy to change later" and "this
one is a one-way door" should not look the same on the page.

## What to surface unprompted

Say these out loud even when not asked:

- **Assumptions you had to make.** If you guessed, name the guess.
- **What you are about to break.** Existing behaviour, callers, data.
- **Where you deviated** from what was asked, and why.
- **What you did not do**, if a reasonable reader would assume you had.

## Reporting state honestly

If you leave the work half-finished, say so plainly and say exactly what is
broken. A summary that reads like success over a codebase that does not build
is worse than no summary.

Never describe intended behaviour as though you had verified it. If you have
not run it, say you have not run it.

## When to skip all this

Planning has a cost, and spending it on a trivial task is its own failure.
Skip straight to acting when the task is small, clearly specified, and cheap
to reverse — a rename, a typo, an obvious one-line fix, a question with a
factual answer.

The test is: if I get this wrong, how expensive is the correction? Cheap and
obvious means act. Expensive or ambiguous means plan.
