---
name: "netease_playlist_export"
description: "Extract NetEase Cloud Music (网易云音乐) playlist tracks into a text file formatted as 'song — artist', no login needed for public playlists. Use when the user asks to export, back up, or list the songs in a NetEase playlist."
---

# NetEase Playlist Export

## Purpose
Given a NetEase Cloud Music playlist URL (or raw playlist ID), export its full track list to a text file in the form "N. 歌名 — 歌手".

## Tooling
Bundled script: `extract_netease_playlist.py` in this directory (self-contained; only requires the `requests` package).

```bash
python3 extract_netease_playlist.py '<playlist-url-or-id>' --format text > raw.txt
```

Supported inputs: `https://music.163.com/playlist?id=XXX`, `y.music.163.com/m/playlist?id=XXX`, short links like `https://163cn.tv/XXX`, or a raw numeric playlist ID.

The script returns playlist metadata (name, track count) plus the numbered track list, then fetches each track's details in batches of 100 via NetEase's public API endpoints. Post-process to the final format:

```bash
# strip trailing durations like " [4:29]" and add the export timestamp at the top
TZ='Asia/Shanghai' python3 -c "
import re,sys,datetime
out=[]
for line in sys.stdin:
    line=re.sub(r'\s+\[\d+:\d+\]$','',line.rstrip('\n'))
    out.append(line)
out.insert(0,'导出时间: '+datetime.datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z'))
sys.stdout.write('\n'.join(out))
" < raw.txt > "<歌单名>.txt"
```

One file per playlist named `<歌单名>.txt`. For a ZIP bundle use the naming convention `网易云音乐歌单导出-<YYYY年MM月DD日>.zip` (e.g. `网易云音乐歌单导出-2026年10月04日.zip` via `date '+%Y年%m月%d日'`).

## Auth
None. The script uses NetEase's public web-player endpoints, which work for **public playlists only**. If the playlist is private or the API returns an auth error, stop and tell the user the playlist requires login — do not ask for or store their NetEase password.

## Operating Rules
1. Default output format is "N. 歌名 — 歌手" with **no duration**. Keep the duration only if the user explicitly asks for it.
2. Multi-artist tracks are rendered "歌名 — 歌手A, 歌手B" (comma-separated); keep this form.
3. On re-export for the user, replace the existing 导出时间 line instead of stacking a second one.
4. Verify the header line: it shows `<name> — 网易云音乐歌单 (<fetched>/<total>首)`. If fetched < total, tell the user how many tracks could not be retrieved (usually downlisted songs).
5. Export playlists one at a time or in parallel — do not merge multiple playlists into a single file unless asked.
6. The script is copied from https://github.com/soujiokita98/playlist-roast-skill (MIT License).
