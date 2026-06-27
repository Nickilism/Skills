---
name: notion-random-article
description: 从 Nickilism 的 Notion "文章收藏" 数据库中随机推荐一篇值得重读的文章，返回摘要与链接。当用户说"随机推荐一篇文章"、"给我一篇收藏文章看看"、"我想读篇文章"、"从文章收藏里选一篇"、"推荐一篇我收藏过的"、"random article"、"文章收藏推荐"时，必须触发本 Skill。
---

# 文章收藏随机推荐

从 Notion **🗂️ 文章收藏** 数据库中随机推荐一篇文章，输出摘要 + 双链接（Notion + 原文）。

## 数据库信息

- **Database URL**: `https://app.notion.com/p/a60f4ca108a34d318a14365ef59e4c71`
- **Database ID**: `a60f4ca1-08a3-4d31-8a14-365ef59e4c71`
- **CLI 工具**: `notion-cli search`（无需 MCP，通过 REST API 直连）
- **环境变量**: `NOTION_TOKEN`（已设置且有效）

数据库字段（CLI 输出中的 key 名）：
| 字段 | CLI key | 说明 |
|------|---------|------|
| `Name` | `title` | 文章标题 |
| `userDefined:Url` | `original_url` | 原文链接 |
| `Fleeting Notes` | `fleeting_notes` | 用户读后笔记（优先作为摘要） |
| `Tags` | `tags` | 主题标签（数组） |
| `Source` | `source` | 来源 |
| `Created Time` | `created_time` | 收藏时间（ISO-8601） |
| 正文 | `body_text` | 页面正文内容 |

---

<!-- 前置依赖检查已移除：当前流程仅需 `notion-cli search`，不依赖 `notion-fetch.py`。保留 `notion-fetch.py` 文件供将来需要 fetch 时使用。 -->


---

## 执行步骤

### Step 1 — 拉取全部文章，随机选一篇

调用一次 API 获取数据库全部文章，在本地解析标签分布、随机选标签、再从该标签下随机挑一篇（不选第一条）。无需第二次 API 调用。

```bash
notion-cli search \
  --database "a60f4ca1-08a3-4d31-8a14-365ef59e4c71" \
  --page-size 100 2>/dev/null \
  | python3 -c "
import json, sys, random

d = json.load(sys.stdin)
results = d['results']

# 按标签建立索引
tag_map = {}
for r in results:
    for t in r.get('tags', []):
        tag_map.setdefault(t, []).append(r)

# 随机选一个标签
tags = sorted(tag_map.keys())
chosen = random.choice(tags)
articles = tag_map[chosen]

# 随机选一篇文章（跳过第一条）
if len(articles) == 1:
    pick = articles[0]
else:
    pick = random.choice(articles[1:])

# 输出结构化结果（供后续步骤解析，NOTES 用 base64 编码避免换行符截断）
import base64
notes = pick.get("fleeting_notes", "") or ""
notes_b64 = base64.b64encode(notes.encode()).decode()
print(f'TOTAL:{d[\"total\"]}')
print(f'TAGS:{json.dumps(tags, ensure_ascii=False)}')
print(f'CHOSEN_TAG:{chosen}')
print(f'ID:{pick[\"id\"]}')
print(f'URL:{pick["url"]}')
print(f'TITLE:{pick["title"]}')
print(f'NOTES_B64:{notes_b64}')
print(f'ORIG:{pick.get("original_url", "") or ""}')
print(f'SOURCE:{pick.get("source", "") or ""}')
print(f'TIME:{pick.get("created_time", "") or ""}')
"
```

解析输出中的 `ID:`、`URL:`、`TITLE:`、`NOTES_B64:` 等行。`NOTES_B64` 是 base64 编码，用 `echo "$NOTES_B64" | base64 -d` 解码得到完整原文。

> 💡 如果用户指定了主题（如"给我一篇哲学相关的"），用该词作为标签直接过滤 `tag_map`，跳过随机选标签。

### Step 2 — 生成输出

从 Step 1 的解析结果中提取字段：

- 如果 `NOTES_B64` 解码后不为空 → 直接用作摘要（原汁原味，这是你自己的笔记）
- 如果 `NOTES_B64` 为空 → 不显示摘要，**跳过 fetch，不拉正文**（节省 API 调用和 token 消耗）

然后按下方输出格式拼接文案。

---

## 输出格式

每块各占一行，用 emoji 标注：

```
📖 **今日随机推荐**

[**文章标题**](Notion页面URL)

🏷️ 标签：标签1, 标签2

📖 来源：xxx

📅 收藏于 YYYY年MM月DD日

📝 摘要：摘要内容

🔗 [阅读原文](original_url)
```

**排版规则：**
- 第一行 → `📖 **今日随机推荐**`
- 第二行 → 标题：`[**标题**](Notion页面URL)`
- 之后逐行列出元信息（缺则跳过）：
  - `🏷️ 标签：xxx`
  - `📖 来源：xxx`
  - `📅 收藏于 YYYY年MM月DD日`
  - `📝 摘要：xxx`（取自 `fleeting_notes`；若无则跳过此行，不拉正文）
- 最后一行 → `🔗 [阅读原文](original_url)`（若无原文链接则省略）

注意：标题已含 Notion 链接，底部不再重复。保持简洁，不要多余解释或客套话。

---

## 异常处理

所有 `notion-cli` 命令可能因环境问题失败：

| 场景 | 一线修复 | 仍失败兜底 |
|------|---------|-----------|
| `search` 返回 401 | 检查 `$NOTION_TOKEN` 是否有效 | 输出"NOTION_TOKEN 失效，请在 Settings → Environments 重新设置"，中止 |
| `search` 超时 | 等待 5 秒重试 1 次 | 输出"Notion API 暂时不可用"，中止 |
| Step 1 拉取 `total=0` | 检查 Notion 数据库是否为空 | 输出"文章收藏数据库为空"，中止 |
| `fleeting_notes` 为空 | 跳过摘要行，正常输出其他字段 | — |
| 用户不喜欢推荐的文章 | 回 Step 1 重新选一篇 | — |

### 🔴 CHECKPOINT · 输出前

生成推荐文案后暂停，确认：
1. 文章与用户兴趣相关？
2. 摘要来自自己的笔记（`fleeting_notes`）而非 AI 概括？
3. 双链接（Notion + 原文）可用？

> 全部通过 → 输出。第 1 条不通过 → 回 Step 1 重选。第 2/3 条不通过 → 仅输出已有字段。

---

## 反例（不要做的事）

- ❌ **不要重复推荐**——同一篇文章 24 小时内不应再次推荐，记录 page ID
- ❌ **不要只选第一条搜索结果**——永远从第 2 条以后选（除非只有 1 条结果）
- ❌ **不要随意扩展用户的关键词**——用户说"哲学"，只用"哲学"搜索，不要变成"哲学思想"等变体
