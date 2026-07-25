import unittest

from futures_quant.backtest import Bar, Contract, StrategyConfig, run_turtle


class TurtleBacktestTest(unittest.TestCase):
    def test_insufficient_data_fails_clearly(self):
        bars = [Bar("2024-01-01", 100, 101, 99, 100)] * 4
        contract = Contract("TEST", 10, 1, 0.0, 0.0)
        cfg = StrategyConfig(3, 2, 2, 2, 3, 0.01, 4, 100_000)
        with self.assertRaises(ValueError):
            run_turtle(bars, contract, cfg)

    def test_never_forces_one_lot_over_risk_budget(self):
        bars = [Bar(str(i), 100, 150, 50, 100) for i in range(30)]
        contract = Contract("TEST", 10, 1, 0.0, 0.0)
        cfg = StrategyConfig(3, 2, 2, 2, 3, 0.000001, 4, 100)
        result = run_turtle(bars, contract, cfg)
        self.assertEqual(result.trades, [])


if __name__ == "__main__":
    unittest.main()
