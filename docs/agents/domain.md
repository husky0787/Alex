# Domain documentation

Use a single-context layout: `GLOSSARY.md` at the repository root and architectural decision records under `docs/adr/`.

## Before exploring or designing

Read the glossary and ADRs relevant to the area being changed. If they do not exist, proceed silently. Create terms and decisions through domain-modeling as they are resolved; setup does not prepopulate a glossary or invent ADRs.

## Shared vocabulary

Use glossary terms consistently in specs, tickets, code discussions, and tests. For a missing term, check existing project usage first and record a real terminology gap through domain-modeling.

## Decisions

Use numbered descriptive ADR filenames such as `docs/adr/0001-market-data-source.md`. Record decisions when made, including their context and consequences. Explicitly identify any proposal that conflicts with an existing ADR and explain why that decision should be revisited.
