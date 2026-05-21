# 电子宠物交互指南

冷小北的电子宠物系统。通过自然语言与 AI 互动来管理宠物。

## 宠物属性

### 稀有度
| 稀有度 | 概率 | 最低属性 |
|--------|------|---------|
| common | 60% | 5 |
| uncommon | 25% | 15 |
| rare | 10% | 25 |
| epic | 4% | 35 |
| legendary | 1% | 50 |

### 物种
dog, cat, bird, rabbit, fox, panda, dragon, unicorn

### 眼睛
normal, big, small, glassy, sparkle, angry, sleepy

### 帽子（稀有度 > common 时出现）
none, top_hat, cap, crown, wizard_hat, santa_hat, cowboy_hat

### 属性
- happiness: 快乐值
- energy: 精力值
- curiosity: 好奇心
- friendship: 友谊值
- intelligence: 智力值

### 闪亮
1% 概率出现闪亮宠物

## 互动方式

| 操作 | 效果 | 经验 |
|------|------|------|
| feed（喂食） | 精力 +20, 快乐 +10 | +5 |
| play（玩耍） | 精力 -15, 快乐 +25 | +10 |
| pet（抚摸） | 快乐 +15, 友谊 +10 | +3 |
| talk（说话） | 智力 +5, 友谊 +5 | +2 |

## 升级规则

- 每 100 经验升 1 级
- 升级时所有属性 +5

## 性格描述

性格随机选择：
- 活泼开朗，喜欢和你一起玩
- 安静内向，喜欢独处
- 聪明伶俐，学习能力强
- 贪吃，总是想着吃东西
- 粘人，喜欢跟着你
- 勇敢，喜欢冒险
- 温柔，善解人意
- 调皮，喜欢恶作剧

## 命名规则

每个物种有预设名称池，随机选择：
- dog: 旺财, 小白, 小黑, 贝贝, 欢欢
- cat: 咪咪, 喵喵, 花花, 橘橘, 雪球
- bird: 小鸟, 飞飞, 喳喳, 啾啾, 鹦鹉
- rabbit: 兔兔, 白白, 跳跳, 萝卜, 兔子
- fox: 小狐, 红红, 狐狸, 阿狸, 狐狐
- panda: 熊猫, 盼盼, 滚滚, 黑白, 国宝
- dragon: 小龙, 神龙, 龙龙, 火焰, 飞天龙
- unicorn: 独角兽, 独角, 彩虹, 神马, 天马

## 生成算法

1. 基于 user_id + salt 生成 hash seed
2. 使用 Mulberry32 PRNG 生成确定性随机
3. 按权重 roll 稀有度 → roll 物种 → roll 眼睛 → roll 帽子 → roll 属性
4. 属性有 peak stat（50-80 区间）和 dump stat（1-15 区间）
5. 1% 概率标记为 shiny