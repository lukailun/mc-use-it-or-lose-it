# WorkBuddy 开发对话上下文

本文件记录 `Mc-Use-It-or-Lose-It`（麦麦积分末班车）在腾讯 WorkBuddy 中的完整开发过程，用于核验本作品真实使用了 WorkBuddy 智能体完成创意构思、开发与调试。

- 开发工具：腾讯 WorkBuddy（Agent 模式）
- 开发日期：2026-10-10
- MCP 连接器：`mcd-mcp`（Streamable HTTP，`https://mcp.mcd.cn`）

---

## 1. 需求提出

**用户原始需求：**

> 我想开发一个积分相关的工具，可以查询积分，查看自己每月过期的积分以及当期积分抽奖的奖品和积分兑换的商品，用户可以选择进行抽奖或者兑换操作，以消耗掉本月过期的积分。

## 2. 能力探查（WorkBuddy 自主执行）

WorkBuddy 未直接开始写代码，而是先检索可用的麦当劳 MCP 工具，并实际调用只读接口验证数据可得性：

| 调用 | 目的 | 关键发现 |
|---|---|---|
| `query-my-account` | 确认过期积分口径 | 返回 `currentMouthExpirePoint` / `nextMouthExpirePoint` / `expiredPoint`，过期口径现成可用 |
| `query-lottery-info` | 确认抽奖消耗结构 | 返回 `drawDecision.nextConsumption`，可精确算出单次消耗 |
| `now-time-info` | 获取时间基准 | 服务器时间 `2026-10-10 11:12:21` |
| `mall-points-products` | 确认商品数据结构 | **发现 `status` 字段滞后：`downTime` 已过的商品仍返回 `status: 2`** |

这一发现直接改变了设计方向——原计划"直接展示商品列表"，改为"必须先做时效过滤"。

## 3. 设计决策

WorkBuddy 提出的关键设计判断：

1. **以"先进先出扣减"作为推理基础**
   麦当劳积分消耗时优先扣减最早到期部分，因此判定条件可简化为「本期消耗总额 ≥ 本月将过期积分」，无需精确匹配单笔积分。

2. **把问题化归为两个方案而不是组合优化**
   - 抽奖：次数 = ⌈过期积分 ÷ 单次消耗⌉
   - 兑换：选 `point ≥ 过期积分` 且可负担的最小积分商品
   在两方案中取消耗更小者。

3. **主动收紧产品取向**
   明确要求：本月无过期积分时必须回答"无需操作"；只推荐能覆盖过期积分的最小消耗；已过期积分标注为既成损失而非可挽回。

4. **抽奖与兑换走不同的确认链路**
   抽奖必须实时重取 `drawDecision` 并展示 `nextConsumption`；兑换必须先取 SKU 再下单，且禁止跳过 `mall-create-order` 直接输出"兑换成功"。

## 4. 开发与验证

WorkBuddy 在 Agent 模式下完成：

- 编写 `scripts/points_planner.py`（纯标准库，无第三方依赖）
- 用真实接口返回构造 `examples/sample-input.json`
- 跑通主流程，并验证 3 个边界场景：

| 场景 | 结果 |
|---|---|
| 本月无过期积分 | 正确输出"无需操作"，并提示下月过期额 |
| 可用积分不足以覆盖 | 正确输出缺口金额，建议攒分而非强行推荐 |
| 抽奖活动不存在 + 无商品 | 正确降级，不报错 |

主流程实测：16 个返回商品中，**7 个已过兑换截止时间被自动剔除**，剩余 9 个在售商品按积分升序输出，并给出"抽 1 次奖（24 分）即可覆盖 9.9 分过期额"的结论。

## 5. 产出物

```
Mc-Use-It-or-Lose-It/
├── SKILL.md                  # Skill 定义
├── README.md                 # 项目说明
├── MCP_INTEGRATION.md        # MCP 集成说明
├── CONTEST_DECLARATION.md    # 参赛声明（官方原文）
├── mcp-config.example.json   # 脱敏配置示例
├── workbuddy.md              # 本文件
├── references/decision-rules.md
├── scripts/points_planner.py
└── examples/sample-input.json
```

## 6. 说明

本项目全部麦当劳 MCP 调用均为真实调用，无 mock 或伪造数据。示例数据已脱敏，不含 Token、账户 ID 等敏感信息。
