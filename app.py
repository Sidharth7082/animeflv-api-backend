import os
import json
import re
import time # For caching timestamp
from flask import Flask, request, jsonify
from flask_cors import CORS # Used to handle Cross-Origin Resource Sharing
from animeflv import AnimeFLV, AnimeInfo, EpisodeInfo, EpisodeFormat
from cloudscraper.exceptions import CloudflareChallengeError # Import specific exception

# Initialize Flask app
app = Flask(__name__)
# Enable CORS for all routes - IMPORTANT for frontend to communicate with this API
CORS(app)

# --- Caching Configuration ---
# Simple in-memory cache
# Stores data like: {'endpoint_hash': {'data': data_object, 'timestamp': time.time()}}
cache = {}
CACHE_TTL = 3600 # Cache Time-To-Live in seconds (1 hour)

def get_cached_data(key):
    """Retrieves data from cache if not expired."""
    if key in cache:
        if (time.time() - cache[key]['timestamp']) < CACHE_TTL:
            print(f"CACHE: Hit for key: {key}")
            return cache[key]['data']
        else:
            print(f"CACHE: Expired for key: {key}. Deleting.")
            del cache[key] # Remove expired item
    print(f"CACHE: Miss for key: {key}")
    return None

def set_cached_data(key, data):
    """Stores data in cache with current timestamp."""
    cache[key] = {'data': data, 'timestamp': time.time()}
    print(f"CACHE: Data stored for key: {key}")

# --- Helper for Video Source Categorization ---
def categorize_video_source(url):
    """
    Analyzes a video URL and categorizes it as 'direct', 'embed', or 'unknown'.
    Prioritizes embed detection for common providers that use iframe embeds.
    """
    if not isinstance(url, str):
        print(f"WARNING: Categorization received non-string URL: Type={type(url)}, Value={url}")
        return "unknown"

    url_lower = url.lower()

    # Common embed patterns (prioritized)
    embed_patterns = [
        r'embed', r'yourupload\.com', r'streamwish\.to', r'streame\.net',
        r'streamtape\.com', r'fembed\.com', r'natu\.moe', r'ok\.ru', r'my\.mail\.ru',
        r'mega\.nz/embed'
    ]
    for pattern in embed_patterns:
        if re.search(pattern, url_lower):
            print(f"  CATEGORIZED: Embed - {url}")
            return "embed"

    # Common direct video extensions
    direct_patterns = [r'\.mp4', r'\.webm', r'\.ogg', r'\.mkv', r'\.avi', r'\.mov']
    for pattern in direct_patterns:
        if re.search(pattern, url_lower):
            print(f"  CATEGORIZED: Direct - {url}")
            return "direct"
    
    print(f"  CATEGORIZED: Unknown - {url}")
    return "unknown"

# --- API Endpoints ---

@app.route('/')
def home():
    """
    Basic home endpoint to confirm the API is running.
    """
    return "<h1>AnimeFLV API Backend is running!</h1><p>Use specific endpoints like /api/search, /api/anime-info, or /api/video-sources.</p><p>Check API health at /health</p>"

@app.route('/health', methods=['GET'])
def health_check():
    """
    Provides a health check endpoint for the API service.
    """
    return jsonify({"status": "healthy", "timestamp": time.time(), "message": "API is operational."}), 200


@app.route('/api/search', methods=['GET'])
def search_anime():
    """
    Searches for anime based on a query string.
    Expected query parameters:
    - query: The search term (e.g., "Naruto").
    - page: (Optional) The page number for results (e.g., 1).
    """
    query = request.args.get('query')
    page = request.args.get('page', type=int, default=None)

    if not query:
        return jsonify({"error": "Missing query parameter. Please provide a 'query' to search for anime.", "details": "Parameter 'query' is required."}), 400

    cache_key = f"search_{query}_{page or 'none'}"
    cached_results = get_cached_data(cache_key)
    if cached_results:
        return jsonify(cached_results)

    with AnimeFLV() as api:
        try:
            print(f"PROCESSING: Searching for anime: '{query}', Page: {page}")
            results = api.search(query=query, page=page)
            
            serializable_results = []
            for anime in results:
                serializable_results.append({
                    "id": anime.id,
                    "title": anime.title,
                    "poster": anime.poster,
                    "banner": anime.banner,
                    "synopsis": anime.synopsis,
                    "rating": anime.rating,
                    "genres": anime.genres,
                    "debut": anime.debut,
                    "type": anime.type
                })
            set_cached_data(cache_key, serializable_results)
            return jsonify(serializable_results)
        except CloudflareChallengeError:
            print("ERROR: Cloudflare challenge encountered during search.")
            return jsonify({"error": "Cloudflare challenge detected. Unable to bypass for this request. Please try again later.", "details": "The target website is actively challenging the scraper."}), 503
        except Exception as e:
            print(f"ERROR: Failed to search for anime '{query}': {e}")
            return jsonify({"error": f"Internal server error during search: {str(e)}", "details": "An unexpected error occurred while fetching data from the source."}), 500

@app.route('/api/anime-info/<string:anime_id>', methods=['GET'])
def get_anime_info_endpoint(anime_id):
    """
    Retrieves detailed information about a specific anime.
    Path parameter:
    - anime_id: The ID of the anime (e.g., "nanatsu-no-taizai").
    """
    if not anime_id:
        return jsonify({"error": "Missing anime ID. Please provide an 'anime_id' in the URL path.", "details": "URL parameter 'anime_id' is required."}), 400

    cache_key = f"anime_info_{anime_id}"
    cached_info = get_cached_data(cache_key)
    if cached_info:
        return jsonify(cached_info)

    with AnimeFLV() as api:
        try:
            print(f"PROCESSING: Getting info for anime ID: '{anime_id}'")
            anime_info = api.get_anime_info(id=anime_id) 
            
            serializable_episodes = []
            if anime_info.episodes:
                for episode in anime_info.episodes:
                    serializable_episodes.append({
                        "id": episode.id,
                        "anime": episode.anime,
                        "image_preview": episode.image_preview
                    })

            serializable_info = {
                "id": anime_info.id,
                "title": anime_info.title if anime_info.title else None,
                "poster": anime_info.poster if anime_info.poster else None,
                "banner": anime_info.banner if anime_info.banner else None,
                "synopsis": anime_info.synopsis if anime_info.synopsis else None,
                "rating": anime_info.rating if anime_info.rating else None,
                "genres": anime_info.genres if anime_info.genres else [],
                "debut": anime_info.debut if anime_info.debut else None,
                "type": anime_info.type if anime_info.type else None,
                "episodes": serializable_episodes
            }
            set_cached_data(cache_key, serializable_info)
            return jsonify(serializable_info)
        except CloudflareChallengeError:
            print(f"ERROR: Cloudflare challenge encountered for anime info '{anime_id}'.")
            return jsonify({"error": "Cloudflare challenge detected. Unable to bypass for this request. Please try again later.", "details": "The target website is actively challenging the scraper."}), 503
        except Exception as e:
            print(f"ERROR: Failed to get anime info for '{anime_id}': {e}")
            return jsonify({"error": f"Failed to retrieve or parse anime information: {str(e)}", "details": "The anime might not exist, or the site structure for this page has changed."}), 500

@app.route('/api/video-sources/<string:anime_id>/<int:episode_number>', methods=['GET'])
def get_video_sources_endpoint(anime_id, episode_number):
    video_format_str = request.args.get('format', 'subtitled').lower()
    video_format = EpisodeFormat.Subtitled

    if video_format_str == 'dubbed':
        video_format = EpisodeFormat.Dubbed
    elif video_format_str == 'both':
        video_format = EpisodeFormat.Subtitled | EpisodeFormat.Dubbed

    cache_key = f"video_sources_{anime_id}_{episode_number}_{video_format_str}"
    cached_sources = get_cached_data(cache_key)
    if cached_sources:
        return jsonify(cached_sources)

    with AnimeFLV() as api:
        try:
            print(f"PROCESSING: Getting raw video sources for '{anime_id}' episode {episode_number} (Format: {video_format_str})")
            raw_servers_output = api.get_video_servers(id=anime_id, episode=episode_number, format=video_format)
            
            structured_sources = []
            extracted_urls = []

            # Robustly extract URL strings from various possible return types of get_video_servers
            if isinstance(raw_servers_output, list):
                for item in raw_servers_output:
                    if isinstance(item, list):
                        for url_val in item:
                            if isinstance(url_val, str): extracted_urls.append(url_val)
                            elif isinstance(url_val, dict) and ('url' in url_val and isinstance(url_val['url'], str)): extracted_urls.append(url_val['url'])
                            elif isinstance(url_val, dict) and ('code' in url_val and isinstance(url_val['code'], str)): extracted_urls.append(url_val['code'])
                            else: print(f"WARNING: Nested list item in raw_servers_output not str/dict with url/code: Type={type(url_val)}, Value={url_val}")
                    elif isinstance(item, str):
                        extracted_urls.append(item)
                    elif isinstance(item, dict):
                        if 'code' in item and isinstance(item['code'], str): extracted_urls.append(item['code'])
                        elif 'url' in item and isinstance(item['url'], str): extracted_urls.append(item['url'])
                        else: print(f"WARNING: Dictionary item in raw_servers_output has no valid 'code' or 'url' field: {item}")
                    else:
                        print(f"WARNING: Unexpected item type in top-level list raw_servers_output: Type={type(item)}, Value={item}")
            elif isinstance(raw_servers_output, dict):
                for key, value in raw_servers_output.items():
                    if isinstance(value, list):
                        for url_val in value:
                            if isinstance(url_val, str): extracted_urls.append(url_val)
                            elif isinstance(url_val, dict) and ('url' in url_val and isinstance(url_val['url'], str)): extracted_urls.append(url_val['url'])
                            elif isinstance(url_val, dict) and ('code' in url_val and isinstance(url_val['code'], str)): extracted_urls.append(url_val['code'])
                            else: print(f"WARNING: List item in dict value not str/dict with url/code: Type={type(url_val)}, Value={url_val}")
                    elif isinstance(value, str): extracted_urls.append(value)
                    elif isinstance(value, dict):
                         if 'code' in value and isinstance(value['code'], str): extracted_urls.append(value['code'])
                         elif 'url' in value and isinstance(value['url'], str): extracted_urls.append(value['url'])
                         else: print(f"WARNING: Dict value in dict has no valid 'code' or 'url' field: {value}")
                    else:
                        print(f"WARNING: Unexpected type in dict value for key {key}: Type={type(value)}, Value={value}")
            else:
                print(f"WARNING: Top-level raw_servers_output is neither list nor dict: Type={type(raw_servers_output)}, Value={raw_servers_output}")

            # Now categorize the extracted pure URLs
            for url in extracted_urls:
                if isinstance(url, str) and url.strip():
                    source_type = categorize_video_source(url)
                    structured_sources.append({
                        "type": source_type,
                        "url": url
                    })
                else:
                    print(f"WARNING: Extracted non-string or empty URL found: Type={type(url)}, Value={url}")

            serializable_sources = {"sources": structured_sources}
            set_cached_data(cache_key, serializable_sources)
            return jsonify(serializable_sources)
        except CloudflareChallengeError:
            print(f"ERROR: Cloudflare challenge encountered for video sources '{anime_id}' episode {episode_number}.")
            return jsonify({"error": "Cloudflare challenge detected. Unable to bypass for this request. Streaming might be temporarily unavailable.", "details": "The target website is actively challenging the scraper."}), 503
        except Exception as e:
            print(f"ERROR: Failed to get video sources for '{anime_id}' episode {episode_number}: {e}")
            return jsonify({"error": f"Internal server error during video source retrieval: {str(e)}", "details": "The episode might not exist, or the site structure for video sources has changed."}), 500

@app.route('/api/latest-episodes', methods=['GET'])
def get_latest_episodes_endpoint():
    cache_key = "latest_episodes"
    cached_episodes = get_cached_data(cache_key)
    if cached_episodes:
        return jsonify(cached_episodes)

    with AnimeFLV() as api:
        try:
            print("PROCESSING: Getting latest episodes...")
            episodes = api.get_latest_episodes()
            serializable_episodes = [
                {
                    "id": ep.id,
                    "anime": ep.anime,
                    "image_preview": ep.image_preview
                } for ep in episodes
            ]
            set_cached_data(cache_key, serializable_episodes)
            return jsonify(serializable_episodes)
        except CloudflareChallengeError:
            print("ERROR: Cloudflare challenge encountered during latest episodes retrieval.")
            return jsonify({"error": "Cloudflare challenge detected. Unable to bypass for this request. Please try again later.", "details": "The target website is actively challenging the scraper."}), 503
        except Exception as e:
            print(f"ERROR: Failed to get latest episodes: {e}")
            return jsonify({"error": f"Internal server error during latest episodes retrieval: {str(e)}", "details": "The section might be empty or the site structure has changed."}), 500

@app.route('/api/latest-animes', methods=['GET'])
def get_latest_animes_endpoint():
    cache_key = "latest_animes"
    cached_animes = get_cached_data(cache_key)
    if cached_animes:
        return jsonify(cached_animes)

    with AnimeFLV() as api:
        try:
            print("PROCESSING: Getting latest animes...")
            animes = api.get_latest_animes()
            serializable_animes = [
                {
                    "id": anime.id,
                    "title": anime.title,
                    "poster": anime.poster,
                    "banner": anime.banner,
                    "synopsis": anime.synopsis,
                    "rating": anime.rating,
                    "genres": anime.genres,
                    "debut": anime.debut,
                    "type": anime.type
                } for anime in animes
            ]
            set_cached_data(cache_key, serializable_animes)
            return jsonify(serializable_animes)
        except CloudflareChallengeError:
            print("ERROR: Cloudflare challenge encountered during latest animes retrieval.")
            return jsonify({"error": "Cloudflare challenge detected. Unable to bypass for this request. Please try again later.", "details": "The target website is actively challenging the scraper."}), 503
        except Exception as e:
            print(f"ERROR: Failed to get latest animes: {e}")
            return jsonify({"error": f"Internal server error during latest animes retrieval: {str(e)}", "details": "The section might be empty or the site structure has changed."}), 500


if __name__ == '__main__':
    app.run(debug=True, port=5000)
