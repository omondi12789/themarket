from app.execution.allocator import StrategyBounds, compute_allocations, rolling_sharpe


def test_rolling_sharpe_zero_for_flat_returns():
    assert rolling_sharpe([0.01] * 10) == 0.0


def test_rolling_sharpe_zero_for_insufficient_data():
    assert rolling_sharpe([0.01]) == 0.0
    assert rolling_sharpe([]) == 0.0


def test_rolling_sharpe_positive_for_positive_drift():
    returns = [0.01, 0.02, -0.005, 0.015, 0.01, -0.002, 0.02, 0.01, -0.003, 0.012]
    assert rolling_sharpe(returns) > 0


def test_compute_allocations_sums_to_one():
    strategy_returns = {
        "sma_crossover": [0.01, 0.02, -0.005, 0.015, 0.01, -0.002, 0.02, 0.01, -0.003, 0.012] * 2,
        "mean_reversion": [0.005, -0.01, 0.008, -0.003, 0.006, 0.001, -0.002, 0.004, 0.003, -0.001] * 2,
    }
    allocations = compute_allocations(strategy_returns)
    assert abs(sum(allocations.values()) - 1.0) < 1e-9


def test_compute_allocations_favors_higher_sharpe_strategy():
    strong = [0.02] * 15  # consistent 2% gains -> very high Sharpe
    weak = [0.01, -0.015, 0.005, -0.02, 0.01, -0.01, 0.005, -0.015, 0.01, -0.005] * 2  # choppy, near-zero Sharpe

    allocations = compute_allocations({"strong": strong, "weak": weak})
    assert allocations["strong"] > allocations["weak"]


def test_compute_allocations_gives_new_strategy_default_allocation():
    established = [0.01, 0.02, -0.005, 0.015, 0.01, -0.002, 0.02, 0.01, -0.003, 0.012] * 2
    new_strategy = [0.01, -0.01, 0.005]  # only 3 trades, below min_trades_for_sharpe default of 10

    allocations = compute_allocations(
        {"established": established, "brand_new": new_strategy},
        default_allocation_for_new_strategy=0.05,
    )
    # New strategy gets a nonzero allocation despite insufficient history
    assert allocations["brand_new"] > 0
    assert abs(sum(allocations.values()) - 1.0) < 1e-9


def test_compute_allocations_respects_max_bound():
    strong = [0.02] * 15
    weak = [0.001] * 15
    bounds = {"strong": StrategyBounds(max_allocation_pct=0.3), "weak": StrategyBounds()}

    allocations = compute_allocations({"strong": strong, "weak": weak}, bounds=bounds)
    assert allocations["strong"] <= 0.3 + 1e-9
    assert abs(sum(allocations.values()) - 1.0) < 1e-9


def test_compute_allocations_respects_min_bound():
    strong = [0.02] * 15
    weak = [-0.03] * 15  # consistently losing -> would otherwise get pushed toward zero
    bounds = {"strong": StrategyBounds(), "weak": StrategyBounds(min_allocation_pct=0.1)}

    allocations = compute_allocations({"strong": strong, "weak": weak}, bounds=bounds)
    assert allocations["weak"] >= 0.1 - 1e-9


def test_compute_allocations_empty_input():
    assert compute_allocations({}) == {}


def test_compute_allocations_single_strategy_gets_full_allocation():
    returns = [0.01, 0.02, -0.005, 0.015, 0.01, -0.002, 0.02, 0.01, -0.003, 0.012]
    allocations = compute_allocations({"only_strategy": returns})
    assert abs(allocations["only_strategy"] - 1.0) < 1e-9
