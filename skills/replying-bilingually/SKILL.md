---
name: replying-bilingually
description: Handle Arabic, English, and mixed-language messages correctly. Use when the user writes in Arabic or another non-English language, mixes languages in one message, asks you to translate, or asks about text whose language is uncertain.
---

# Replying bilingually

Getting language wrong is not a style error. Answering an Arabic question in
English tells the user their language was an obstacle you worked around.

## Reply in the language they wrote in

Default: match the user's language exactly. Arabic question, Arabic answer.
English question, English answer.

Two exceptions, both narrow:

- They asked you to answer in a particular language. Do that.
- They switched languages mid-conversation. Follow the switch; it is
  deliberate. Do not keep replying in the earlier language.

A one-word greeting is not a language signal. Judge from the substance of the
message, not from `مرحبا` on its own line.

## Mixed-language messages

Mixing is normal, not a mistake to correct. An Arabic sentence carrying
English technical terms — `عايز أعمل caching للـ API` — is how practitioners
actually write.

Reply in the **matrix language**: the one carrying the grammar, here Arabic.
Keep the technical terms in the form they used. Translating `caching` to
`التخزين المؤقت` when they wrote `caching` makes the answer harder to read,
not more correct. Established loanwords stay as loanwords.

If they wrote the concept in Arabic, answer in Arabic. Follow their lead term
by term rather than imposing one policy on the whole reply.

## Arabic that reads like Arabic

Write Arabic a native speaker would write, not English reassembled with Arabic
words. Watch for:

- **Calqued syntax.** English sentence order forced into Arabic reads
  translated. Let the verb sit where Arabic wants it.
- **Dialect drift.** Match the user's regional dialect for the whole reply.
  Levantine/Jordanian cues (`احكيلي`، `أكتر`، `بدي`، `هيك`، `مش`، `شو`، `ليش`)
  → stay Levantine (`شو` / `ليش` / `بدي` / `هيك` / `مش`). Never slip into Gulf
  (`وش` / `تبي` / `أبي` / `هالقدر`) unless they wrote that way.
  Gulf (`وش`، `تبي`) → stay Gulf. Egyptian (`عايز`، `كده`) → stay Egyptian.
  Clear MSA → clear MSA.
- **Broken collocations.** Prefer natural phrases: Levantine
  «أحكي لك أكتر عن حالي» not «أكثرك عن نفسي».
- **Over-formality.** Match their register. Someone writing casual Levantine
  does not want Classical prose back.
- **Numbers and units.** Use the digit form they used — Western `123` or
  Arabic-Indic `١٢٣` — consistently within a reply.
- **Punctuation.** Arabic comma `،` and question mark `؟`, not `,` and `?`.

Formatting conventions are unchanged: lead with the answer, keep code and
identifiers in Latin script and left-to-right, and do not translate file
names, commands, or error messages.

## Translation requests

When asked to translate, translate — do not also explain, summarise, or
improve the text unless asked.

Preserve register: a blunt sentence stays blunt, a formal one stays formal.
Preserve structure: line breaks, lists, and headings map across.

When a term has no clean equivalent, give your best rendering and note the
original in parentheses once. Flag genuine ambiguity rather than silently
picking a reading — Arabic without diacritics is often ambiguous in ways the
author would want to resolve themselves.

## Uncertain or mixed-script input

If you cannot tell what language a fragment is in, say so and ask, rather than
guessing and answering the wrong question. Short strings, proper nouns, and
transliterated text are genuinely ambiguous — `salam` could be several things.

Script is a strong signal but not proof: Arabic script covers Arabic, Persian,
and Urdu, and Latin script covers most of Europe. Content decides, not
alphabet.

## Failure modes

- Answering in English because the *topic* is technical, when the question
  was in Arabic.
- Translating technical terms the user deliberately wrote in English.
- Apologising for or commenting on their language choice.
- Mixing digit systems inside one answer.
- Producing stiff Modern Standard Arabic in reply to a casual dialect message.
- Mixing Gulf and Levantine in one reply (e.g. user said `احكيلي` / `شو` and
  you answered with `وش` / `تبي`).
