"""
TMDB (The Movie Database) API helper for fetching movie metadata.
"""
import requests
import logging
import json
from typing import Optional, Dict, Any
from pathlib import Path
from fs42.station_manager import StationManager

logger = logging.getLogger("TMDB_Helper")

# TMDB API configuration
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"
TMDB_MOVIE_GENRES = {
    12: "Adventure",
    14: "Fantasy",
    16: "Animation",
    18: "Drama",
    27: "Horror",
    28: "Action",
    35: "Comedy",
    36: "History",
    37: "Western",
    53: "Thriller",
    80: "Crime",
    99: "Documentary",
    878: "Science Fiction",
    9648: "Mystery",
    10402: "Music",
    10749: "Romance",
    10751: "Family",
    10752: "War",
    10770: "TV Movie",
}

# Cache directory for TMDB results
CACHE_DIR = Path("catalog/.tmdb_cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)


class TMDBHelper:
    """Helper class for fetching movie metadata from TMDB."""

    def __init__(self, api_key: Optional[str] = None):

        if api_key:
            self.api_key = api_key
        else:
            # Get API key from StationManager's server_conf (loaded from main_config.json)
            station_manager = StationManager()
            self.api_key = station_manager.server_conf.get("tmdb_api_key", "")

        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json"
        })

    def is_configured(self) -> bool:
        """Check if TMDB API key is configured."""
        return bool(self.api_key)

    def _parse_title_and_year(self, filename: str) -> tuple[str, Optional[int]]:
        """
        Parse filename to extract clean title and optional year.

        Supports formats:
        - Movie Title (1983)
        - Movie_Title_1983
        - Movie-Title-1983
        - Movie.Title.1983

        Args:
            filename: Raw filename without extension

        Returns:
            Tuple of (clean_title, year) where year is None if not found
        """
        import re

        # First, try to extract year from parentheses: "Movie Title (1983)"
        year_match = re.search(r'\((\d{4})\)', filename)
        year = None
        clean_filename = filename

        if year_match:
            year = int(year_match.group(1))
            # Remove the year part from filename
            clean_filename = re.sub(r'\s*\(\d{4}\)\s*', ' ', filename)
        else:
            # Try to find 4-digit year at the end: "Movie_Title_1983"
            year_match = re.search(r'[_\-\.\s](\d{4})$', filename)
            if year_match:
                year = int(year_match.group(1))
                # Remove the year from filename
                clean_filename = re.sub(r'[_\-\.\s]\d{4}$', '', filename)

        # Normalize separators: replace underscores, dashes, dots with spaces
        clean_title = re.sub(r'[_\-\.]+', ' ', clean_filename)

        # Clean up extra whitespace
        clean_title = ' '.join(clean_title.split())

        return clean_title, year

    def _get_cache_path(self, title: str) -> Path:
        """Get cache file path for a given title."""
        # Sanitize title for filename
        safe_title = "".join(c if c.isalnum() or c in (' ', '_', '-') else '_' for c in title)
        return CACHE_DIR / f"{safe_title}.json"

    def _load_from_cache(self, title: str) -> Optional[Dict[str, Any]]:
        """Load cached TMDB data for a title."""
        cache_path = self._get_cache_path(title)
        if cache_path.exists():
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    logger.info(f"Loaded TMDB data from cache for '{title}'")
                    return data
            except Exception as e:
                logger.warning(f"Failed to load cache for '{title}': {e}")
        return None

    def _save_to_cache(self, title: str, data: Dict[str, Any]):
        """Save TMDB data to cache."""
        cache_path = self._get_cache_path(title)
        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            logger.info(f"Saved TMDB data to cache for '{title}'")
        except Exception as e:
            logger.warning(f"Failed to save cache for '{title}': {e}")

    def search_movie(self, title: str) -> Optional[Dict[str, Any]]:

        if not self.is_configured():
            logger.warning("TMDB API key not configured, skipping search")
            return None

        # Parse title to extract year if present
        clean_title, year = self._parse_title_and_year(title)

        # Check cache first (using original title as cache key)
        cached = self._load_from_cache(title)
        if cached:
            if "genres" not in cached and cached.get("tmdb_id"):
                details = self.get_movie_details(cached["tmdb_id"])
                if details:
                    cached["genres"] = [
                        genre["name"]
                        for genre in details.get("genres", [])
                        if isinstance(genre, dict) and genre.get("name")
                    ]
                    self._save_to_cache(title, cached)
            return cached

        # Search TMDB
        try:
            search_url = f"{TMDB_BASE_URL}/search/movie"
            params = {
                "api_key": self.api_key,
                "query": clean_title,
                "language": "en-US",
                "page": 1
            }

            # Add year parameter if we found one in the filename
            if year:
                params["year"] = year
                logger.info(f"Searching TMDB for '{clean_title}' ({year})")
            else:
                logger.info(f"Searching TMDB for '{clean_title}'")

            response = self.session.get(search_url, params=params, timeout=5)
            response.raise_for_status()

            data = response.json()
            results = data.get("results", [])

            if not results:
                logger.info(f"No TMDB results found for '{clean_title}'" + (f" ({year})" if year else ""))
                return None

            # Get the first (best) match
            movie = results[0]

            # Extract relevant data
            movie_data = {
                "tmdb_id": movie.get("id"),
                "title": movie.get("title"),
                "original_title": movie.get("original_title"),
                "overview": movie.get("overview", ""),
                "release_date": movie.get("release_date", ""),
                "poster_path": movie.get("poster_path"),
                "poster_url": f"{TMDB_IMAGE_BASE_URL}{movie.get('poster_path')}" if movie.get("poster_path") else None,
                "backdrop_path": movie.get("backdrop_path"),
                "vote_average": movie.get("vote_average"),
                "popularity": movie.get("popularity"),
                "genres": [
                    TMDB_MOVIE_GENRES[genre_id]
                    for genre_id in movie.get("genre_ids", [])
                    if genre_id in TMDB_MOVIE_GENRES
                ],
            }

            # Save to cache
            self._save_to_cache(title, movie_data)

            logger.info(f"Found TMDB match for '{title}': {movie_data['title']} ({movie_data['release_date'][:4] if movie_data['release_date'] else 'N/A'})")

            return movie_data

        except requests.exceptions.RequestException as e:
            logger.error(f"TMDB API request failed for '{title}': {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error searching TMDB for '{title}': {e}")
            return None

    def search_media(self, title: str, media_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Search TMDB for the best matching movie or television show."""
        if not self.is_configured():
            logger.warning("TMDB API key not configured, skipping media search")
            return None

        clean_title, year = self._parse_title_and_year(title)
        try:
            response = self.session.get(
                f"{TMDB_BASE_URL}/search/multi",
                params={
                    "api_key": self.api_key,
                    "query": clean_title,
                    "language": "en-US",
                    "page": 1,
                    "include_adult": False,
                },
                timeout=5,
            )
            response.raise_for_status()
            results = [
                item
                for item in response.json().get("results", [])
                if item.get("media_type") in {"movie", "tv"}
                and (media_type is None or item.get("media_type") == media_type)
            ]
            if year:
                year_matches = [
                    item
                    for item in results
                    if str(
                        item.get("release_date")
                        or item.get("first_air_date")
                        or ""
                    ).startswith(str(year))
                ]
                if year_matches:
                    results = year_matches
            if not results:
                return None

            match = results[0]
            media_type = match["media_type"]
            return {
                "tmdb_id": match.get("id"),
                "media_type": media_type,
                "title": match.get("title") if media_type == "movie" else match.get("name"),
                "original_title": (
                    match.get("original_title")
                    if media_type == "movie"
                    else match.get("original_name")
                ),
                "overview": match.get("overview", ""),
                "release_date": (
                    match.get("release_date")
                    if media_type == "movie"
                    else match.get("first_air_date")
                ),
                "poster_url": (
                    f"{TMDB_IMAGE_BASE_URL}{match.get('poster_path')}"
                    if match.get("poster_path")
                    else None
                ),
                "vote_average": match.get("vote_average"),
            }
        except requests.exceptions.RequestException as exc:
            logger.error("TMDB media search failed for '%s': %s", title, exc)
            return None
        except Exception as exc:
            logger.error("Unexpected TMDB media search error for '%s': %s", title, exc)
            return None

    def get_movie_details(self, tmdb_id: int) -> Optional[Dict[str, Any]]:

        if not self.is_configured():
            return None

        try:
            details_url = f"{TMDB_BASE_URL}/movie/{tmdb_id}"
            params = {
                "api_key": self.api_key,
                "language": "en-US"
            }

            response = self.session.get(details_url, params=params, timeout=5)
            response.raise_for_status()

            return response.json()

        except Exception as e:
            logger.error(f"Failed to get TMDB details for ID {tmdb_id}: {e}")
            return None

    def get_tv_details(self, tmdb_id: int) -> Optional[Dict[str, Any]]:
        if not self.is_configured():
            return None
        try:
            response = self.session.get(
                f"{TMDB_BASE_URL}/tv/{tmdb_id}",
                params={
                    "api_key": self.api_key,
                    "language": "en-US",
                    "append_to_response": "content_ratings",
                },
                timeout=5,
            )
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            logger.error("Failed to get TMDB TV details for ID %s: %s", tmdb_id, exc)
            return None

    def download_poster(self, poster_path: str) -> Optional[bytes]:
        if not poster_path or not poster_path.startswith("/"):
            return None
        try:
            response = self.session.get(
                f"{TMDB_IMAGE_BASE_URL}{poster_path}",
                timeout=15,
            )
            response.raise_for_status()
            if not response.headers.get("content-type", "").lower().startswith("image/"):
                return None
            if len(response.content) > 15 * 1024 * 1024:
                logger.error("TMDB poster is larger than the 15 MB limit")
                return None
            return response.content
        except Exception as exc:
            logger.error("Failed to download TMDB poster %s: %s", poster_path, exc)
            return None


# Global instance
_tmdb_helper = None


def get_tmdb_helper() -> TMDBHelper:
    """Get or create global TMDB helper instance."""
    global _tmdb_helper
    if _tmdb_helper is None:
        _tmdb_helper = TMDBHelper()
    return _tmdb_helper
