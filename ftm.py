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

def get_track_info_and_link(spotify_url, session):
    """
    Fetches track information from the SpotifySave service.
    This function now expects the response to contain the direct download link.
    """
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
        # The /track-info endpoint is assumed to return the direct download link
        response = session.post('https://spotifysave.com/track-info', headers=headers, json=payload)
        response.raise_for_status()
        return json.loads(decompress_response(response))
    except (requests.RequestException, json.JSONDecodeError) as e:
        print(f"Error getting track info: {e}")
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
    Returns track info and the original download link from the source service.
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

    # Fetch track data, which should include the download link
    track_data = get_track_info_and_link(spotify_url, scraper)

    if not track_data:
        return jsonify({"error": "Failed to retrieve track metadata from the source"}), 500

    # We expect the source API to provide a 'link' key for the direct download.
    direct_download_link = track_data.get('link')

    # The original 'url' key is the Spotify URL, which we can remove to avoid confusion
    if 'url' in track_data:
        del track_data['url'] 
        
    return jsonify({
        "trackinfo": track_data,
        "downloadurl": direct_download_link
    })

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)


