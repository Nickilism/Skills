#!/usr/bin/env python3
"""Parse Notion page + blocks JSON, extract all fields + body_text."""
import json, sys

def extract_plain_text(rich_text_arr):
    return ''.join(t.get('plain_text', '') for t in (rich_text_arr or []))

def parse_block_text(block):
    """Recursively extract text from a block."""
    btype = block.get('type', '')
    content = block.get(btype, {})
    if btype == 'paragraph':
        return extract_plain_text(content.get('rich_text', []))
    elif btype == 'heading_1':
        return '# ' + extract_plain_text(content.get('rich_text', []))
    elif btype == 'heading_2':
        return '## ' + extract_plain_text(content.get('rich_text', []))
    elif btype == 'heading_3':
        return '### ' + extract_plain_text(content.get('rich_text', []))
    elif btype == 'bulleted_list_item':
        return '- ' + extract_plain_text(content.get('rich_text', []))
    elif btype == 'numbered_list_item':
        return '1. ' + extract_plain_text(content.get('rich_text', []))
    elif btype == 'quote':
        return '> ' + extract_plain_text(content.get('rich_text', []))
    elif btype == 'code':
        lang = content.get('language', '')
        code = extract_plain_text(content.get('rich_text', []))
        return f'```{lang}\n{code}\n```'
    elif btype == 'to_do':
        checked = content.get('checked', False)
        prefix = '- [x] ' if checked else '- [ ] '
        return prefix + extract_plain_text(content.get('rich_text', []))
    elif btype == 'callout':
        return extract_plain_text(content.get('rich_text', []))
    elif btype == 'divider':
        return '---'
    elif btype == 'image':
        caption = extract_plain_text(content.get('caption', []))
        url = (content.get('external') or content.get('file') or {}).get('url', '')
        return f'![{caption}]({url})' if url else ''
    elif btype == 'embed':
        return content.get('url', '')
    elif btype == 'bookmark':
        caption = extract_plain_text(content.get('caption', []))
        url = content.get('url', '')
        return f'🔗 {caption} <{url}>' if caption else f'🔗 {url}'
    elif btype == 'child_page':
        return f'## 📄 子页面：{content.get("title", "")}'
    else:
        # fallback: try rich_text
        return extract_plain_text(content.get('rich_text', []))

def main():
    if len(sys.argv) < 3:
        print(json.dumps({"error": "用法: notion-fetch.py <page.json> <blocks.json>"}))
        sys.exit(1)

    page_path = sys.argv[1]
    blocks_path = sys.argv[2]

    with open(page_path) as f:
        page = json.load(f)
    with open(blocks_path) as f:
        blocks_data = json.load(f)

    # Extract properties
    props = page.get('properties', {})
    result = {
        'id': page.get('id', ''),
        'url': page.get('url', ''),
        'created_time': page.get('created_time', ''),
    }

    for k, v in props.items():
        t = v.get('type', '')
        if t == 'title':
            result['title'] = extract_plain_text(v.get('title', []))
        elif t == 'rich_text':
            result['fleeting_notes'] = extract_plain_text(v.get('rich_text', []))
        elif t == 'multi_select':
            result['tags'] = [o['name'] for o in v.get('multi_select', [])]
        elif t == 'select':
            s = v.get('select')
            result['source'] = s['name'] if s else None
        elif t == 'url':
            result['original_url'] = v.get('url')
        elif t == 'created_time':
            result['created_time'] = v.get('created_time')

    # Extract body text from blocks
    body_parts = []
    for block in blocks_data.get('results', []):
        text = parse_block_text(block)
        if text.strip():
            body_parts.append(text)

    result['body_text'] = '\n\n'.join(body_parts)

    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
