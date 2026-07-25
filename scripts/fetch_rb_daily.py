"""下载并标准化螺纹钢主力连续日线（研究用途）。

数据源为 AKShare 的新浪主力连续接口。主力连续序列并非交易所官方可交割合约，
换月规则可能调整；脚本会同时保存原始字段和可供回测的标准化 CSV。
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path

import akshare as ak


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="20100101")
    parser.add_argument("--end", default=date.today().strftime("%Y%m%d"))
    parser.add_argument("--output", type=Path, default=Path("data/rb_main_sina_daily.csv"))
    args = parser.parse_args()

    raw = ak.futures_main_sina(symbol="RB0", start_date=args.start, end_date=args.end)
    if raw.empty:
        raise RuntimeError("未获取到 RB0 数据；请检查网络、数据源及日期范围")

    raw_dir = args.output.parent / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / "rb0_sina_raw.csv"
    raw.to_csv(raw_path, index=False, encoding="utf-8-sig")

    renamed = raw.rename(columns={"日期": "timestamp", "开盘价": "open", "最高价": "high", "最低价": "low", "收盘价": "close"})
    bars = renamed[["timestamp", "open", "high", "low", "close"]].dropna().copy()
    bars["timestamp"] = bars["timestamp"].astype(str)
    bars = bars.sort_values("timestamp").drop_duplicates("timestamp")
    invalid = (bars["high"] < bars[["open", "close"]].max(axis=1)) | (bars["low"] > bars[["open", "close"]].min(axis=1))
    if invalid.any():
        raise ValueError(f"发现 {int(invalid.sum())} 条不一致 OHLC 数据，已停止写入")
    if len(bars) < 100:
        raise ValueError(f"有效数据仅 {len(bars)} 条，少于研究所需的 100 条")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    bars.to_csv(args.output, index=False, encoding="utf-8")
    metadata = {
        "symbol": "RB0",
        "description": "新浪螺纹钢主力连续日线；仅研究用途，必须独立核验换月规则。",
        "source": "AKShare futures_main_sina",
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "requested_range": {"start": args.start, "end": args.end},
        "actual_range": {"start": bars.iloc[0]["timestamp"], "end": bars.iloc[-1]["timestamp"]},
        "rows": len(bars),
        "raw_file": str(raw_path),
    }
    args.output.with_suffix(".metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已保存 {len(bars)} 根日线：{args.output}")
    print(f"日期范围：{metadata['actual_range']['start']} 至 {metadata['actual_range']['end']}")


if __name__ == "__main__":
    main()
