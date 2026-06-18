# 投资策略准则扩展笔记

本项目的目标不是预测市场，也不是提供保证收益的公式。更稳妥的目标是：

- 用规则减少情绪化决策
- 用历史数据验证规则是否改善风险调整后收益
- 用可解释信号说明每一次建议来自哪条准则
- 用风控约束避免单一错误毁掉组合

## 当前应纳入系统的核心准则

### 1. 长期趋势过滤

公式：

```text
trend_state = bullish if close > SMA(close, 200) else bearish
```

用途：

- 牛市或上升趋势：允许持有或按规则加仓
- 熊市或下行趋势：阻止逆势加仓，考虑降低风险敞口、提高现金

依据：

- Lance Roberts / RIA 强调长期趋势和风险管理
- Meb Faber 的 tactical allocation 研究支持简单趋势过滤
- AQR trend-following 研究显示跨资产、长历史趋势信号有解释力

### 2. 标准差 / Z-score 极端区间

公式：

```text
z = (price - rolling_mean(price, window)) / rolling_std(price, window)
```

用途：

- z-score 过高：过热/拥挤，优先检查 trim
- z-score 过低：可能便宜，但必须结合趋势、动量、风险规则

重点：

这不是独立买卖信号，而是“是否过度偏离”的证据。

### 3. 阈值再平衡

公式：

```text
drift = current_weight - target_weight
rebalance if abs(drift) > threshold
```

用途：

- 不因小波动频繁交易
- 超配时修剪，低配时按规则补足
- 让组合风险回到原计划

### 4. 单一持仓与行业上限

公式：

```text
position_weight <= max_single_position_weight
sector_weight <= max_sector_weight
```

用途：

- 防止赢家变成隐形杠杆
- 防止多个股票表面分散、实际都押注同一行业

### 5. 禁止自动摊低成本

公式：

```text
block_add if latest_price / entry_price - 1 <= -loss_block_pct
```

用途：

- 防止“我只是更有信念了”变成亏损加码
- 只有在有明确 thesis reset 时才允许例外

### 6. 止损与 trailing stop

公式：

```text
drawdown_from_entry = latest_price / entry_price - 1
drawdown_from_peak = latest_price / trailing_high - 1
```

用途：

- 控制深度亏损
- 防止大幅盈利回吐
- 用 partial trim，而不是情绪化清仓

### 7. 动量确认

公式：

```text
momentum = price[today] / price[today - lookback] - 1
```

用途：

- 优先加到绝对动量为正、相对强度靠前的资产
- 避免因为“便宜”买入持续下跌资产

依据：

- Jegadeesh & Titman 的 momentum 研究
- AQR 的 value + momentum 组合研究

### 8. 估值意识

公式方向：

```text
valuation_percentile = percentile(CAPE or valuation proxy over long history)
```

用途：

- 高估值不是马上卖出理由
- 高估值 + 趋势变差 + 动量变差 = 降低激进程度

### 9. 波动率目标 / 风险预算

公式：

```text
scale = target_volatility / realized_volatility
```

用途：

- 市场波动率升高时减少风险敞口
- 让组合风险更稳定

### 10. ML 风险覆盖层

公式方向：

```text
p(drawdown_event) = sigmoid(beta * rolling_price_features)
```

用途：

- 估计未来一个 horizon 内发生显著回撤的概率
- 高风险时阻止加仓或建议 trim
- 必须保持可解释，不能替代规则系统

## 项目实现方向

已实现：

- 200日趋势过滤
- Z-score sector signals
- 持仓/行业上限
- 阈值再平衡
- 禁止自动摊低
- stop-loss / trailing stop
- 现金缓冲
- 轻量 ML drawdown risk
- 规则目录 `/api/rules`
- K线 OHLC 接口 `/api/ohlc`

下一步：

- 真正的多策略 comparison harness
- CAPE / valuation data ingestion
- 12-1 momentum strategy
- volatility targeting strategy
- rolling walk-forward test
- 2000, 2008, 2020, 2022 压力期专项回测

## 参考来源

- Meb Faber, A Quantitative Approach to Tactical Asset Allocation: https://mebfaber.com/wp-content/uploads/2016/05/SSRN-id962461.pdf
- AQR, A Century of Evidence on Trend-Following Investing: https://www.aqr.com/Insights/Research/Journal-Article/A-Century-of-Evidence-on-Trend-Following-Investing
- Vanguard, Rebalancing your portfolio: https://investor.vanguard.com/investor-resources-education/portfolio-management/rebalancing-your-portfolio
- Fidelity, Bollinger Bands guide: https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/bollinger-bands
- Jegadeesh & Titman momentum paper reference: https://econpapers.repec.org/RePEc%3Abla%3Ajfinan%3Av%3A48%3Ay%3A1993%3Ai%3A1%3Ap%3A65-91
- Shiller data: https://www.econ.yale.edu/~shiller/data.htm

