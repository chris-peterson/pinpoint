from pinpoint.paths import derive_path


def test_memory_no_tags():
    assert derive_path("memory", {"month": ["2025-01"]}, "IMG_4521.jpg") == "memories/2025-01/IMG_4521.jpg"


def test_memory_with_event():
    tags = {"month": ["2025-01"], "event": ["Hawaii Vacation"]}
    assert derive_path("memory", tags, "IMG_4521.jpg") == "memories/2025-01/Hawaii Vacation/IMG_4521.jpg"


def test_memory_nested_event():
    tags = {"month": ["2025-01"], "event": ["Hawaii Vacation:Snorkeling"]}
    assert derive_path("memory", tags, "IMG_4521.jpg") == "memories/2025-01/Hawaii Vacation/Snorkeling/IMG_4521.jpg"


def test_memory_with_name():
    tags = {"month": ["2025-01"], "name": ["Sunset Over Ocean"]}
    assert derive_path("memory", tags, "IMG_4521.jpg") == "memories/2025-01/Sunset Over Ocean.jpg"


def test_memory_event_and_name():
    tags = {"month": ["2025-01"], "event": ["Hawaii Vacation:Snorkeling"], "name": ["Sunset Over Ocean"]}
    assert derive_path("memory", tags, "IMG_4521.jpg") == "memories/2025-01/Hawaii Vacation/Snorkeling/Sunset Over Ocean.jpg"


def test_music_full():
    tags = {"artist": ["Pink Floyd"], "album": ["Dark Side of the Moon"], "year": ["1973"], "track": ["01"], "name": ["Time"]}
    assert derive_path("music", tags, "track.flac") == "music/Pink Floyd/[1973] Dark Side of the Moon/01 - Time.flac"


def test_music_no_album():
    tags = {"artist": ["Pink Floyd"], "name": ["Another Brick"]}
    assert derive_path("music", tags, "track.mp3") == "music/Pink Floyd/Another Brick.mp3"


def test_music_no_artist():
    tags = {"name": ["Mystery Track"]}
    assert derive_path("music", tags, "track.mp3") == "music/_unknown/Mystery Track.mp3"


def test_music_no_tags():
    assert derive_path("music", {}, "track-01.mp3") == "music/_unknown/track-01.mp3"


def test_movie_with_year():
    tags = {"name": ["The Dark Knight"], "year": ["2008"]}
    assert derive_path("movie", tags, "movie.mkv") == "movies/The Dark Knight [2008].mkv"


def test_movie_with_series():
    tags = {"series": ["Indiana Jones"], "name": ["Raiders of the Lost Ark"], "year": ["1981"]}
    assert derive_path("movie", tags, "movie.mkv") == "movies/Indiana Jones/Raiders of the Lost Ark [1981].mkv"


def test_movie_no_tags():
    assert derive_path("movie", {}, "movie.mkv") == "movies/movie.mkv"


def test_tv_full():
    tags = {"show": ["The Office"], "season": ["03"], "episode": ["05"], "name": ["The Merger"]}
    assert derive_path("tv", tags, "ep.mkv") == "tv/The Office/Season 03/05 - The Merger.mkv"


def test_podcast_full():
    tags = {"show": ["Hardcore History"], "episode": ["66"], "name": ["Supernova in the East"]}
    assert derive_path("podcast", tags, "ep.mp3") == "podcast/Hardcore History/66 - Supernova in the East.mp3"


def test_book_with_series():
    tags = {"author": ["Tolkien"], "series": ["Middle Earth"], "name": ["The Hobbit"]}
    assert derive_path("book", tags, "book.m4a") == "books/Tolkien/Middle Earth/The Hobbit.m4a"


def test_comedy_full():
    tags = {"artist": ["John Mulaney"], "name": ["Kid Gorgeous"], "year": ["2018"]}
    assert derive_path("comedy", tags, "special.mp4") == "comedy/John Mulaney/[2018] Kid Gorgeous.mp4"
