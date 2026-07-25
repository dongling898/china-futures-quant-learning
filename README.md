# 中国期货量化研究

这是一个**研究和回测优先**的中国期货量化项目骨架。它不连接期货账户，也不包含实盘下单功能。

## 已解决的基础问题

- 信号在当日收盘生成、下一根 K 线开盘成交，避免把尚未收盘的数据用于当日成交。
- 仓位按 ATR、合约乘数和单笔风险计算；资金不足一手时不交易，不会为了凑一手而突破风险预算。
- 手续费、滑点和多空方向均计入每笔交易及净值。
- 合约规格、交易成本和策略参数集中配置，避免把失效合约代码写死在策略中。
- 所有密钥、账户配置、回测结果及虚拟环境均被 Git 忽略。

## 快速开始

使用 Python 3.10–3.13：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
pip install -r requirements-research.txt
python -m futures_quant.backtest --csv data\your_verified_rb.csv --config config\rb.toml
```

`data/example_rb.csv` 仅是格式示例，不能用于任何结论。请替换为至少含 22 根 K 线、已核验且包含换月规则的连续合约数据。CSV 必须包含：`timestamp,open,high,low,close`。

## 包的角色

- **AKShare**：研究数据抓取与交易所公开数据补充。接口可能变化，下载后应固化原始数据与数据字典。
- **TqSdk**：行情、回测和模拟交易。只在独立的模拟环境中使用。
- **vn.py / VeighNa**：交易系统与网关集成；仅在独立验收后才考虑接入。

安装前先确认期货公司、交易所、合约规则及数据授权。策略历史表现不代表未来收益。

## 目录

```text
config/                  策略与合约参数（可提交的示例）
data/                    本地数据（不提交）
src/futures_quant/       无账户依赖的回测核心
tests/                   核心行为测试
```

## 从桌面旧代码迁移

桌面“交易策略与开发”中的 TqSdk 脚本可作为信号逻辑参考，但存在固定到期合约、状态文件依赖当前目录等问题。先在这里完成 CSV 回测、样本外测试、参数敏感性和模拟交易，再单独改写 TqSdk 适配层。

已完成的逐项审计见 [桌面策略迁移审计](docs/legacy-strategy-audit.md)。
