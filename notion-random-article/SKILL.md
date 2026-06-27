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

## 执行步骤

### Step 1 — 拉取全部文章，随机选一篇

调用一次 API 获取数据库全部文章，在本地解析标签分布、随机选标签、再从该标签下随机挑一篇（不选第一条）。无需第二次 API 调用。

**两步法**（避免 BusyBox ash 管道吞 stdin 的 bug）：

```bash
# 1. 存文件
notion-cli search \
  --database "a60f4ca1-08a3-4d31-8a14-365ef59e4c71" \
  --page-size 100 2>/dev/null > /tmp/articles.json

# 2. 用独立脚本处理（与 SKILL.md 同级）
python3 ./pick_random.py < /tmp/articles.json
```

> `./pick_random.py` 是相对于本 skill 目录的路径。代理执行前应将工作目录设为该 skill 目录，或根据 skill name 解析完整路径。
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

---

## 反例（不要做的事）

- ❌ **不要重复推荐**——同一篇文章 24 小时内不应再次推荐，记录 page ID
- ❌ **不要只选第一条搜索结果**——永远从第 2 条以后选（除非只有 1 条结果）
- ❌ **不要随意扩展用户的关键词**——用户说"哲学"，只用"哲学"搜索，不要变成"哲学思想"等变体
