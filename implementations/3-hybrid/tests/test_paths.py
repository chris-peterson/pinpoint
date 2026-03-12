from pinpoint.paths import derive_path


def test_memory_no_tags():
    result = derive_path("memory", {"month": ["2025-01"]}, "IMG_4521.jpg")
    assert result == "memories/2025-01/IMG_4521.jpg"


def test_memory_event():
    result = derive_path("memory", {"month": ["2025-01"], "event": ["Hawaii Vacation"]}, "IMG_4521.jpg")
    assert result == "memories/2025-01/Hawaii Vacation/IMG_4521.jpg"


def test_memory_nested_event():
    result = derive_path(
        "memory",
        {"month": ["2025-01"], "event": ["Hawaii Vacation:Snorkeling"]},
        "IMG_4521.jpg",
    )
    assert result == "memories/2025-01/Hawaii Vacation/Snorkeling/IMG_4521.jpg"


def test_memory_name():
    result = derive_path("memory", {"month": ["2025-01"], "name": ["Sunset Over Ocean"]}, "IMG_4521.jpg")
    assert result == "memories/2025-01/Sunset Over Ocean.jpg"


def test_memory_event_and_name():
    result = derive_path(
        "memory",
        {"month": ["2025-01"], "event": ["Hawaii Vacation:Snorkeling"], "name": ["Sunset Over Ocean"]},
        "IMG_4521.jpg",
    )
    assert result == "memories/2025-01/Hawaii Vacation/Snorkeling/Sunset Over Ocean.jpg"


def test_music_full():
    result = derive_path(
        "music",
        {"artist": ["Pink Floyd"], "album": ["Dark Side of the Moon"], "year": ["1973"], "track": ["01"], "name": ["Time"]},
        "time.flac",
    )
    assert result == "music/Pink Floyd/[1973] Dark Side of the Moon/01 - Time.flac"


def test_music_no_album():
    result = derive_path("music", {"artist": ["Pink Floyd"], "name": ["Another Brick"]}, "another.mp3")
    assert result == "music/Pink Floyd/Another Brick.mp3"


def test_music_no_tags():
    result = derive_path("music", {}, "track-01.mp3")
    assert result == "music/_unknown/track-01.mp3"


def test_movie_with_year():
    result = derive_path("movie", {"name": ["The Dark Knight"], "year": ["2008"]}, "movie.mkv")
    assert result == "movies/The Dark Knight [2008].mkv"


def test_movie_with_series():
    result = derive_path(
        "movie",
        {"series": ["Indiana Jones"], "name": ["Raiders of the Lost Ark"], "year": ["1981"]},
        "movie.mkv",
    )
    assert result == "movies/Indiana Jones/Raiders of the Lost Ark [1981].mkv"


def test_movie_no_tags():
    result = derive_path("movie", {}, "movie.mkv")
    assert result == "movies/movie.mkv"


def test_tv_full():
    result = derive_path(
        "tv",
        {"show": ["The Office"], "season": ["03"], "episode": ["05"], "name": ["The Merger"]},
        "episode.mkv",
    )
    assert result == "tv/The Office/Season 03/05 - The Merger.mkv"


def test_podcast_full():
    result = derive_path(
        "podcast",
        {"show": ["Hardcore History"], "episode": ["66"], "name": ["Supernova in the East"]},
        "episode.mp3",
    )
    assert result == "podcast/Hardcore History/66 - Supernova in the East.mp3"


def test_book_with_series():
    result = derive_path(
        "book",
        {"author": ["Tolkien"], "series": ["Middle Earth"], "name": ["The Hobbit"]},
        "book.m4a",
    )
    assert result == "books/Tolkien/Middle Earth/The Hobbit.m4a"


def test_comedy_full():
    result = derive_path(
        "comedy",
        {"artist": ["John Mulaney"], "name": ["Kid Gorgeous"], "year": ["2018"]},
        "special.mp4",
    )
    assert result == "comedy/John Mulaney/[2018] Kid Gorgeous.mp4"
