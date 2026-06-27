---
name: notion-random-article
description: 从 Notion 文章收藏随机推荐一篇，输出摘要+链接。触发：随机推荐/给我一篇收藏/random article
---

# 文章收藏随机推荐

**DB**: `a60f4ca1-08a3-4d31-8a14-365ef59e4c71` · `$NOTION_TOKEN` · `notion-cli search`
**依赖**: `./pick_random.py`（与 SKILL.md 同目录），执行前 `which notion-cli && test -f ./pick_random.py`

---

## 执行

### Step 1 — 拉取 + 随机选

```bash
notion-cli search --database "a60f4ca1-08a3-4d31-8a14-365ef59e4c71" --page-size 100 2>/dev/null > /tmp/articles.json
python3 ./pick_random.py < /tmp/articles.json
```

输出行：`ID:` `URL:` `TITLE:` `NOTES_B64:`（base64 编码，解码：`base64 -d`）`ORIG:` `SOURCE:` `TIME:`。`TAGS:` 行可看标签分布。

用户指定主题（如"哲学"）→ 过滤 tags，跳过随机选标签。

### Step 2 — 输出

```
📖 **今日随机推荐** [**{TITLE}**]({URL})

🏷️**标签** {tags} 

📚**来源** {SOURCE} 

📅**收藏时间** {TIME}

📝**摘要** {NOTES_B64 解码内容；为空则省略}

🔗 [阅读原文]({ORIG})
```

NOTES_B64 为空 → 不显示摘要，**不 fetch 正文**。

---

## 异常

| 场景 | 处理 |
|------|------|
| `search` 401 | 提示 NOTION_TOKEN 失效，中止 |
| `search` 超时 | 5s 重试 1 次，仍失败则中止 |
| total=0 | 提示数据库为空，中止 |
| 用户不喜欢 | 回 Step 1 |

## 反例

- ❌ 24h 内不重复推荐（记录 page ID）
- ❌ 不选第一条（除非仅 1 篇）
- ❌ 不扩展用户关键词
