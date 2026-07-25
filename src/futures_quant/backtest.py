"""无账户依赖的日线海龟策略回测器。

信号在第 t 根 K 线收盘计算，委托在第 t+1 根开盘成交。此模块刻意不包含
任何交易网关或账户凭证，目的是先验证研究逻辑与风险假设。
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class Bar:
    timestamp: str
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class Contract:
    symbol: str
    multiplier: int
    tick_size: float
    commission_rate: float
    slippage_ticks: float


@dataclass(frozen=True)
class StrategyConfig:
    entry_window: int
    exit_window: int
    atr_window: int
    fast_ma: int
    slow_ma: int
    risk_per_trade: float
    max_units: int
    initial_cash: float


@dataclass
class Trade:
    side: str
    entry_time: str
    exit_time: str
    quantity: int
    entry_price: float
    exit_price: float
    gross_pnl: float
    costs: float

    @property
    def net_pnl(self) -> float:
        return self.gross_pnl - self.costs


@dataclass
class Result:
    ending_equity: float
    max_drawdown: float
    trades: list[Trade]


def load_bars(path: Path) -> list[Bar]:
    with path.open(newline="", encoding="utf-8-sig") as file:
        rows = list(csv.DictReader(file))
    required = {"timestamp", "open", "high", "low", "close"}
    if not rows or not required.issubset(rows[0]):
        raise ValueError(f"{path} 必须含有列：{', '.join(sorted(required))}")
    bars = [Bar(row["timestamp"], *(float(row[key]) for key in ("open", "high", "low", "close"))) for row in rows]
    if any(bar.high < max(bar.open, bar.close) or bar.low > min(bar.open, bar.close) for bar in bars):
        raise ValueError("OHLC 数据不一致：high/low 与 open/close 不匹配")
    return bars


def atr(bars: list[Bar], index: int, window: int) -> float | None:
    if index < window:
        return None
    true_ranges = []
    for i in range(index - window + 1, index + 1):
        previous_close = bars[i - 1].close
        true_ranges.append(max(bars[i].high - bars[i].low, abs(bars[i].high - previous_close), abs(bars[i].low - previous_close)))
    return sum(true_ranges) / window


def _fill_price(open_price: float, direction: int, contract: Contract) -> float:
    return open_price + direction * contract.slippage_ticks * contract.tick_size


def run_turtle(bars: list[Bar], contract: Contract, cfg: StrategyConfig) -> Result:
    warmup = max(cfg.entry_window, cfg.exit_window, cfg.slow_ma, cfg.atr_window + 1)
    if len(bars) <= warmup + 1:
        raise ValueError(f"数据不足，至少需要 {warmup + 2} 根 K 线")

    cash = cfg.initial_cash
    equity_peak = cash
    max_drawdown = 0.0
    position = 0
    entry_price = 0.0
    entry_time = ""
    entry_cost = 0.0
    trades: list[Trade] = []
    pending: int | None = None

    for i, bar in enumerate(bars):
        # 昨日收盘产生的委托，今天开盘成交。
        if pending is not None:
            desired = pending
            delta = desired - position
            if delta:
                fill = _fill_price(bar.open, 1 if delta > 0 else -1, contract)
                quantity = abs(delta)
                cost = abs(fill * quantity * contract.multiplier) * contract.commission_rate
                if position == 0:
                    position = desired
                    entry_price, entry_time, entry_cost = fill, bar.timestamp, cost
                    # 开仓费用立即扣除，未平仓时的权益也不会高估。
                    cash -= cost
                elif desired == 0:
                    gross = (fill - entry_price) * position * contract.multiplier
                    total_cost = entry_cost + cost
                    cash += gross - cost
                    trades.append(Trade("long" if position > 0 else "short", entry_time, bar.timestamp, abs(position), entry_price, fill, gross, total_cost))
                    position, entry_price, entry_time, entry_cost = 0, 0.0, "", 0.0
                else:
                    raise ValueError("策略只允许平仓或从空仓开仓，禁止同一时点反手")
            pending = None

        mark_equity = cash + ((bar.close - entry_price) * position * contract.multiplier if position else 0.0)
        equity_peak = max(equity_peak, mark_equity)
        max_drawdown = max(max_drawdown, (equity_peak - mark_equity) / equity_peak if equity_peak else 0.0)
        if i < warmup:
            continue

        # 只使用截至当前收盘的历史；pending 保证不会在此根成交。
        recent = bars[i - cfg.entry_window:i]
        exits = bars[i - cfg.exit_window:i]
        closes = [item.close for item in bars[i - cfg.slow_ma + 1:i + 1]]
        fast_ma = sum(closes[-cfg.fast_ma:]) / cfg.fast_ma
        slow_ma = sum(closes) / cfg.slow_ma
        current_atr = atr(bars, i, cfg.atr_window)
        assert current_atr is not None

        if position > 0 and bar.close < min(item.low for item in exits):
            pending = 0
        elif position < 0 and bar.close > max(item.high for item in exits):
            pending = 0
        elif position == 0:
            risk_per_lot = current_atr * contract.multiplier
            units = math.floor((mark_equity * cfg.risk_per_trade) / risk_per_lot)
            units = min(units, cfg.max_units)
            if units > 0 and fast_ma > slow_ma and bar.close > max(item.high for item in recent):
                pending = units
            elif units > 0 and fast_ma < slow_ma and bar.close < min(item.low for item in recent):
                pending = -units

    # 最后一根 K 线不假设未来开盘；持仓按最后收盘盯市，不虚构平仓交易。
    ending_equity = cash + ((bars[-1].close - entry_price) * position * contract.multiplier if position else 0.0)
    return Result(ending_equity, max_drawdown, trades)


def read_config(path: Path) -> tuple[Contract, StrategyConfig]:
    with path.open("rb") as file:
        raw = tomllib.load(file)
    contract = Contract(**raw["contract"])
    strategy = StrategyConfig(**raw["strategy"])
    return contract, strategy


def main() -> None:
    parser = argparse.ArgumentParser(description="研究用途：中国期货日线海龟策略回测")
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="可选：保存 JSON 回测报告")
    args = parser.parse_args()
    contract, cfg = read_config(args.config)
    result = run_turtle(load_bars(args.csv), contract, cfg)
    ret = result.ending_equity / cfg.initial_cash - 1
    print(f"品种: {contract.symbol}")
    print(f"期末权益: {result.ending_equity:,.2f}")
    print(f"收益率: {ret:.2%}")
    print(f"最大回撤: {result.max_drawdown:.2%}")
    print(f"已平仓交易: {len(result.trades)}")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        report = {
            "research_only": True,
            "data_file": str(args.csv),
            "config_file": str(args.config),
            "contract": asdict(contract),
            "strategy": asdict(cfg),
            "metrics": {
                "initial_equity": cfg.initial_cash,
                "ending_equity": result.ending_equity,
                "return": ret,
                "max_drawdown": result.max_drawdown,
                "closed_trades": len(result.trades),
            },
            "trades": [{**asdict(trade), "net_pnl": trade.net_pnl} for trade in result.trades],
        }
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"报告: {args.output}")


if __name__ == "__main__":
    main()
