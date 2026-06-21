#!/usr/bin/env python3
"""WeRead → Anki helper: fetch highlights, parse text, merge CSV batches."""

import json, os, sys, subprocess, re, glob, base64

API_URL = "https://i.weread.qq.com/api/agent/gateway"
SKILL_VERSION = "1.0.3"

def api_call(api_name, **params):
    body = {"api_name": api_name, "skill_version": SKILL_VERSION, **params}
    result = subprocess.run(
        ["curl", "-s", "-X", "POST", API_URL,
         "-H", f"Authorization: Bearer {os.environ.get('WEREAD_API_KEY', '')}",
         "-H", "Content-Type: application/json",
         "-d", json.dumps(body)],
        capture_output=True, text=True
    )
    return json.loads(result.stdout) if result.stdout else {}

def fetch_book_highlights(book_id):
    """Fetch highlights + reviews for a book, return formatted bullet list + metadata."""
    # Fetch highlights
    hl = api_call("/book/bookmarklist", bookId=book_id)
    # Fetch personal notes/reviews
    rv = api_call("/review/list/mine", bookid=book_id, count=200)
    
    if "updated" not in hl:
        return None, None, []
    
    # Build chapter map
    chapters = {}
    for ch in hl.get("chapters", []):
        chapters[ch["chapterUid"]] = ch.get("title", "")
    
    # Book info
    book_info = hl.get("book", {})
    title = book_info.get("title", "未知书名")
    author = book_info.get("author", "未知")
    
    # Format highlights
    lines = []
    seen = set()
    for item in hl.get("updated", []):
        text = item.get("markText", "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ch_uid = item.get("chapterUid", 0)
        ch_name = chapters.get(ch_uid, "")
        prefix = f"[{ch_name}] " if ch_name else ""
        lines.append(f"◆ {prefix}{text}")
    
    # Add reviews/thoughts
    for r in rv.get("reviews", []):
        rev = r.get("review", {})
        content = rev.get("content", "").strip()
        if not content or content in seen:
            continue
        seen.add(content)
        ch_name = rev.get("chapterName", "")
        abstract = rev.get("abstract", "").strip()
        prefix = f"[{ch_name}] " if ch_name else ""
        if abstract:
            lines.append(f"◆ {prefix}💭 {content}（对应划线：{abstract[:30]}...）")
        else:
            lines.append(f"◆ {prefix}💭 {content}")
    
    return title, author, lines

def find_book_in_notebooks(keyword):
    """Search user's notebook list by title keyword. Returns matching books."""
    results = []
    last_sort = None
    while True:
        params = {"count": 200}
        if last_sort:
            params["lastSort"] = last_sort
        data = api_call("/user/notebooks", **params)
        for b in data.get("books", []):
            info = b.get("book", {})
            title = info.get("title", "")
            if keyword.lower() in title.lower():
                results.append({
                    "bookId": b.get("bookId", ""),
                    "title": title,
                    "author": info.get("author", "未知"),
                    "notes": b.get("noteCount", 0) + b.get("reviewCount", 0)
                })
        if data.get("hasMore") != 1:
            break
        last_sort = data["books"][-1].get("sort")
    return results

def search_book(keyword):
    """Search store books, return results list."""
    result = api_call("/store/search", keyword=keyword, count=5)
    books = result.get("books", [])
    return [{
        "bookId": b.get("bookId", ""),
        "title": b.get("book", {}).get("title", ""),
        "author": b.get("book", {}).get("author", ""),
        "intro": b.get("book", {}).get("intro", "")[:100]
    } for b in books]

def parse_pasted_text(text):
    """Parse manually pasted WeRead highlights into structured format.
    
    Returns (title, author, lines) — title/author are '未知' since we can't 
    infer them reliably from pasted text.
    """
    text = text.strip()
    if not text:
        return "未知", "未知", []
    
    # Try to detect book title from first non-highlight line
    lines_raw = text.split("\n")
    title = "未知"
    author = "未知"
    
    # Clean and format
    lines = []
    for raw_line in lines_raw:
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("◆"):
            lines.append(line)
        elif not lines:
            # Before any highlight — might be title/header, skip
            pass
    
    return title, author, lines

def batch_lines(lines, batch_size=40):
    """Split lines into batches."""
    return [lines[i:i+batch_size] for i in range(0, len(lines), batch_size)]

def format_batch_input(title, author, book_id, batch_lines):
    """Format a batch of highlights into the model input string."""
    if book_id.startswith("CB_"):
        weread_url = f"weread://reading?bId={book_id}"
    elif book_id:
        weread_url = f"https://weread.qq.com/web/bookDetail/{book_id}"
    else:
        weread_url = ""
    header = f"书名：{title}\n作者：{author}"
    if weread_url:
        header += f"\n书籍链接：{weread_url}"
    header += "\n\n以下是划线摘录：\n\n"
    body = "\n".join(batch_lines)
    return header + body

def merge_csv_batches(batch_dir, output_path):
    """Merge all batch CSV files into one, skipping empty lines."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    pattern = os.path.join(batch_dir, "anki_batch_*.csv")
    files = sorted(glob.glob(pattern))
    count = 0
    with open(output_path, "w", encoding="utf-8") as out:
        for f in files:
            with open(f, "r", encoding="utf-8") as inp:
                for line in inp:
                    line = line.strip()
                    if line:
                        out.write(line + "\n")
                        count += 1
    return count

def upload_to_github(file_path, repo="Nickilism/Skills", base_dir="weread-anki/Anki"):
    """Upload a CSV file to GitHub using the Contents API."""
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        return {"ok": False, "error": "GITHUB_TOKEN not set"}
    
    filename = os.path.basename(file_path)
    remote_path = f"{base_dir}/{filename}"
    api_url = f"https://api.github.com/repos/{repo}/contents/{remote_path}"
    
    with open(file_path, "rb") as f:
        content_b64 = base64.b64encode(f.read()).decode("utf-8")
    
    # Check if file exists (get SHA for update)
    sha = None
    result = subprocess.run(
        ["curl", "-s", "-w", "\n%{http_code}", api_url,
         "-H", f"Authorization: token {token}",
         "-H", "Accept: application/vnd.github.v3+json"],
        capture_output=True, text=True
    )
    lines = result.stdout.strip().split("\n")
    status_code = int(lines[-1]) if lines else 0
    if status_code == 200:
        try:
            sha = json.loads("\n".join(lines[:-1])).get("sha")
        except json.JSONDecodeError:
            pass
    
    # Create or update file
    payload = {
        "message": f"Add Anki cards: {filename}",
        "content": content_b64,
    }
    if sha:
        payload["sha"] = sha
    
    result = subprocess.run(
        ["curl", "-s", "-w", "\n%{http_code}", "-X", "PUT", api_url,
         "-H", f"Authorization: token {token}",
         "-H", "Content-Type: application/json",
         "-H", "Accept: application/vnd.github.v3+json",
         "-d", json.dumps(payload)],
        capture_output=True, text=True
    )
    lines = result.stdout.strip().split("\n")
    status_code = int(lines[-1]) if lines else 0
    body = "\n".join(lines[:-1])
    
    if status_code in (200, 201):
        try:
            html_url = json.loads(body).get("content", {}).get("html_url", "")
        except json.JSONDecodeError:
            html_url = f"https://github.com/{repo}/blob/main/{remote_path}"
        return {"ok": True, "url": html_url, "path": remote_path}
    else:
        return {"ok": False, "status": status_code, "error": body[:200]}

# --- CLI interface ---
if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    
    if cmd == "search-notebooks":
        keyword = " ".join(sys.argv[2:])
        results = find_book_in_notebooks(keyword)
        for i, b in enumerate(results):
            print(f"{i+1}. {b['title']} — {b['author']} (ID: {b['bookId']}, notes: {b['notes']})")
    
    elif cmd == "search":
        keyword = " ".join(sys.argv[2:])
        results = search_book(keyword)
        for i, b in enumerate(results):
            print(f"{i+1}. {b['title']} — {b['author']} (ID: {b['bookId']})")
    
    elif cmd == "fetch":
        book_id = sys.argv[2]
        title, author, lines = fetch_book_highlights(book_id)
        if lines is None:
            print("ERROR: 无法获取划线内容", file=sys.stderr)
            sys.exit(1)
        # Save metadata
        meta = {"title": title, "author": author, "bookId": book_id, "count": len(lines)}
        print(json.dumps(meta, ensure_ascii=False))
        # Save formatted lines
        with open("/tmp/weread_lines.txt", "w") as f:
            f.write("\n".join(lines))
        print(f"Saved {len(lines)} highlights to /tmp/weread_lines.txt")
    
    elif cmd == "parse":
        # Read from stdin or file
        if len(sys.argv) > 2:
            with open(sys.argv[2]) as f:
                text = f.read()
        else:
            text = sys.stdin.read()
        title, author, lines = parse_pasted_text(text)
        meta = {"title": title, "author": author, "bookId": "", "count": len(lines)}
        print(json.dumps(meta, ensure_ascii=False))
        with open("/tmp/weread_lines.txt", "w") as f:
            f.write("\n".join(lines))
        print(f"Parsed {len(lines)} highlights to /tmp/weread_lines.txt")
    
    elif cmd == "batch":
        batch_size = int(sys.argv[2]) if len(sys.argv) > 2 else 40
        with open("/tmp/weread_lines.txt") as f:
            lines = [l.strip() for l in f if l.strip()]
        batches = batch_lines(lines, batch_size)
        os.makedirs("/tmp/anki_batches", exist_ok=True)
        for i, batch in enumerate(batches):
            with open(f"/tmp/anki_batches/batch_{i:03d}.txt", "w") as f:
                f.write("\n".join(batch))
        print(json.dumps({"total_lines": len(lines), "batches": len(batches)}, ensure_ascii=False))
    
    elif cmd == "merge":
        import datetime
        title_slug = sys.argv[2] if len(sys.argv) > 2 else "weread"
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        output = f"/var/minis/attachments/anki/{title_slug}_{ts}.csv"
        count = merge_csv_batches("/tmp/anki_batches", output)
        print(json.dumps({"output": output, "cards": count}, ensure_ascii=False))
    
    elif cmd == "upload":
        import glob as g
        title_slug = sys.argv[2] if len(sys.argv) > 2 else "weread"
        # Find the latest CSV matching the title slug
        pattern = f"/var/minis/attachments/anki/{title_slug}_*.csv"
        files = sorted(g.glob(pattern))
        if not files:
            print(json.dumps({"ok": False, "error": f"No CSV found matching {pattern}"}, ensure_ascii=False))
            sys.exit(1)
        latest = files[-1]
        result = upload_to_github(latest)
        result["local_file"] = latest
        print(json.dumps(result, ensure_ascii=False))
    
    else:
        print("Usage: python3 weread_anki.py <command> [args]")
        print("  search-notebooks <keyword> — Search user's notebook list (preferred)")
        print("  search <keyword>     — Search WeRead store books")
        print("  fetch <bookId>       — Fetch highlights for a book")
        print("  parse [file]         — Parse pasted text (stdin or file)")
        print("  batch [size]         — Split into batches (default 40)")
        print("  merge [title_slug]   — Merge batch CSVs into final output")
        print("  upload [title_slug]  — Upload latest CSV to GitHub")
