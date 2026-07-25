"""研究用途：迁移桌面 ADX 双模逻辑的无账户回测。

信号只使用前一交易日及更早数据，按当日开盘成交。趋势模式为 SMA+唐奇安，
震荡模式为 RSI+布林带；所有参数仅作研究，不代表可交易策略。
"""
import argparse, json
from pathlib import Path
import pandas as pd


def indicators(df):
    high, low, close = df.high, df.low, df.close
    prev = close.shift(1)
    tr = pd.concat([high-low, (high-prev).abs(), (low-prev).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    up, down = high.diff(), -low.diff()
    plus = up.where((up > down) & (up > 0), 0.0).rolling(14).mean()
    minus = down.where((down > up) & (down > 0), 0.0).rolling(14).mean()
    pdi, mdi = 100*plus/atr, 100*minus/atr
    adx = (100*(pdi-mdi).abs()/(pdi+mdi)).rolling(14).mean()
    delta = close.diff(); gain = delta.clip(lower=0).rolling(14).mean(); loss = (-delta.clip(upper=0)).rolling(14).mean()
    rsi = 100 - 100/(1 + gain/loss.replace(0, float('nan')))
    mid = close.rolling(20).mean(); std = close.rolling(20).std()
    return pd.DataFrame({"atr": atr, "adx": adx, "rsi": rsi, "upper": mid+2*std, "lower": mid-2*std, "mid": mid,
                         "fast": close.rolling(5).mean(), "slow": close.rolling(20).mean(),
                         "entry_hi": high.shift(1).rolling(20).max(), "entry_lo": low.shift(1).rolling(20).min(),
                         "exit_hi": high.shift(1).rolling(10).max(), "exit_lo": low.shift(1).rolling(10).min()})


def run(df, start, adx_threshold=25, cash=1_000_000, multiplier=10, fee=0.0001, slip=1):
    ind = indicators(df); pos=0; entry=0.; entry_cost=0.; trades=[]; peak=cash; mdd=0.
    for i in range(60, len(df)):
        b, prior, s = df.iloc[i], df.iloc[i-1], ind.iloc[i-1]  # 前一日信号，当日开盘成交
        if s.isna().any(): continue
        price=b.open; mode="trend" if s.adx>adx_threshold else "range"; desired=pos
        if pos==0:
            qty=min(4, int(cash*(.01 if mode=="trend" else .005)/(s.atr*multiplier)))
            if qty and mode=="trend" and s.fast>s.slow and prior.close>s.entry_hi: desired=qty
            elif qty and mode=="trend" and s.fast<s.slow and prior.close<s.entry_lo: desired=-qty
            elif qty and mode=="range" and s.rsi<30 and prior.close<=s.lower*1.01: desired=qty
            elif qty and mode=="range" and s.rsi>70 and prior.close>=s.upper*.99: desired=-qty
        elif mode=="trend":
            if (pos>0 and prior.close<s.exit_lo) or (pos<0 and prior.close>s.exit_hi): desired=0
        else:
            if (pos>0 and (prior.close>=s.mid or s.rsi>=50)) or (pos<0 and (prior.close<=s.mid or s.rsi<=50)): desired=0
        if desired!=pos:
            fill=price + (1 if desired>pos else -1)*slip
            cost=abs(fill*(desired-pos)*multiplier)*fee
            if pos==0:
                pos, entry, entry_cost = desired, fill, cost; cash-=cost
            elif desired==0:
                gross=(fill-entry)*pos*multiplier; cash+=gross-cost
                trades.append({"entry":str(df.iloc[i-1].timestamp),"exit":str(b.timestamp),"side":"long" if pos>0 else "short","net_pnl":gross-entry_cost-cost})
                pos=0
        equity=cash+((b.close-entry)*pos*multiplier if pos else 0); peak=max(peak,equity); mdd=max(mdd,(peak-equity)/peak)
    return {"period":start,"ending_equity":cash+((df.iloc[-1].close-entry)*pos*multiplier if pos else 0),"max_drawdown":mdd,"closed_trades":len(trades),"trades":trades}


def main():
    p=argparse.ArgumentParser(); p.add_argument("--csv",type=Path,required=True); p.add_argument("--output",type=Path,required=True); p.add_argument("--adx-threshold",type=float,default=25); a=p.parse_args()
    df=pd.read_csv(a.csv); df["timestamp"]=pd.to_datetime(df.timestamp); df=df.sort_values("timestamp").reset_index(drop=True)
    split=pd.Timestamp("2023-01-01"); train=run(df[df.timestamp<split].reset_index(drop=True),"train: 2015-2022",a.adx_threshold); test=run(df[df.timestamp>=split].reset_index(drop=True),"test: 2023-2026",a.adx_threshold)
    for x in (train,test): x["return"]=x["ending_equity"]/1_000_000-1
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps({"research_only":True,"strategy":"desktop adaptive_strategy migration","adx_threshold":a.adx_threshold,"train":train,"test":test},ensure_ascii=False,indent=2),encoding="utf-8")
    for n,x in (("训练",train),("样本外",test)): print(f"{n}: 收益 {x['return']:.2%} | 回撤 {x['max_drawdown']:.2%} | 平仓 {x['closed_trades']}")

if __name__=="__main__": main()
