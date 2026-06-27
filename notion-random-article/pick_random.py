#!/usr/bin/env python3
"""
从 notion-cli search 输出的 JSON 文件中随机选一篇文章。
用法：python3 pick_random.py < articles.json
输出结构化结果行，供 agent 解析。
"""
import json, sys, random, base64

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

# 输出结构化结果（NOTES 用 base64 编码避免换行符截断）
notes = pick.get('fleeting_notes', '') or ''
notes_b64 = base64.b64encode(notes.encode()).decode()
print(f'TOTAL:{d["total"]}')
print(f'TAGS:{json.dumps(tags, ensure_ascii=False)}')
print(f'CHOSEN_TAG:{chosen}')
print(f'ID:{pick["id"]}')
print(f'URL:{pick["url"]}')
print(f'TITLE:{pick["title"]}')
print(f'NOTES_B64:{notes_b64}')
print(f'ORIG:{pick.get("original_url", "") or ""}')
print(f'SOURCE:{pick.get("source", "") or ""}')
print(f'TIME:{pick.get("created_time", "") or ""}')
