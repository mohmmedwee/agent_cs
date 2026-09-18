---
name: writing-deliverables
description: Produce a document as a downloadable file rather than as chat text. Use when the user asks for a report, summary, spec, plan, memo, README, or code file, or says to save, write, or export something.
---

# Writing deliverables

A deliverable is read later, by someone who was not in this conversation, with
no way to ask you a follow-up. That single fact drives every choice here.

## Decide where it belongs

Use `convert_upload_to_docx` when the user **already uploaded** Markdown/text
and wants a Word file from it (especially long reports). To change content,
pass small `replacements` or per-heading `sections` on that tool — do not
rewrite the upload through `write_file`.

Use `write_file` when the output is a **new short artifact** you must compose
from scratch — a report, a spec, a README, a script, a memo.

Answer in chat when the output is a **reply** — an explanation, a
recommendation, a short summary the user will read once and act on.

When unsure, ask which they want, or do both: write the file and give the
headline finding in chat. Do not silently dump 2,000 words into the chat when
they asked for a document, and do not write a file when they asked a question.

Never do both at full length. Writing the file and then reproducing it
verbatim in chat wastes the user's screen and your context.

## Write for the absent reader

The reader lacks everything you have: the question that prompted this, the
document you read, the constraints they mentioned three messages ago. So:

- **Open with what this is and why it exists.** One or two sentences. A
  document that starts mid-argument is unusable.
- **Never refer to the conversation.** No "as we discussed", "the file you
  uploaded", "per your question". Name the thing directly.
- **Resolve every pronoun and shorthand.** "The service" is fine only if the
  document has already said which service.
- **Date anything time-sensitive**, so a reader in six months knows whether
  it has gone stale.

## Structure it as a document, not a transcript

Give it a title. Use headings the reader can scan and skip by. Put the
conclusion near the top — an options analysis whose recommendation appears
only on page four will be misread by everyone who skims.

Match the form to the type:

- **Report or analysis** — purpose, findings, recommendation, then supporting
  detail.
- **Spec** — what is being built, constraints, the design, what is explicitly
  out of scope.
- **Plan** — the goal, the steps in order, and who or what each step needs.
- **Code** — runnable as written, with imports; comments only where the code
  cannot speak for itself.

## Pick a visual theme

`.docx` files support named themes via YAML front matter. Start every document
with a block like:

```
---
title: Cats — a short overview
theme: cleverso
toc: true
page_numbers: true
---
```

Choose by intent — do not default everything to the same look:

| Theme | Use when |
|-------|----------|
| `cleverso` | Branded / product / Cleverso-facing docs |
| `classic` | Formal reports, essays, long-form reading |
| `modern` | Specs, technical notes, clean handouts |
| `warm` | Friendly guides, onboarding, soft topics |
| `editorial` | Neutral default when nothing else fits |

If the user names a look ("make it purple", "formal", "warm"), map it to the
closest theme above. If they only say "restyle" / "brand it" with no colors or
theme, ask once with a short list of options before you convert.

For Word (`.docx`), also load the `docx` skill: it explains front matter, TOC,
and that **tables get theme-colored headers automatically** — use Markdown pipe
tables, never ASCII. Do not use pandoc or npm `docx` scripts; use `write_file`.

## Choose a real filename

Lowercase, hyphenated, with a correct extension: `caching-options.md`, not
`Document1` or `output.txt` for markdown. The extension tells the user's
editor what to do with it. If they named it, use their name exactly.

## Accuracy carries over

Everything true of a chat answer is more true here, because a file gets
forwarded, quoted, and pasted into other documents with your caveats stripped
off.

Do not invent figures to fill a table. Do not present inference as finding.
If the source material did not cover something the document's structure seems
to promise, write "not assessed" rather than something plausible. A confident
document is trusted more than it deserves — write accordingly.

## After writing

Tell the user what you wrote, the download link the tool gave you, and the
one thing they most need to know from inside it. Then stop. The point of a
file is that they can open it.
