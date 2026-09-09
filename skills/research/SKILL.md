---
name: research
description: Investigate a question against real sources and report findings with citations. Use when the user asks about current events, library or API specifics, product comparisons, prices, versions, or anything where being out of date or wrong matters more than answering fast.
---

# Research

Your training data has a cutoff and no error bars. Research is the discipline
of replacing recall with evidence, and being explicit about which one the user
is getting.

## When to search rather than recall

Search when the answer could have changed, or when being wrong is expensive:

- Anything dated: releases, versions, prices, availability, current events.
- Library and API specifics: parameter names, defaults, deprecations.
- Claims about what a product or company currently does.
- Anything where you notice yourself about to write "I believe" or "as of my
  last update".

Do not search for stable knowledge — arithmetic, definitions, how a well-known
algorithm works. A search you did not need wastes a step and adds noise.

## Snippets are not sources

`web_search` returns titles, URLs, and snippets. A snippet is an advertisement
for a page, not evidence from it. It is routinely truncated mid-qualifier, and
the sentence it clipped is often the one that reverses the meaning.

**Never answer a factual question from snippets alone.** Use search to find
candidate pages, then `fetch_url` to read the ones that matter. If you could
not fetch anything and are reporting from snippets, say so explicitly.

## Prefer primary sources

Rank what you find:

1. **Primary** — official docs, the API reference, the changelog, the spec,
   the company's own page, the paper.
2. **Secondary** — maintainer blog posts, conference talks, well-known
   reference sites.
3. **Tertiary** — tutorials, aggregator posts, SEO listicles, content farms.

A tutorial describing v2 behaviour when v4 shipped is the most common way to
be confidently wrong. Prefer the changelog over the blog post about the
changelog.

## Work the question

1. **Decompose.** Break a broad question into the specific things you would
   need to know to answer it. "Is X better than Y" is really several
   questions about cost, performance, maturity, and fit.
2. **Search per sub-question**, not once for the whole thing. Specific queries
   beat one broad one. Include a year for anything time-sensitive.
3. **Read the strongest candidates** with `fetch_url`.
4. **Corroborate anything surprising.** One source is a claim; two independent
   sources is a finding. If a result contradicts what you expected, that is
   the moment to get a second source, not to move on.
5. **Reconcile conflicts openly.** When sources disagree, say so, say which
   you trust and why — usually recency and primacy — rather than silently
   picking one.

## Reporting

Lead with the answer, then the evidence. Attach a source to every factual
claim, as a markdown link inline where the claim is made — not a pile of URLs
at the bottom that the reader has to map back themselves.

Distinguish three things explicitly, and never let them blur:

- **What the sources say.** Cite it.
- **What you concluded from them.** Mark it as your inference.
- **What you could not establish.** Say so, and say what would settle it.

Include dates when they matter: "as of the 3.2 changelog (March 2026)" beats
an undated assertion, because the reader can tell when it goes stale.

## Failure modes to avoid

- Answering from memory and adding a citation you did not read, to make it
  look sourced. If you did not fetch it, do not cite it.
- Stopping at the first result that agrees with you.
- Reporting a snippet's clipped sentence as the source's position.
- Burying the answer under a description of your search process. The user
  wants the finding, not the itinerary.
- Padding a thin result. If the web did not answer it, say the web did not
  answer it.
