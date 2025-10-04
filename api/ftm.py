import requests
import cloudscraper
import json
import re
import brotli
import gzip
import zstandard

def decompress_response(response):
    encodings = response.headers.get("content-encoding", "").split(",")
    data = response.content
    for encoding in encodings:
        encoding = encoding.strip()
        try:
            if encoding == "br":
                data = brotli.decompress(data)
            elif encoding == "gzip":
                data = gzip.decompress(data)
            elif encoding == "zstd":
                data = zstandard.ZstdDecompressor().decompress(data)
        except:
            return response.text
    try:
        return data.decode("utf-8")
    except:
        return response.text

def get_track_info(spotify_url, session):
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0",
        "Origin": "https://spotifysave.com",
        "Referer": "https://spotifysave.com/",
        "Accept-Encoding": "gzip, deflate, br, zstd",
    }
    payload = {"url": spotify_url}
    try:
        res = session.post("https://spotifysave.com/track-info", headers=headers, json=payload)
        res.raise_for_status()
        return json.loads(decompress_response(res))
    except:
        return None

def handler(request, response):
    # GET or POST
    if request.method == "GET":
        spotify_url = request.query.get("url")
    elif request.method == "POST":
        spotify_url = request.json().get("url")
    else:
        return response.status(405).json({"error": "Only GET/POST allowed"})

    if not spotify_url or not re.match(r"^https://open\.spotify\.com/track/[a-zA-Z0-9]+$", spotify_url):
        return response.status(400).json({"error": "Invalid Spotify URL"})

    scraper = cloudscraper.create_scraper()
    track_info = get_track_info(spotify_url, scraper)
    if not track_info or not track_info.get("url"):
        return response.status(500).json({"error": "Failed to fetch track info"})

    # Fetch MP3 into memory
    mp3_res = scraper.get(track_info["url"])
    if mp3_res.status_code != 200:
        return response.status(500).json({"error": "Failed to download MP3"})

    filename = f"{track_info.get('title','Unknown')}-{track_info.get('artist','Unknown')}.mp3"

    return (
        response.set_header("Content-Type", "audio/mpeg")
        .set_header("Content-Disposition", f"attachment; filename=\"{filename}\"")
        .send(mp3_res.content)
    )
