---
name: weread-anki
description: 微信读书划线转 Anki 卡片。当用户说"把划线做成Anki卡片"、"微信读书笔记转Anki"、"导出Anki"、"帮我制卡"、"划线复习卡片"时触发。支持两种输入：自动拉取微信读书划线（需 WEREAD_API_KEY），或用户手动粘贴划线文本。
version: 1.0.0
---

# WeRead → Anki 卡片生成器

将微信读书划线内容转为 Anki 可导入的 pipe 分隔 CSV 文件。

## 前置条件

- 自动拉取模式：需设置 `WEREAD_API_KEY` 环境变量。未设置时提示用户 [设置环境变量](minis://settings/environments?create_key=WEREAD_API_KEY&create_value=&create_note=微信读书%20API%20Key%2C%20格式%20wrk-xxxxxxxx)
- 本 skill 依赖 `weread` skill 的 API 能力和 `notes.md` 文档（`/var/minis/skills/weread/notes.md`）

## 工作流

### Step 1：确定输入来源

检测 `WEREAD_API_KEY` 是否可用：
- **已设置**：询问用户书名，走 API 自动拉取模式
- **未设置**：请用户粘贴划线原始文本，走手动模式

### Step 2A：API 模式 — 拉取划线

参考 `/var/minis/skills/weread/notes.md` 中的接口规范。

**重要**：用户导入的书 bookId 带 `CB_` 前缀，`/store/search` 可能搜不到或返回商店版。必须优先从 `/user/notebooks` 匹配书名。

1. 获取用户笔记本列表，按书名匹配：
```bash
curl -s -X POST "https://i.weread.qq.com/api/agent/gateway" \
  -H "Authorization: Bearer $WEREAD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"api_name":"/user/notebooks","count":200,"skill_version":"1.0.3"}'
```
在返回的 `books` 数组中按书名关键词匹配，让用户确认是哪本。如有翻页（`hasMore=1`），用最后一条的 `sort` 继续请求。

如果 notebook 列表中未找到，再 fallback 到 `/store/search`：
```bash
curl -s -X POST "https://i.weread.qq.com/api/agent/gateway" \
  -H "Authorization: Bearer $WEREAD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"api_name":"/store/search","keyword":"书名","count":5,"skill_version":"1.0.3"}'
```
让用户确认是哪本书。

2. 拉取划线（bookmarklist）和想法（review/list/mine）：
```bash
# 划线
curl -s -X POST "https://i.weread.qq.com/api/agent/gateway" \
  -H "Authorization: Bearer $WEREAD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"api_name":"/book/bookmarklist","bookId":"<bookId>","skill_version":"1.0.3"}'
# 想法
curl -s -X POST "https://i.weread.qq.com/api/agent/gateway" \
  -H "Authorization: Bearer $WEREAD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"api_name":"/review/list/mine","bookid":"<bookId>","count":100,"skill_version":"1.0.3"}'
```

3. 提取信息：
   - 从 `chapters` 数组构建 chapterUid → 章节名映射
   - 从 `updated` 数组提取每条划线的 `markText`，通过 `chapterUid` 关联章节
   - 合并想法/点评（`reviews[].review.content` + `reviews[].review.chapterName`）
   - 去重（同一 markText 可能出现在划线和想法中）

4. 格式化为制卡输入（每条一行）：
```
◆ [章节名] 划线原文内容
```
想法/点评格式：
```
◆ [章节名] 💭 想法内容（对应划线：划线原文前20字...）
```

5. 收集书籍元信息：书名、作者、bookId（用于构造 weread 链接）

### Step 2B：手动模式 — 解析粘贴文本

用户粘贴的微信读书笔记通常格式为：
```
章节名
◆ 划线内容1
◆ 划线内容2
...
```

解析逻辑：
- 识别章节标题行（非 ◆ 开头的行）
- 每段以 ◆ 开头的内容作为一条独立摘录
- 保留完整摘录，不做拆分
- 如果格式不清晰，直接按 ◆ 分割，章节信息留空

### Step 3：分批

将所有摘录按顺序分成每批最多 40 条。记录总批次数。

### Step 4：逐批生成卡片

对每一批：

1. 读取制卡规则：`file_read` `/var/minis/skills/weread-anki/card-rules.md`
2. 构造输入，调用 `minis-model-use` 生成卡片：

```
minis-model-use run --model <选择的模型> --input /tmp/anki_batch_N.json
```

输入 JSON 结构：
```json
{
  "messages": [
    {
      "role": "system",
      "content": "<card-rules.md 的完整内容>"
    },
    {
      "role": "user",
      "content": "请为以下划线内容生成 Anki 卡片：\n\n书名：XXX\n作者：YYY\n\n以下是划线摘录：\n\n◆ [章节A] 划线内容...\n◆ [章节B] 划线内容..."
    }
  ]
}
```

3. 模型返回的每行格式：`问题|回答|作者|书名|微信读书链接|原文摘录|书名::章节名`

4. 将每批结果写入 `/tmp/anki_batch_N.csv`

### Step 5：合并与输出

1. 用 shell 合并所有批次 CSV（跳过可能的空行），文件名带时间戳：
```bash
python3 /var/minis/skills/weread-anki/weread_anki.py merge 书名slug
# 输出：/var/minis/attachments/anki/书名slug_20260621_1430.csv
```

2. 统计总卡片数（行数）

3. 输出：
   - 告知用户生成了多少张卡片
   - 提供 CSV 下载链接：`[书名_时间.csv](minis://attachments/anki/书名_时间.csv)`
   - 提供 Anki 导入说明：文件 → 导入 → 选择文件 → 分隔符选自定义 "|"

### 模型选择

- 默认使用主模型（当前对话模型）
- 如果用户指定，使用 `minis-model-use list` 查看可用模型
- 推荐使用推理能力强的模型以保证卡片质量

## 注意事项

- 每条 ◆ 摘录必须被遍历，不得遗漏
- 如果某条摘录内容过短（少于 10 字）或纯属标记/页码，可跳过并告知用户
- 生成过程中显示进度（"正在处理第 2/5 批..."）
- CSV 中所有字段的 `|` 必须转义为 `\|`
