---
name: skill-creator
description: >
  Create or improve Agent Skills for this product. Use when the user wants a new
  skill, to rewrite a skill's description or body, or to turn a workflow into a
  reusable skill. Also use when drafting skills from the Skills page Generate
  button. Prefer this whenever someone says "make a skill", "skill for X", or
  "teach the agent how to…".
---

# Skill creator (this product)

Write skills that this agent can load with `read_skill`. A skill is a short
Markdown playbook: **when** it applies (description) and **how** to act (body).

Do **not** invent Claude Code / Cursor shell workflows, eval harnesses, or
filesystem layouts under `~/.claude`. Here, user skills are saved in the
database via the Skills UI (or API). Built-in skills live under `skills/`.

## Capture intent

Answer these before drafting:

1. What should the agent do when this skill loads?
2. What user phrases / situations should trigger it?
3. Expected output (chat reply, `.docx`, table, checklist, …)?
4. Hard rules or brand constraints?

If the user's request is already specific enough, draft immediately.

## Anatomy

```text
name: kebab-case-id
description: What it does AND when to use it (pushy triggers).
body: Markdown instructions (imperative, concrete, < ~500 lines ideal)
```

### Description (critical)

The description is the **only** thing in the system prompt until `read_skill`
runs. Under-triggering is common — make descriptions a little pushy:

- Bad: "How to review code."
- Good: "Review pull requests and code diffs for bugs, security, and clarity.
  Use whenever the user asks for a code review, PR review, or feedback on a
  patch — even if they only paste code without saying 'review'."

Put all "when to use" cues in the description, not only in the body.

### Body

- Imperative voice ("Check X", "Prefer Y").
- Explain *why* when it helps the model choose correctly.
- Define output formats with exact templates when structure matters.
- Include 1–2 short examples when format is non-obvious.
- Prefer general rules over one-off narrow cases.
- No malware, no surprise side effects, no instructions to hide intent.

### Progressive disclosure

Keep the body focused. If a topic is large, use clear headings so the model can
scan; do not dump unrelated domains into one skill.

## Tools in this product

When the skill needs product tools, name them exactly as they exist here, e.g.
`read_skill`, `write_file`, `convert_upload_to_docx`, `ask_user`, `run_python`,
`list_uploaded_files`. Do not reference tools this agent does not have.

## Output when drafting for the Skills UI / generate API

Return **only** a JSON object (no fences, no commentary):

```json
{
  "name": "kebab-case-id",
  "description": "pushy one-to-two sentence trigger line",
  "body": "# Title\n\nMarkdown instructions…"
}
```

`name` must start with a letter and use only lowercase letters, digits, hyphens.
`description` under 500 characters. `body` under ~800 words unless the user
asked for a long playbook.
