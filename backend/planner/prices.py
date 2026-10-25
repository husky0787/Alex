"""Legacy quote entry points are closed until verified snapshots replace them.

Task 5 will load immutable versions from the market-data repository. Neither a
provider error nor a seeded instruments.current_price may invent a valuation.
"""


class VerifiedPricesUnavailable(RuntimeError):
    pass


def require_verified_analysis():
    raise VerifiedPricesUnavailable(
        "verified_price_snapshot_required: Analysis is unavailable until verified price snapshots are connected."
    )


def get_share_price(symbol) -> float:
    """Do not substitute a random price or bypass the verified ingestion path."""
    require_verified_analysis()
