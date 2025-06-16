# AnimeFLV API Backend

This is a Flask API that scrapes anime information and streaming links from animeflv.net.

## Endpoints:
- `/api/search?query=...`
- `/api/anime-info/<anime_id>`
- `/api/video-sources/<anime_id>/<episode_number>`
- `/api/latest-episodes`
- `/api/latest-animes`

## Setup (Local Development):
1. Clone this repository.
2. Create and activate a Python virtual environment:
   `python -m venv .venv`
   `.\.venv\Scripts\Activate.ps1` (Windows PowerShell)
3. Install dependencies:
   `pip install -r requirements.txt`
4. Run the Flask app:
   `python app.py`