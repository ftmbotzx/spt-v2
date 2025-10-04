from flask import Flask, request, jsonify
import requests
import cloudscraper
import json
import brotli
import gzip
import zstandard
import re
import os

# Initialize Flask app
app = Flask(__name__)

def decompress_response(response):
    """Decompresses the response content based on content-encoding header."""
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
        except Exception:
            return response.text
    try:
        return data.decode('utf-8')
    except UnicodeDecodeError:
        return response.text

def get_track_info(spotify_url, session):
    """Fetches only the track metadata from the SpotifySave service."""
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
    except (requests.RequestException, json.JSONDecodeError) as e:
        print(f"Error getting track info: {e}")
        return None

def get_direct_download_link(spotify_url, title, artist, session):
    """
    Makes a request to the download endpoint to resolve the final, direct file URL.
    """
    headers = {
        'Accept': '*/*',
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
        'Origin': 'https://spotifysave.com',
        'Referer': 'https://spotifysave.com/',
        'Accept-Encoding': 'gzip, deflate, br, zstd'
    }
    payload = {'title': title, 'artist': artist, 'url': spotify_url}
    try:
        # Use stream=True to avoid downloading the file content.
        # The service redirects to the actual file, and response.url will hold the final URL.
        response = session.post('https://spotifysave.com/download', headers=headers, json=payload, allow_redirects=True, stream=True)
        response.raise_for_status()
        # The final URL after all redirects is what we want.
        direct_link = response.url
        # It's important to close the response to free up the connection.
        response.close()
        return direct_link
    except requests.RequestException as e:
        print(f"Error getting direct download link: {e}")
        return None

def is_valid_spotify_url(url):
    """Validates the Spotify track URL format."""
    return re.match(r'^https://open\.spotify\.com/track/[a-zA-Z0-9]+.*$', url)

@app.route('/')
def index():
    """A simple health check endpoint."""
    return jsonify({"status": "ok", "message": "Spotify Direct Link API is running"}), 200

@app.route('/ftmdl', methods=['GET', 'POST'])
def get_info_and_direct_link():
    """
    Performs a two-step fetch to get metadata and the direct download link.
    """
    spotify_url = request.args.get('url') if request.method == 'GET' else (request.get_json() or {}).get('url')

    if not spotify_url:
        return jsonify({"error": "URL parameter is missing or invalid"}), 400

    if not is_valid_spotify_url(spotify_url):
        return jsonify({"error": "Invalid Spotify track URL format"}), 400

    scraper = cloudscraper.create_scraper()
    try:
        scraper.get('https://spotifysave.com')
    except requests.RequestException as e:
        return jsonify({"error": f"Failed to access the download service: {e}"}), 503

    # Step 1: Get the track metadata
    track_info = get_track_info(spotify_url, scraper)
    if not track_info or 'title' not in track_info or 'artist' not in track_info:
        return jsonify({"error": "Failed to retrieve complete track metadata from the source"}), 500

    # Step 2: Use the metadata to get the actual direct download link
    title = track_info.get('title')
    artist = track_info.get('artist')
    direct_download_link = get_direct_download_link(spotify_url, title, artist, scraper)

    if not direct_download_link:
        return jsonify({"error": "Failed to resolve the direct download link"}), 500

    return jsonify({
        "trackinfo": track_info,
        "downloadurl": direct_download_link
    })

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)


