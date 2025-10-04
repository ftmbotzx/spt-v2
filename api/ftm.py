import requests
import cloudscraper
import json
import brotli
import gzip
import zstandard
import re

def decompress_response(response):
    encodings = response.headers.get('content-encoding', '').split(',')
    data = response.content
    if not encodings or encodings == ['']:
        return response.text
    for encoding in encodings:
        encoding = encoding.strip()
        try:
            if encoding == 'br':
                data = brotli.decompress(data)
            elif encoding == 'gzip':
                data = gzip.decompress(data)
            elif encoding == 'zstd':
                data = zstandard.ZstdDecompressor().decompress(data)
        except:
            return response.text
    try:
        return data.decode('utf-8')
    except UnicodeDecodeError:
        return response.text

def get_track_info(spotify_url, session):
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0",
        "Origin": "https://spotifysave.com",
        "Referer": "https://spotifysave.com/",
        "Accept-Encoding": "gzip, deflate, br, zstd"
    }
    payload = {"url": spotify_url}
    try:
        response = session.post("https://spotifysave.com/track-info", headers=headers, json=payload)
        response.raise_for_status()
        return json.loads(decompress_response(response))
    except:
        return None


def handler(request, response):
    # Support GET and POST
    if request.method == "GET":
        spotify_url = request.query.get("url")
    elif request.method == "POST":
        spotify_url = request.json().get("url")
    else:
        return response.status(405).json({"error": "Only GET and POST allowed"})

    if not spotify_url or not re.match(r"^https://open\.spotify\.com/track/[a-zA-Z0-9]+$", spotify_url):
        return response.status(400).json({"error": "Invalid or missing Spotify track URL"})

    scraper = cloudscraper.create_scraper()
    track_info = get_track_info(spotify_url, scraper)

    if not track_info or not track_info.get("url"):
        return response.status(500).json({"error": "Failed to fetch track info"})

    # Get MP3 file from the returned track_info URL
    mp3_url = track_info["url"]
    mp3_response = scraper.get(mp3_url, stream=True)

    filename = f"{track_info.get('title', 'Unknown')} - {track_info.get('artist', 'Unknown')}.mp3"

    # Return as streaming HTTP response
    return response.set_header("Content-Type", "audio/mpeg")\
                   .set_header("Content-Disposition", f"attachment; filename=\"{filename}\"")\
                   .send(mp3_response.content)
