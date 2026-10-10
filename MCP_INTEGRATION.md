# MCP 集成说明

本文件说明 `mc-use-it-or-lose-it` 实际调用的麦当劳 MCP Server、Tool、调用流程与业务价值。

## MCP Server

| 项 | 值 |
|---|---|
| 名称 | `mcd-mcp` |
| 协议 | Streamable HTTP |
| 地址 | `https://mcp.mcd.cn` |
| 鉴权 | `Authorization: Bearer <MCD_MCP_TOKEN>` |
| Token 申请 | <https://open.mcd.cn/mcp> → 登录 → 控制台 → 激活 |

## 调用的 Tool 清单

### 只读类（可自由调用）

| Tool | 在本项目中的作用 | 取用字段 |
|---|---|---|
| `now-time-info` | 取服务器当前时间，作为商品时效过滤的基准 | `data.formatted` |
| `query-my-account` | 积分账户核心数据 | `availablePoint`、`currentMouthExpirePoint`、`nextMouthExpirePoint`、`expiredPoint`、`lastMouthExpirePoint`、`frozenPoint` |
| `query-lottery-info` | 当期抽奖活动、单次消耗、奖品池 | `activityName`、`activityStatusText`、`endTime`、`drawTypeText`、`drawDecision`、`prizes[]` |
| `mall-points-products` | 可兑换商品清单 | `spuId`、`spuName`、`point`、`upTime`、`downTime`、`status`、`catName` |
| `mall-product-detail` | 取 SKU 列表 | `skuId`、`spuCategory` |
| `query-my-prizes` | 抽奖后续：查看已中奖品与有效期 | `prizes[]`、`statusText`、`timeRemindText` |

### 写入类（需用户明确确认后调用）

| Tool | 触发条件 | 关键约束 |
|---|---|---|
| `draw-lottery` | 用户确认用积分抽奖止损 | 必须先展示 `drawDecision.nextConsumption` 并获明确确认 |
| `mall-create-order` | 用户确认兑换商品 | 必须先取 `skuId` |

## 调用流程

```
                    ┌──────────────────────┐
                    │  now-time-info       │  当前时间基准
                    └──────────┬───────────┘
┌──────────────────┐           │           ┌──────────────────────┐
│ query-my-account │───────────┼───────────│ query-lottery-info   │
│ 积分 / 过期口径   │           │           │ 抽奖消耗 / 奖品池     │
└──────────────────┘           │           └──────────────────────┘
                    ┌──────────┴───────────┐
                    │ mall-points-products │  可兑换商品
                    └──────────┬───────────┘
                               ▼
                 ┌──────────────────────────────┐
                 │ points_planner.py            │
                 │ 过滤在售 → 计算最小消耗方案   │
                 └──────────────┬───────────────┘
                                ▼
                 ┌──────────────────────────────┐
                 │ 用户选择：抽奖 / 兑换 / 不动    │
                 └───────┬──────────────┬───────┘
                         ▼              ▼
              mall-product-detail   draw-lottery
                         ▼
                mall-create-order
```

**四个只读工具并行调用**，一次拉齐全部输入，避免串行等待。

## 业务价值

### 1. 把"过期"从被动损失变成可操作事项

`query-my-account` 已经直接返回 `currentMouthExpirePoint`，但原始字段名对普通用户没有意义。本项目把它转成一句可执行结论：**这个月有 9.9 分要过期，抽 1 次奖（24 分）即可止损**。

### 2. 修正商品列表的时效陷阱

`mall-points-products` 返回的 `status` 字段存在滞后——`downTime` 已过期的商品仍会返回 `status: 2`（上架）。

真实样例中，16 个返回商品里有 **7 个实际已过兑换截止时间**。若直接照搬原始列表，用户会看到大量根本无法兑换的商品，体验极差。

本项目的处理：以 `upTime` / `downTime` 与 `now-time-info` 的服务器时间比较作为主判据，`status` 仅作辅助，自动剔除失效商品并告知剔除数量。

### 3. 给出"最小消耗"而非"最划算"

判定基础是麦当劳[《会员服务协议》](https://www.mcdonalds.com.cn/page/member-service-agreement)规定的**积分有效期**规则：当月（第 n 月）内获得的积分，有效期截止至获得积分当月起的第 n+12 月的最后一天的 24 点，到期未用即自动失效扣除、不累计到次月。因此只要本期消耗总额 ≥ 本月将过期积分，过期风险即清零。

由此可以把问题化归为两个简单方案，而不是复杂的组合优化：

- **抽奖方案**：抽奖次数 = ⌈本月将过期积分 ÷ 单次消耗⌉
- **兑换方案**：在售商品中，选 `point ≥ 本月将过期积分` 且可负担的最小积分商品

工具在这两个方案里挑消耗更小的那个，而不是挑更贵的商品。

## 真实性说明

本项目**真实调用**上述麦当劳 MCP 工具，无任何 mock 或伪造数据。仓库中 `examples/sample-input.json` 为真实接口返回的脱敏片段（已移除账户 ID、Trace ID 等标识信息），用于离线验证计算脚本。
