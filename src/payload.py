"""Workload payload for Mini Grid: fake portfolios and Monte Carlo VaR.

Stdlib only, no numpy, so the worker image needs nothing extra.

Usage from the worker:

    from payload import run_var
    result = run_var(job["params"], progress=callback)

`params` is the job's params dict from /claim:
    {"portfolio_id": 1, "n_sims": 10000, "confidence": 0.99, "seed": 42}

`progress` is optional. It is called after every chunk of simulations with
the fraction done (0.0 to 1.0). To cancel the job (lease lost), raise an
exception from inside the callback; run_var does not catch it.

The result dict matches what /complete already stores.
"""
import heapq
import math
import random
from array import array

TRADING_DAYS = 252
PORTFOLIO_VALUE = 10_000_000.0
N_ASSETS = 10


class JobCancelled(Exception):
    """Raise this from the progress callback to stop run_var early."""


def generate_portfolio(portfolio_id, n_assets=N_ASSETS, total_value=PORTFOLIO_VALUE):
    """Build a deterministic fake portfolio for this portfolio_id.

    Same portfolio_id always gives the same portfolio, so a retried job
    computes the same answer. Each asset has a position value, an annual
    volatility, and a beta to one shared market factor. Using a single
    factor keeps the assets correlated without needing a correlation
    matrix or Cholesky.
    """
    rng = random.Random(f"portfolio-{portfolio_id}")
    weights = [rng.uniform(0.5, 1.5) for _ in range(n_assets)]
    total_weight = sum(weights)
    assets = []
    for i, w in enumerate(weights):
        assets.append({
            "ticker": f"P{portfolio_id}-A{i}",
            "value": total_value * w / total_weight,
            "annual_vol": rng.uniform(0.15, 0.45),
            "beta": rng.uniform(0.3, 0.9),
        })
    return assets


def run_var(params, progress=None, chunk_size=1000):
    """One-day Monte Carlo Value at Risk and Expected Shortfall.

    Each simulation draws one market move plus one idiosyncratic move per
    asset, turns them into a one-day P&L, and records the loss. VaR is the
    loss at the confidence quantile; Expected Shortfall is the average loss
    beyond it. Deterministic for a given params dict.
    """
    portfolio_id = int(params["portfolio_id"])
    n_sims = int(params["n_sims"])
    confidence = float(params["confidence"])
    seed = int(params["seed"])
    if n_sims < 1:
        raise ValueError("n_sims must be at least 1")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be between 0 and 1")

    assets = generate_portfolio(portfolio_id)
    portfolio_value = sum(a["value"] for a in assets)

    # Precompute per-asset daily dollar volatility split into the market part
    # and the asset's own part: r = beta * market + sqrt(1 - beta^2) * own.
    day_scale = 1.0 / math.sqrt(TRADING_DAYS)
    market_loading = []
    own_loading = []
    for a in assets:
        dollar_vol = a["value"] * a["annual_vol"] * day_scale
        market_loading.append(dollar_vol * a["beta"])
        own_loading.append(dollar_vol * math.sqrt(1.0 - a["beta"] ** 2))
    total_market_loading = sum(market_loading)

    rng = random.Random(seed)
    gauss = rng.gauss
    losses = array("d")  # 8 bytes per sim, so large n_sims stays cheap
    done = 0
    while done < n_sims:
        batch = min(chunk_size, n_sims - done)
        for _ in range(batch):
            pnl = total_market_loading * gauss(0.0, 1.0)
            for own in own_loading:
                pnl += own * gauss(0.0, 1.0)
            losses.append(-pnl)
        done += batch
        if progress is not None:
            progress(done / n_sims)

    # Only the tail matters, so pull out the worst losses instead of sorting
    # everything. tail[-1] is the loss at the confidence quantile.
    cutoff = min(int(math.ceil(confidence * n_sims)) - 1, n_sims - 1)
    tail = heapq.nlargest(n_sims - cutoff, losses)
    var = tail[-1]
    expected_shortfall = sum(tail) / len(tail)

    return {
        "portfolio_id": portfolio_id,
        "confidence": confidence,
        "n_sims": n_sims,
        "seed": seed,
        "var": round(var, 2),
        "expected_shortfall": round(expected_shortfall, 2),
        "portfolio_value": round(portfolio_value, 2),
    }


if __name__ == "__main__":
    import json
    import sys
    import time

    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10_000
    start = time.monotonic()
    out = run_var({"portfolio_id": 1, "n_sims": n, "confidence": 0.99, "seed": 42},
                  progress=lambda f: print(f"\r{f:6.1%}", end="", file=sys.stderr))
    print(file=sys.stderr)
    print(json.dumps(out, indent=2))
    print(f"{n} sims in {time.monotonic() - start:.2f}s", file=sys.stderr)
