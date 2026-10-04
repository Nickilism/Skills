#!/usr/bin/env python3
"""Extract tracks from a public NetEase Cloud Music (网易云音乐) playlist URL without login.

Method:
1. Parse playlist ID from URL (supports multiple URL formats).
2. Call NetEase API endpoint for playlist detail.
3. Paginate if needed (NetEase returns up to 1000 tracks per request).
4. Output as text, JSON, or CSV.

Works for public playlists only. Private playlists require authentication.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from typing import Any

import requests

# Match various NetEase playlist URL formats
# Handles: playlist?id=XXX, playlist/detail?id=XXX, 163cn.tv/XXX
PLAYLIST_RE = re.compile(r"[?&]id=(\d+)")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://music.163.com/",
    "Accept": "application/json, text/plain, */*",
}


def playlist_id(value: str) -> str:
    """Extract playlist ID from URL or raw ID string."""
    # If it's a short URL like 163cn.tv, resolve it first
    if "163cn.tv" in value:
        try:
            r = requests.head(value, headers=HEADERS, allow_redirects=True, timeout=10)
            value = r.url
        except Exception:
            pass

    # Try to find id= parameter in URL
    m = PLAYLIST_RE.search(value)
    if m:
        return m.group(1)

    # Try to find playlist/XXX pattern
    m = re.search(r"playlist/(\d+)", value)
    if m:
        return m.group(1)

    # Raw numeric ID
    if re.fullmatch(r"\d+", value):
        return value

    raise SystemExit(f"Could not parse NetEase playlist id from: {value}")


def fetch_playlist_detail(pid: str) -> dict[str, Any]:
    """Fetch playlist detail from NetEase API."""
    url = "https://music.163.com/api/v6/playlist/detail"
    params = {"id": pid, "n": 100000, "s": 0}
    r = requests.get(url, headers=HEADERS, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    if data.get("code") != 200:
        raise RuntimeError(f"NetEase API error: {data.get('code')} - {data.get('msg', 'Unknown error')}")
    return data.get("playlist", {})


def fetch_track_details(track_ids: list[int]) -> list[dict[str, Any]]:
    """Fetch detailed track info in batches of 100 (API limit)."""
    url = "https://music.163.com/api/song/detail"
    all_tracks = []
    batch_size = 100  # NetEase API returns 0 results for batches > ~300
    for i in range(0, len(track_ids), batch_size):
        batch = track_ids[i : i + batch_size]
        ids_str = ",".join(str(tid) for tid in batch)
        params = {"ids": f"[{ids_str}]"}
        r = requests.get(url, headers=HEADERS, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        songs = data.get("songs", [])
        all_tracks.extend(songs)
        if i + batch_size < len(track_ids):
            time.sleep(0.3)  # Rate limiting
    return all_tracks


def ms_to_mmss(ms: int) -> str:
    """Convert milliseconds to MM:SS format."""
    if not ms:
        return ""
    seconds = ms // 1000
    return f"{seconds // 60}:{seconds % 60:02d}"


def extract(pid: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Extract playlist metadata and tracks."""
    playlist = fetch_playlist_detail(pid)

    meta = {
        "id": pid,
        "title": playlist.get("name", ""),
        "owner": (playlist.get("creator") or {}).get("nickname", ""),
        "total": playlist.get("trackCount", 0),
        "play_count": playlist.get("playCount", 0),
        "cover_url": playlist.get("coverImgUrl", ""),
        "description": playlist.get("description", ""),
    }

    # Get track IDs from the playlist detail
    track_ids = [t.get("id") for t in playlist.get("trackIds", []) if t.get("id")]

    # The playlist detail may already contain full track info in "tracks" field
    # If it does and covers all tracks, use it directly; otherwise fetch details
    existing_tracks = playlist.get("tracks", [])
    if len(existing_tracks) >= len(track_ids):
        # All tracks already loaded
        raw_tracks = existing_tracks
    else:
        # Need to fetch track details in batches
        print(f"Fetching details for {len(track_ids)} tracks...", file=sys.stderr)
        raw_tracks = fetch_track_details(track_ids)

    tracks = []
    for t in raw_tracks:
        if not t.get("name"):
            continue
        artists = ", ".join(a.get("name", "") for a in (t.get("artists") or []) if a.get("name"))
        album = (t.get("album") or {})
        tracks.append(
            {
                "name": t.get("name", ""),
                "artists": artists,
                "album": album.get("name", ""),
                "duration_ms": t.get("duration"),
                "duration": ms_to_mmss(t.get("duration", 0)),
                "url": f"https://music.163.com/song?id={t.get('id', '')}",
                "id": t.get("id"),
            }
        )

    # If we got fewer tracks than expected, some may have been removed/unavailable
    # Fill in from trackIds for completeness
    if len(tracks) < len(track_ids):
        fetched_ids = {t.get("id") for t in raw_tracks if t.get("id")}
        missing_ids = [tid for tid in track_ids if tid not in fetched_ids]
        if missing_ids:
            print(f"Note: {len(missing_ids)} tracks unavailable (possibly removed or region-locked)", file=sys.stderr)

    return meta, tracks


def main() -> None:
    ap = argparse.ArgumentParser(description="Extract tracks from a NetEase Cloud Music playlist")
    ap.add_argument("playlist", help="Playlist URL or ID")
    ap.add_argument("--format", choices=["text", "json", "csv"], default="text")
    args = ap.parse_args()

    pid = playlist_id(args.playlist)
    meta, tracks = extract(pid)

    if args.format == "json":
        print(json.dumps({"playlist": meta, "tracks": tracks}, ensure_ascii=False, indent=2))
    elif args.format == "csv":
        w = csv.DictWriter(sys.stdout, fieldnames=["index", "name", "artists", "album", "duration", "duration_ms", "url", "id"])
        w.writeheader()
        for i, t in enumerate(tracks, 1):
            w.writerow({"index": i, **t})
    else:
        print(f"{meta['title']} — 网易云音乐歌单 ({len(tracks)}/{meta['total']}首)")
        print(f"https://music.163.com/playlist?id={meta['id']}")
        if meta.get("owner"):
            print(f"创建者: {meta['owner']}")
        if meta.get("play_count"):
            print(f"播放次数: {meta['play_count']:,}")
        print()
        for i, t in enumerate(tracks, 1):
            print(f"{i}. {t['name']} — {t['artists']}  [{t['duration']}]")


if __name__ == "__main__":
    main()
