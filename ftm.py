from flask import Flask, request, jsonify, send_file, url_for
import requests
import cloudscraper
import json
import brotli
import gzip
import zstandard
import re
import os
import urllib.parse

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
    """Fetches track information from the SpotifySave service."""
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

def download_track_file(spotify_url, title, artist, session):
    """Downloads the track file from the SpotifySave service and saves it temporarily."""
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
        response = session.post('https://spotifysave.com/download', headers=headers, json=payload, stream=True)
        response.raise_for_status()
        
        content_disposition = response.headers.get('content-disposition', '')
        filename_search = re.search(r'filename="(.+)"', content_disposition)
        filename = filename_search.group(1) if filename_search else f"{title} - {artist}.mp3"
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        
        download_dir = 'temp_downloads'
        if not os.path.exists(download_dir):
            os.makedirs(download_dir)
        filepath = os.path.join(download_dir, filename)

        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        return filepath
    except requests.RequestException as e:
        print(f"Error downloading file: {e}")
        return None

def is_valid_spotify_url(url):
    """Validates the Spotify track URL format."""
    return re.match(r'^https://open\.spotify\.com/track/[a-zA-Z0-9]+.*$', url)

@app.route('/ftmdl', methods=['GET', 'POST'])
def get_info_and_link():
    """
    Returns track info and a dedicated download link.
    GET usage: /ftmdl?url=<spotify_track_url>
    POST usage: /ftmdl with JSON body {"url": "<spotify_track_url>"}
    """
    spotify_url = None
    if request.method == 'GET':
        spotify_url = request.args.get('url')
    elif request.method == 'POST':
        data = request.get_json()
        if data and 'url' in data:
            spotify_url = data['url']

    if not spotify_url:
        return jsonify({"error": "URL parameter is missing or invalid"}), 400

    if not is_valid_spotify_url(spotify_url):
        return jsonify({"error": "Invalid Spotify track URL format"}), 400

    scraper = cloudscraper.create_scraper()
    try:
        scraper.get('https://spotifysave.com')
    except requests.RequestException as e:
        return jsonify({"error": f"Failed to access the download service: {e}"}), 503

    track_info = get_track_info(spotify_url, scraper)
    if not track_info:
        return jsonify({"error": "Failed to retrieve track metadata"}), 500

    # Generate a download URL that points to our own /download endpoint
    encoded_url = urllib.parse.quote(spotify_url)
    download_link = url_for('download_file_endpoint', url=encoded_url, _external=True)

    return jsonify({
        "trackinfo": track_info,
        "downloadurl": download_link
    })

@app.route('/download')
def download_file_endpoint():
    """
    This endpoint is called by the downloadurl. It downloads and serves the file.
    """
    spotify_url = request.args.get('url')
    if not spotify_url:
        return jsonify({"error": "URL parameter for download is missing"}), 400
    
    scraper = cloudscraper.create_scraper()
    try:
        scraper.get('https://spotifysave.com')
    except requests.RequestException:
        return jsonify({"error": "Failed to connect to download service"}), 503

    track_info = get_track_info(spotify_url, scraper)
    if not track_info or 'title' not in track_info or 'artist' not in track_info:
        return jsonify({"error": "Failed to retrieve track info for download"}), 500

    filepath = download_track_file(spotify_url, track_info.get('title'), track_info.get('artist'), scraper)
    if not filepath:
        return jsonify({"error": "Failed to download the file from the source"}), 500

    try:
        return send_file(filepath, as_attachment=True, download_name=os.path.basename(filepath))
    finally:
        # Clean up the temp file after sending it
        if os.path.exists(filepath):
            os.remove(filepath)

if __name__ == '__main__':
    # Get port from environment variable or default to 5000
    port = int(os.environ.get("PORT", 5000))
    # Run the app, listening on all interfaces
    app.run(host='0.0.0.0', port=port, debug=False)


