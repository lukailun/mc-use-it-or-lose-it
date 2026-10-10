# 麦麦积分末班车 · mc-use-it-or-lose-it

> 麦当劳积分有固定有效期，到期未用即自动失效扣除。这个 Skill 只做一件事：**计算当月即将失效的积分，帮你进行抽奖或者兑换操作。**

麦当劳程序员创意开发大赛参赛作品，基于麦当劳 MCP 构建。

---

## 它解决什么问题

麦当劳[《会员服务协议》](https://www.mcdonalds.com.cn/page/member-service-agreement)中有积分有效期的说明：当月（第 n 月）内获得的积分的有效期截止至获得积分当月起的第 n+12 月的最后一天的 24 点。也就是说，每个月月末都有一批积分清零。但大部分用户根本不知道：

- 自己这个月有多少积分即将过期
- 需要积分抽奖多少次，可以消耗掉即将过期的积分
- 积分可以兑换哪些商品

等到发现时，积分已经过期。本 Skill 把「查询即将过期积分 → 计算消耗方式 → 确认执行」这条链路压缩成一次对话。

## 目标用户

- **高频麦当劳用户**：积分攒得多，即将过期的积分也多，手动抽奖需要大量操作
- **低频麦当劳用户**：积分零散，不清楚如何查看积分和抽奖，方便快速体验
- **想用积分换到实物周边的用户**：需要知道哪些商品当前真的在售

## 安装方法

### 1. 申请 MCP Token

访问 [麦当劳 MCP 平台](https://open.mcd.cn/mcp)，登录后在「控制台」激活并复制 MCP Token。

> 参见[麦当劳 MCP Server GitHub 使用指南](https://github.com/M-China/mcd-mcp-server)

### 2. 配置 MCP 连接

在 WorkBuddy 左侧边栏【专家·技能·连接器】→【连接器】→ 右上角【自定义连接器】→【配置 MCP】中，
填入 [`mcp-config.example.json`](mcp-config.example.json) 的内容，
并把 `${MCD_MCP_TOKEN}` 替换为你的真实 MCP Token，保存后【启用】。

### 3. 安装本 Skill

把 `skills/mc-use-it-or-lose-it/` 整个目录复制到 WorkBuddy 的用户技能目录：

```bash
cp -r skills/mc-use-it-or-lose-it ~/.workbuddy/skills/
```

（Windows 为 `%USERPROFILE%\.workbuddy\skills\`）

装好后在对话框里直接说「我这个月有多少积分要过期」即可触发。

## 使用示例

直接说需求即可，不需要记命令：

```
我这个月有多少积分要过期
帮我把快过期的积分花掉
积分抽奖现在有什么奖品
积分能兑换什么
```

### 实际运行结果

以下为真实账户的一次完整体检输出：

```
积分止损体检
  快照时间：2026-10-10 11:12:21
  可用积分 1572.5｜本月将过期 9.9｜下月将过期 0｜累计已过期 4944.3

抽奖方案：周六麦金喜抽奖（进行中）
  可行 → 抽 1 次，消耗 24 分，剩余 1548.5 分

兑换方案：当前在售 9 个商品
  [可兑] 6.9元可乐麦炫酷｜50 分｜截止 2026-12-30 23:59:59｜spuId=17073
  [可兑] 6.9元香芋派/菠萝派任选｜50 分｜截止 2026-12-30 23:59:59｜spuId=17074
  [可兑] 10.9元指定小食任选｜100 分｜截止 2026-12-30 23:59:59｜spuId=17076
  [可兑] 3.9元圆筒冰淇淋｜100 分｜截止 2026-12-30 23:59:59｜spuId=17075
  [可兑] 21.9元巨无霸可乐组合｜800 分｜截止 2026-12-30 23:59:59｜spuId=17081

建议：本月将过期 9.9 分，建议积分抽奖 × 1，消耗 24 分，剩余可用 1548.5 分。

提示：
  - 历史已过期积分 4944.3 分，本工具只能止损未来过期部分，已过期的无法找回。
  - 接口返回的 7 个商品已过兑换截止时间（status 仍显示上架），已自动剔除。
```

注意最后一行——**7 个商品被自动剔除**。这不是小事，是接口 `status` 字段滞后导致的真实陷阱，也是本工具和"直接照着原始列表念"的本质区别。

## 项目结构

```
mc-use-it-or-lose-it/
├── README.md                     # 本文件
├── MCP_INTEGRATION.md            # MCP 工具调用说明与业务价值
├── CONTEST_DECLARATION.md        # 参赛声明（官方原文，未改动）
├── mcp-config.example.json       # 脱敏配置示例
├── workbuddy.md                  # WorkBuddy 开发对话上下文
├── LICENSE                       # MIT
└── skills/
    └── mc-use-it-or-lose-it/     # Skill 本体（安装时复制此目录）
        ├── SKILL.md              # Skill 定义：工作流、决策规则、安全边界
        ├── references/
        │   └── decision-rules.md # 决策规则详解
        ├── scripts/
        │   └── points_planner.py # 止损方案计算（纯标准库，无依赖）
        └── examples/
            └── sample-input.json # 真实接口数据样例
```

## 计算脚本

无第三方依赖，Python 3.8+ 即可运行：

```bash
# 可读文本输出
python3 skills/mc-use-it-or-lose-it/scripts/points_planner.py \
  --input skills/mc-use-it-or-lose-it/examples/sample-input.json

# 机器可读
python3 skills/mc-use-it-or-lose-it/scripts/points_planner.py \
  --input skills/mc-use-it-or-lose-it/examples/sample-input.json --format json
```

脚本只做计算，**不发起任何网络请求、不执行任何消耗动作**。

## 设计取向

市面上的积分工具大多在做"帮你花更多钱"——推荐套餐、凑单满减。这个工具刻意反过来：

- 本月无过期积分时，直接告诉你**无需操作**，不制造焦虑
- 只推荐**能覆盖过期积分的最小消耗**，不推荐更贵的商品
- 已过期积分明确标注为**既成损失**，不假装能挽回

## 免责声明

本项目为麦当劳程序员节创意开发大赛参赛作品，由参赛者独立开发，非麦当劳官方产品。积分余额、商品信息、活动规则均以麦当劳官方渠道实时返回为准。

## 许可证

[MIT License](./LICENSE)
