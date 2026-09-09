---
name: working-with-documents
description: Read and answer questions about files the user uploaded. Use whenever the user attaches a document or refers to one, asks what a file says, wants it summarised or checked, or asks you to find something inside it.
---

# Working with documents

The user attached a document because they want an answer grounded in *that
document*, not in what documents like it usually say. Everything here serves
one goal: never assert something the file does not support.

## Find your way in before reading it all

You have three tools and they are not interchangeable:

- `list_uploaded_files` — what is available. Cheap. Start here when the user
  refers to "the file" without naming it.
- `search_uploaded_files` — where a term appears, with offsets. Cheap.
- `read_uploaded_file` — the text itself. Expensive.

Reading is expensive in a way that is easy to miss: a document you read at
step two is re-sent to you at every later step. A long file read early can
crowd out everything that comes after it.

So for a **targeted question** — "what does it say about pricing?" — search
first, then read around the offsets you got back. For a **whole-document
question** — "summarise this", "review this" — read it properly. Do not
summarise from search excerpts; you will miss the argument.

## Read the whole thing when the whole thing matters

Long files come back in windows, ending with something like
`[12000 characters remain — call again with offset=40000]`.

That notice is not a formality. If you stop there and summarise, you are
describing the first part of a document while implying you read all of it.
Either page through with the offsets, or say plainly that you read the first
N characters and your answer covers only that.

A conclusion usually lives at the end. A document you half-read is a document
whose recommendation you probably missed.

## Quote, don't paraphrase, when precision matters

For anything the user might act on — a figure, a deadline, a recommendation, a
requirement — quote the document's words and mark them as a quote. Paraphrase
is where accuracy quietly leaks.

> The document specifies "a minimum segment length of 20 characters before
> detection is attempted."

Not: *it says short text is skipped* — which loses the number, which is the
part they needed.

## Distinguish the document's view from yours

Three things must never blur together:

- **What the document says.** Attributed: "the analysis recommends…"
- **What you conclude from it.** Marked as yours: "which suggests…"
- **What it does not address.** Said plainly: "it does not cover…"

When the user asks "is this a good approach?", they are asking for your view
*on top of* the document's. Give both, clearly separated. When they ask "what
does it recommend?", they want only the first — your opinion is noise.

## When the document does not answer

Say so. "The document does not state a target latency" is a useful answer and
a common one. Filling that gap with a plausible-sounding number is the single
worst thing you can do with a document, because the user has no way to tell
it apart from a real finding.

If a search returns nothing, try the obvious variants before concluding —
`recommend` for `recommendation`, the singular for the plural, a synonym the
author might have used. A term absent in one form is often present in another.

## Failure modes

- Summarising a truncated read as though it were the whole file.
- Answering from the document's title or headings without reading the body.
- Blending your own domain knowledge into the summary so the user cannot tell
  which parts came from their file.
- Reading a 20,000-character file to answer a question one search would have
  located.
- Quoting a figure without its unit or its qualifier.
