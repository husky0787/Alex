# Alex market data

Daily market observations used to show dated, traceable prices alongside the financial-planning application.

## Language

**Daily bar**:
A stock or ETF's open, high, low, close and traded volume for one US trading date. It is not a live quote.

**Verified price**:
A daily bar whose source, trading date, adjustment basis and numeric relationships passed the ingestion checks. Verified describes provenance and validation, not a guarantee that the provider will never revise it.

**Fresh**:
The latest verified bar is for the most recent trading date that should be available under the source's publication schedule.

**Stale**:
A verified bar exists, but it predates the most recent expected publication. The dated bar remains visible with a warning.

**Unavailable**:
No verified bar can be presented. A seeded, random or untraceable legacy price cannot substitute for one.

**Observation version**:
One distinct set of daily bar values for a source, symbol, trading date and adjustment basis. A later provider correction may produce another version.

**Quarantined bar**:
A source record excluded from verified prices because it fails a quality check. Its original response and rejection reason remain available to the operator.

**Partial run**:
An ingestion run that published valid bars but also encountered rejected records or missing expected trading dates.

**Completed through**:
The last consecutive expected trading date covered by valid bars within a run's requested interval. A later valid bar does not close an earlier gap.
