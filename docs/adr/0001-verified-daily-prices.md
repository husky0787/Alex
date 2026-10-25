# Keep verified daily observations separate from legacy instrument prices

Use Massive (the existing Polygon integration direction) custom daily REST bars, split-adjusted with `adjusted=true`, in USD for a fixed 20-symbol US universe. Keep immutable observation versions and source-run references in new PostgreSQL tables instead of overwriting `instruments.current_price`: existing seeded/random prices do not carry provenance, and future reports need to retain their chosen price version. The first slice uses AAPL; task 4 adds full-universe backfill/history presentation, and task 5 connects portfolio analysis. ADR 0002 brings removal of the random fallback into task 3, with a temporary analysis guard until those snapshots exist.

Save the raw response before validation; insert validated observations and mark the run complete in one database transaction. Object storage and PostgreSQL do not share a transaction: an object may remain after a failed load. Local private files exercise this boundary now; the S3 adapter targets an explicitly configured private data bucket, separate from frontend hosting. Task 3 adds quarantine, retries and recovery.

Basic-plan freshness uses the latest XNYS trading session before the current America/New_York calendar date: the provider documents REST EOD access after midnight ET. This accounts for weekends, holidays and DST and does not label Monday's not-yet-published bar as missing on Monday evening. The calendar library is version-locked; new emergency closures require a calendar update. Split-adjusted is not dividend-adjusted or a guarantee of point-in-time corporate-action knowledge.

The market-data module uses a PostgreSQL connection URL. The existing account API retains Aurora Data API; connecting market data to deployed Aurora will require its own network/secrets setup during the later controlled cloud deployment. Local validation does not establish cloud connectivity or provider-account entitlement.

Sources: [custom bar contract](https://massive.com/docs/rest/stocks/aggregates/custom-bars), [Basic pricing](https://massive.com/pricing), [publication timing](https://massive.com/knowledge-base/article/what-time-are-massives-flat-files-ready-each-day).

2026-10-25 live verification corrected the original integer-volume assumption: all 63 returned AAPL daily bars contained fractional volume. Preserve nonnegative finite decimals in PostgreSQL NUMERIC and JSON strings, without rounding to whole shares. See https://massive.com/changelog (fractional-share precision update).
