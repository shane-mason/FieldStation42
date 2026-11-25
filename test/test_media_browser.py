from fs42.fs42_server.api import media_browser


def test_media_browser_libraries_accept_named_rows_and_shorthand():
    station = {
        "media_browser": {
            "movies": [
                {"title": "Classics", "path": "catalog/movies/classics"},
                "catalog/movies/new",
            ],
            "shows": [{"title": "Series", "path": "catalog/shows"}],
        }
    }

    assert media_browser.configured_libraries(station) == [
        {
            "id": "movies-0",
            "kind": "movies",
            "title": "Classics",
            "path": "catalog/movies/classics",
        },
        {
            "id": "movies-1",
            "kind": "movies",
            "title": "Movies",
            "path": "catalog/movies/new",
        },
        {
            "id": "shows-0",
            "kind": "shows",
            "title": "Series",
            "path": "catalog/shows",
        },
    ]


def test_movie_and_show_scanning(tmp_path):
    movie_root = tmp_path / "movies"
    movie_root.mkdir()
    (movie_root / "Example Movie (2026).mp4").write_bytes(b"")

    show_root = tmp_path / "shows"
    season = show_root / "Example Show" / "Season 1"
    season.mkdir(parents=True)
    (season / "Example Show S01E02.mkv").write_bytes(b"")
    (season / "Example Show S01E01.mkv").write_bytes(b"")

    movie_library = {
        "id": "movies-0",
        "kind": "movies",
        "title": "Movies",
        "path": str(movie_root),
    }
    show_library = {
        "id": "shows-0",
        "kind": "shows",
        "title": "TV Shows",
        "path": str(show_root),
    }

    movies = media_browser.scan_movie_library(44, movie_library)
    shows = media_browser.scan_show_library(44, show_library)

    assert [movie["title"] for movie in movies] == ["Example Movie (2026)"]
    assert [show["title"] for show in shows] == ["Example Show"]
    assert shows[0]["seasons"][0]["number"] == 1
    assert [episode["episode"] for episode in shows[0]["seasons"][0]["episodes"]] == [1, 2]


def test_movie_item_defers_tmdb_lookup(tmp_path):
    movie = tmp_path / "Local Filename (2026).mp4"
    movie.write_bytes(b"")
    library = {
        "id": "movies-0",
        "kind": "movies",
        "title": "Movies",
        "path": str(tmp_path),
    }

    item = media_browser._media_item(str(movie), 44, library)

    assert item["title"] == "Local Filename (2026)"
    assert item["tmdb_query"] == "Local Filename (2026)"
    assert item["image_url"] is None
    assert "tmdb_id" not in item


def test_tmdb_endpoint_returns_movie_metadata(monkeypatch):
    class FakeStationManager:
        @staticmethod
        def station_by_channel(channel_number):
            assert channel_number == 44
            return {"channel_number": 44}

    class FakeTMDB:
        @staticmethod
        def is_configured():
            return True

        @staticmethod
        def search_movie(title):
            assert title == "Example Movie (2026)"
            return {
                "tmdb_id": 42,
                "title": "Example Movie",
                "overview": "Metadata supplied by TMDB.",
                "release_date": "2026-04-03",
                "poster_url": "https://image.tmdb.org/t/p/w500/example.jpg",
                "vote_average": 7.5,
            }

    monkeypatch.setattr(media_browser, "StationManager", FakeStationManager)
    monkeypatch.setattr(media_browser, "get_tmdb_helper", lambda: FakeTMDB())

    response = media_browser.get_tmdb_metadata(44, "Example Movie (2026)")

    assert response["configured"] is True
    assert response["movie"]["title"] == "Example Movie"
    assert response["movie"]["vote_average"] == 7.5
