---
name: weread-anki
description: 微信读书划线转 Anki 卡片。当用户说"把划线做成Anki卡片"、"微信读书笔记转Anki"、"导出Anki"、"帮我制卡"、"划线复习卡片"时触发。支持两种输入：自动拉取微信读书划线（需 WEREAD_API_KEY），或用户手动粘贴划线文本。
---

# WeRead → Anki 卡片生成器

将微信读书划线内容转为 Anki 可导入的 pipe 分隔 CSV 文件。

## 前置条件

- 自动拉取模式：需设置 `WEREAD_API_KEY` 环境变量。未设置时提示用户 [设置环境变量](minis://settings/environments?create_key=WEREAD_API_KEY&create_value=&create_note=微信读书%20API%20Key%2C%20格式%20wrk-xxxxxxxx)
- 本 skill 依赖 `weread` skill 的 API 能力和 `notes.md` 文档（`/var/minis/skills/weread/notes.md`）

| 条件 | 状态 | 处理 |
|------|------|------|
| `WEREAD_API_KEY` 未设置 | 退化 | 自动切换手动模式，提示用户粘贴划线文本 |
| `/var/minis/skills/weread/notes.md` 不存在 | 降级 | Step 2A 使用本文档中的 curl 命令（已内联） |
| `minis-model-use` 不可用 | 中止 | 告知用户无法调用模型制卡，建议手动编辑 |

## 工作流

### Step 1：确定输入来源

检测 `WEREAD_API_KEY` 是否可用：
- **已设置**：询问用户书名，走 API 自动拉取模式
- **未设置**：请用户粘贴划线原始文本，走手动模式

**🔴 CHECKPOINT · 确认模式后继续。**

### Step 2A：API 模式 — 拉取划线

参考 `/var/minis/skills/weread/notes.md` 中的接口规范。若该文件不存在，使用以下内联命令。

**重要**：用户导入的书 bookId 带 `CB_` 前缀，`/store/search` 可能搜不到或返回商店版。必须优先从 `/user/notebooks` 匹配书名。

1. 获取用户笔记本列表，按书名匹配（优先用脚本）：

```bash
python3 /var/minis/skills/weread-anki/weread_anki.py search-notebooks "书名关键词"
```

若脚本不可用，手动请求：
```bash
curl -s -X POST "https://i.weread.qq.com/api/agent/gateway" \
  -H "Authorization: Bearer $WEREAD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"api_name":"/user/notebooks","count":200,"skill_version":"1.0.3"}'
```
在返回的 `books` 数组中按书名关键词匹配。如有翻页（`hasMore=1`），用最后一条的 `sort` 继续请求。

**🔴 CHECKPOINT · 展示匹配结果，让用户确认是哪本书。**

如果 notebook 列表中未找到，再 fallback 到 `/store/search`：
```bash
curl -s -X POST "https://i.weread.qq.com/api/agent/gateway" \
  -H "Authorization: Bearer $WEREAD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"api_name":"/store/search","keyword":"书名","count":5,"skill_version":"1.0.3"}'
```
**🔴 CHECKPOINT · 让用户确认搜索结果中的书。若仍未找到 → 切换手动模式（Step 2B）。**

2. 拉取划线和想法（优先用脚本）：

```bash
python3 /var/minis/skills/weread-anki/weread_anki.py fetch <bookId>
# 输出 JSON 元信息 + 保存划线到 /tmp/weread_lines.txt
```

若脚本不可用，手动请求：
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

| 触发条件 | 一线修复 | 仍失败兜底 |
|----------|----------|------------|
| API 返回错误码或超时 | 重试 1 次（间隔 3 秒） | 告知用户 API 暂不可用，切换手动模式 |
| `updated` 数组为空（无划线） | 检查 bookId 是否正确，确认用户是否真的有划线 | 告知用户该书无划线数据，建议手动粘贴 |
| `chapters` 数组为空 | 章节名留空，只用划线原文 | 正常继续，标签用书名代替 `书名::章节名` |
| store search 也搜不到（CB_ 书） | 让用户提供 bookId 或手动粘贴 | 切换手动模式 |

**🔴 CHECKPOINT · 展示提取到的划线条数和前 3 条预览，让用户确认内容正确。**

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

| 触发条件 | 一线修复 | 仍失败兜底 |
|----------|----------|------------|
| 粘贴文本中无 ◆ 标记 | 尝试按空行分段，每段作为一条摘录 | 告知用户格式无法识别，请重新粘贴或手动整理 |
| 解析后 0 条摘录 | 检查编码问题（如全角/半角 ◆） | 告知用户解析失败 |

**🔴 CHECKPOINT · 展示解析结果条数和前 3 条预览，让用户确认。**

### Step 3：分批

将所有摘录按顺序分成每批最多 40 条。记录总批次数。

如果提取到 0 条摘录 → **🛑 STOP：告知用户没有可制卡的内容，终止流程。**

### Step 4：逐批生成卡片

对每一批：

1. 读取制卡规则：`file_read` `/var/minis/skills/weread-anki/card-rules.md`
2. 构造输入 JSON，调用 `minis-model-use` 生成卡片：

```bash
minis-model-use run --model <模型名> --input /tmp/anki_batch_N.json
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
      "content": "请为以下划线内容生成 Anki 卡片：\n\n书名：XXX\n作者：YYY\n书籍链接：<链接>\n\n以下是划线摘录：\n\n◆ [章节A] 划线内容...\n◆ [章节B] 划线内容..."
    }
  ]
}
```

3. 解析模型输出为 CSV 行：
   - 模型应返回每行格式：`问题|回答|作者|书名|微信读书链接|原文摘录|书名::章节名`
   - **解析策略**：按行分割输出 → 每行按 `|` 分割为 7 个字段 → 检查字段数是否为 7
   - 若字段数不对：尝试智能修复（合并多余 `|` 到第 6 字段"原文摘录"中），修复失败则丢弃该行并记录警告
   - 字段中的 `|` 转义为 `\|`，换行替换为空格
   - 跳过空行和明显非卡片行（如模型的开头说明文字）

4. 将每批结果写入 `/tmp/anki_batch_N.csv`

| 触发条件 | 一线修复 | 仍失败兜底 |
|----------|----------|------------|
| `minis-model-use` 调用失败/超时 | 重试 1 次 | 跳过该批次，记录到警告列表，继续下一批 |
| 模型输出非 CSV 格式（如返回 Markdown/解释文字） | 用正则提取 pipe 分隔行，忽略其他内容 | 丢弃该批次，告知用户该批制卡失败 |
| 某批次所有行解析失败 | 降低 batch_size 到 20 重试 | 告知用户该批制卡失败，请手动处理 |

### Step 5：合并与输出

1. 用 shell 合并所有批次 CSV（跳过空行），文件名带时间戳：
```bash
python3 /var/minis/skills/weread-anki/weread_anki.py merge 书名slug
# 输出：/var/minis/attachments/anki/书名slug_20260621_1430.csv
```

2. 统计总卡片数（行数）

3. 输出：
   - 告知用户生成了多少张卡片
   - 若有警告（失败批次），一并列出
   - 提供 CSV 下载链接：`[书名_时间.csv](minis://attachments/anki/书名_时间.csv)`
   - 提供 Anki 导入说明：文件 → 导入 → 选择文件 → 分隔符选自定义 "|"

| 触发条件 | 一线修复 | 仍失败兜底 |
|----------|----------|------------|
| 合并后 CSV 为空（0 行） | 检查 /tmp/anki_batches/ 下是否有文件 | 告知用户全部批次制卡失败，建议检查划线内容或换模型重试 |
| 输出目录不可写 | 使用 /tmp/anki/ 替代 | 告知用户文件保存失败 |

### 模型选择

- **默认**：使用当前对话模型（主模型）
- **用户指定**：运行 `minis-model-use list` 查看可用模型，让用户选择
- **选择策略**：制卡任务需要强指令遵从 + 结构化输出能力。优先选择 claude-sonnet-4-20250514 或同级模型；若可用模型仅有推理型（如 o1/o3），也可使用但可能速度较慢

## 反例与黑名单

以下行为会降低卡片质量或破坏输出格式，**必须避免**：

| # | 不要做 | 为什么 | 应该做 |
|---|--------|--------|--------|
| 1 | 合并多条摘录制一张卡 | 违反最小信息原则，卡片过于宽泛无法有效回忆 | 每条 ◆ 摘录独立制卡 |
| 2 | 修改摘录原文内容 | 摘录是学习素材，改动后失去溯源价值 | 原文摘录字段必须完整保留原始文本 |
| 3 | 在答案中加注释性副语言 | 如"值得注意的是""我们知道"等，增加认知噪音 | 答案只包含核心知识，去掉引导性废话 |
| 4 | 生成表头行 | Anki 导入时表头会被当成一张卡片 | 输出不含表头，直接是数据行 |
| 5 | 用 Markdown 格式输出卡片 | 模型返回 ```csv 代码块会破坏解析 | 严格按 pipe 分隔纯文本输出，无代码块包裹 |
| 6 | 对短摘录（<10 字）强行制卡 | 碎片内容无法构成有效卡片 | 跳过并告知用户 |
| 7 | 在标签字段使用空格 | Anki 标签中空格会分割标签 | 用 `::` 分隔层级，不用空格 |

## 注意事项

- 每条 ◆ 摘录必须被遍历，不得遗漏（制卡完成后核对：生成卡片数 ≥ 摘录条数）
- 如果某条摘录内容过短（少于 10 字）或纯属标记/页码，可跳过并告知用户
- 生成过程中显示进度（"正在处理第 2/5 批..."）
- CSV 中所有字段的 `|` 必须转义为 `\|`
- 每批之间无需表头，直接拼接即可
