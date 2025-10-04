import requests
import cloudscraper
import json
import brotli
import gzip
import zstandard
import re
import os

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
        'Accept': '*/*',
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
        'Origin': 'https://spotifysave.com',
        'Referer': 'https://spotifysave.com/',
        'Accept-Encoding': 'gzip, deflate, br, zstd'
    }
    payload = {'url': spotify_url}
    try:
        response = session.post('https://spotifysave.com/track-info', headers=headers, json=payload)
        response.raise_for_status()
        return json.loads(decompress_response(response))
    except (requests.RequestException, json.JSONDecodeError):
        return None

def download_file(spotify_url, title, artist, session):
    headers = {
        'Accept': '*/*',
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
        'Origin': 'https://spotifysave.com',
        'Referer': 'https://spotifysave.com/',
        'Accept-Encoding': 'gzip, deflate, br, zstd'
    }
    payload = {
        'title': title,
        'artist': artist,
        'url': spotify_url
    }
    try:
        response = session.post('https://spotifysave.com/download', headers=headers, json=payload, stream=True)
        response.raise_for_status()
        content_disposition = response.headers.get('content-disposition', '')
        filename = re.search(r'filename="(.+)"', content_disposition)
        filename = filename.group(1) if filename else f"{title} - {artist}.mp3"
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        with open(filename, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        return filename
    except requests.RequestException:
        return None

def main():
    spotify_url = input("Enter Spotify URL: ")
    if not re.match(r'^https://open\.spotify\.com/track/[a-zA-Z0-9]+$', spotify_url):
        print("Invalid Spotify track URL")
        return

    scraper = cloudscraper.create_scraper()
    try:
        response = scraper.get('https://spotifysave.com')
        response.raise_for_status()
    except requests.RequestException:
        print("Failed to access spotifysave.com")
        return

    track_info = get_track_info(spotify_url, scraper)
    if not track_info:
        print("Failed to retrieve track information")
        return

    print("Song Info:")
    print(f"Title: {track_info.get('title', 'Unknown')}")
    print(f"Artist: {track_info.get('artist', 'Unknown')}")
    print(f"Image: {track_info.get('image', 'Unknown')}")
    print(f"Duration: {track_info.get('duration', 'Unknown')}")
    print(f"URL: {track_info.get('url', 'Unknown')}")

    filename = download_file(spotify_url, track_info.get('title'), track_info.get('artist'), scraper)
    if not filename:
        print("Failed to download the file")
        return

    print(f"File downloaded: {os.path.abspath(filename)}")

if __name__ == "__main__":
    main()
