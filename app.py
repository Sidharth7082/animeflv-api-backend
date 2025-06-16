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
            print(f"Cache hit for key: {key}")
            return cache[key]['data']
        else:
            print(f"Cache expired for key: {key}")
            del cache[key] # Remove expired item
    print(f"Cache miss for key: {key}")
    return None

def set_cached_data(key, data):
    """Stores data in cache with current timestamp."""
    cache[key] = {'data': data, 'timestamp': time.time()}
    print(f"Data cached for key: {key}")

# --- Helper for Video Source Categorization ---
def categorize_video_source(url):
    """
    Analyzes a video URL and categorizes it as 'direct', 'embed', or 'unknown'.
    Prioritizes embed detection for common providers that use iframe embeds.
    """
    url_lower = url.lower()

    # Common embed patterns
    embed_patterns = [
        r'embed', r'yourupload\.com', r'streamwish\.to', r'streame\.net',
        r'streamtape\.com', r'fembed\.com', r'natu\.moe', r'ok\.ru', r'my\.mail\.ru',
        r'mega\.nz' # Mega links are often direct downloads but their embed can be used in iframes
    ]
    for pattern in embed_patterns:
        if re.search(pattern, url_lower):
            print(f"  Source categorized as 'embed': {url}")
            return "embed"

    # Common direct video extensions (order matters for efficiency)
    direct_patterns = [r'\.mp4', r'\.webm', r'\.ogg', r'\.mkv', r'\.avi', r'\.mov']
    for pattern in direct_patterns:
        if re.search(pattern, url_lower):
            print(f"  Source categorized as 'direct': {url}")
            return "direct"
    
    print(f"  Source categorized as 'unknown': {url}")
    return "unknown" # Fallback for anything not recognized

# --- API Endpoints ---

@app.route('/')
def home():
    """
    Basic home endpoint to confirm the API is running.
    """
    return "<h1>AnimeFLV API Backend is running!</h1><p>Use specific endpoints like /api/search, /api/anime-info, or /api/video-sources.</p>"

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
        return jsonify({"error": "Query parameter 'query' is required."}), 400

    cache_key = f"search_{query}_{page or 'none'}"
    cached_results = get_cached_data(cache_key)
    if cached_results:
        return jsonify(cached_results)

    with AnimeFLV() as api:
        try:
            print(f"Searching for anime: '{query}', Page: {page}")
            results = api.search(query=query, page=page)

            # Convert AnimeInfo objects to dictionaries for JSON serialization
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
            # Handle Cloudflare challenge specifically - often requires manual intervention
            print("Cloudflare challenge encountered during search. Manual intervention or advanced scraper may be needed.")
            return jsonify({"error": "Cloudflare challenge detected. Please try again later or access directly to bypass."}), 503
        except Exception as e:
            print(f"Error during search for '{query}': {e}")
            return jsonify({"error": f"Failed to search for anime: {str(e)}"}), 500

@app.route('/api/anime-info/<string:anime_id>', methods=['GET'])
def get_anime_info_endpoint(anime_id):
    """
    Retrieves detailed information about a specific anime.
    Path parameter:
    - anime_id: The ID of the anime (e.g., "nanatsu-no-taizai").
    """
    if not anime_id:
        return jsonify({"error": "Anime ID is required."}), 400

    cache_key = f"anime_info_{anime_id}"
    cached_info = get_cached_data(cache_key)
    if cached_info:
        return jsonify(cached_info)

    with AnimeFLV() as api:
        try:
            print(f"Getting info for anime ID: '{anime_id}'")
            anime_info = api.get_anime_info(id=anime_id) 
            
            serializable_episodes = []
            if anime_info.episodes:
                for episode in anime_info.episodes:
                    serializable_episodes.append({
                        "id": episode.id,
                        "anime": episode.anime,
                        "image_preview": episode.image_preview
                    })

            # --- Robustness Improvement ---
            # Ensure attributes are not None before accessing .string or other methods
            serializable_info = {
                "id": anime_info.id,
                "title": anime_info.title if anime_info.title else None,
                "poster": anime_info.poster if anime_info.poster else None,
                "banner": anime_info.banner if anime_info.banner else None,
                "synopsis": anime_info.synopsis if anime_info.synopsis else None,
                "rating": anime_info.rating if anime_info.rating else None,
                "genres": anime_info.genres if anime_info.genres else [], # Ensure list if None
                "debut": anime_info.debut if anime_info.debut else None,
                "type": anime_info.type if anime_info.type else None,
                "episodes": serializable_episodes
            }
            set_cached_data(cache_key, serializable_info)
            return jsonify(serializable_info)
        except CloudflareChallengeError:
            print("Cloudflare challenge encountered during anime info retrieval. Manual intervention or advanced scraper may be needed.")
            return jsonify({"error": "Cloudflare challenge detected. Please try again later or access directly to bypass."}), 503
        except Exception as e:
            print(f"Error getting anime info for '{anime_id}': {e}")
            # More specific error message for parsing issues
            return jsonify({"error": f"Failed to get anime info or parse data: {str(e)}. The site structure might have changed."}), 500

@app.route('/api/video-sources/<string:anime_id>/<int:episode_number>', methods=['GET'])
def get_video_sources_endpoint(anime_id, episode_number):
    """
    Gets video streaming/download links for a specific anime episode.
    Path parameters:
    - anime_id: The ID of the anime (e.g., "nanatsu-no-taizai").
    - episode_number: The episode number (e.g., 1).
    Query parameters:
    - format: (Optional) "subtitled" or "dubbed". Defaults to "subtitled".
    """
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
            print(f"Getting raw video sources for '{anime_id}' episode {episode_number} (Format: {video_format_str})")
            raw_servers = api.get_video_servers(id=anime_id, episode=episode_number, format=video_format)
            
            structured_sources = []
            for sublist in raw_servers:
                for raw_url in sublist:
                    source_type = categorize_video_source(raw_url)
                    structured_sources.append({
                        "type": source_type,
                        "url": raw_url
                    })

            serializable_sources = {"sources": structured_sources}
            set_cached_data(cache_key, serializable_sources)
            return jsonify(serializable_sources)
        except CloudflareChallengeError:
            print("Cloudflare challenge encountered during video source retrieval. This endpoint often faces Cloudflare. You may need a more advanced scraper or manual bypass.")
            return jsonify({"error": "Cloudflare challenge detected. This endpoint often faces Cloudflare. You may need a more advanced scraper or manual bypass."}), 503
        except Exception as e:
            print(f"Error getting video sources for '{anime_id}' episode {episode_number}: {e}")
            return jsonify({"error": f"Failed to get video sources: {str(e)}"}), 500

@app.route('/api/latest-episodes', methods=['GET'])
def get_latest_episodes_endpoint():
    cache_key = "latest_episodes"
    cached_episodes = get_cached_data(cache_key)
    if cached_episodes:
        return jsonify(cached_episodes)

    with AnimeFLV() as api:
        try:
            print("Getting latest episodes...")
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
            print("Cloudflare challenge encountered during latest episodes retrieval. Manual intervention or advanced scraper may be needed.")
            return jsonify({"error": "Cloudflare challenge detected. Please try again later or access directly to bypass."}), 503
        except Exception as e:
            print(f"Error getting latest episodes: {e}")
            return jsonify({"error": f"Failed to get latest episodes: {str(e)}"}), 500

@app.route('/api/latest-animes', methods=['GET'])
def get_latest_animes_endpoint():
    cache_key = "latest_animes"
    cached_animes = get_cached_data(cache_key)
    if cached_animes:
        return jsonify(cached_animes)

    with AnimeFLV() as api:
        try:
            print("Getting latest animes...")
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
            print("Cloudflare challenge encountered during latest animes retrieval. Manual intervention or advanced scraper may be needed.")
            return jsonify({"error": "Cloudflare challenge detected. Please try again later or access directly to bypass."}), 503
        except Exception as e:
            print(f"Error getting latest animes: {e}")
            return jsonify({"error": f"Failed to get latest animes: {str(e)}"}), 500


if __name__ == '__main__':
    app.run(debug=True, port=5000)
