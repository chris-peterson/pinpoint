"""Tests for output path derivation — the core contract."""

from datetime import date
from pathlib import PurePosixPath

from pinpoint.paths import derive_path


class TestMemories:
    def test_no_tags(self):
        result = derive_path("memories", {}, "IMG_4521.jpg", date(2025, 1, 15))
        assert result == PurePosixPath("memories/2025-01/IMG_4521.jpg")

    def test_event(self):
        result = derive_path(
            "memories",
            {"event": ["hawaii-vacation"]},
            "IMG_4521.jpg",
            date(2025, 1, 15),
        )
        assert result == PurePosixPath("memories/2025-01/hawaii-vacation/IMG_4521.jpg")

    def test_nested_event(self):
        result = derive_path(
            "memories",
            {"event": ["hawaii-vacation:snorkeling"]},
            "IMG_4521.jpg",
            date(2025, 1, 15),
        )
        assert result == PurePosixPath(
            "memories/2025-01/hawaii-vacation/snorkeling/IMG_4521.jpg"
        )

    def test_name(self):
        result = derive_path(
            "memories",
            {"name": ["sunset-over-ocean"]},
            "IMG_4521.jpg",
            date(2025, 1, 15),
        )
        assert result == PurePosixPath("memories/2025-01/sunset-over-ocean.jpg")

    def test_event_and_name(self):
        result = derive_path(
            "memories",
            {"event": ["hawaii-vacation:snorkeling"], "name": ["sunset-over-ocean"]},
            "IMG_4521.jpg",
            date(2025, 1, 15),
        )
        assert result == PurePosixPath(
            "memories/2025-01/hawaii-vacation/snorkeling/sunset-over-ocean.jpg"
        )

    def test_no_date(self):
        result = derive_path("memories", {}, "IMG_4521.jpg", None)
        assert result == PurePosixPath("memories/_unknown/IMG_4521.jpg")


class TestMusic:
    def test_full_tags_with_track(self):
        """[OP-3] Track number is zero-padded and prepended to filename."""
        result = derive_path(
            "music",
            {"artist": ["Pink Floyd"], "album": ["Dark Side of the Moon"], "year": ["1973"], "track": ["1"], "name": ["Time"]},
            "track01.flac",
            None,
        )
        assert result == PurePosixPath(
            "music/Pink Floyd/[1973] Dark Side of the Moon/01 Time.flac"
        )

    def test_track_double_digit(self):
        """[OP-3] Double-digit track numbers stay as-is."""
        result = derive_path(
            "music",
            {"artist": ["Pink Floyd"], "album": ["The Wall"], "year": ["1979"], "track": ["12"], "name": ["Another Brick in the Wall"]},
            "track12.flac",
            None,
        )
        assert result == PurePosixPath(
            "music/Pink Floyd/[1979] The Wall/12 Another Brick in the Wall.flac"
        )

    def test_no_track_number(self):
        """Without track tag, no number is prepended."""
        result = derive_path(
            "music",
            {"artist": ["Pink Floyd"], "album": ["Dark Side of the Moon"], "year": ["1973"], "name": ["Time"]},
            "track01.flac",
            None,
        )
        assert result == PurePosixPath(
            "music/Pink Floyd/[1973] Dark Side of the Moon/Time.flac"
        )

    def test_album_without_year(self):
        result = derive_path(
            "music",
            {"artist": ["Pink Floyd"], "album": ["Dark Side of the Moon"], "name": ["Time"]},
            "track01.flac",
            None,
        )
        assert result == PurePosixPath(
            "music/Pink Floyd/Dark Side of the Moon/Time.flac"
        )

    def test_album_with_year_already_in_name(self):
        """If album already starts with [year], don't double-prefix."""
        result = derive_path(
            "music",
            {"artist": ["Pink Floyd"], "album": ["[1973] Dark Side of the Moon"], "year": ["1973"], "name": ["Time"]},
            "track01.flac",
            None,
        )
        assert result == PurePosixPath(
            "music/Pink Floyd/[1973] Dark Side of the Moon/Time.flac"
        )

    def test_artist_and_name(self):
        result = derive_path(
            "music",
            {"artist": ["Pink Floyd"], "name": ["Another Brick"]},
            "song.mp3",
            None,
        )
        assert result == PurePosixPath("music/Pink Floyd/Another Brick.mp3")

    def test_name_only(self):
        result = derive_path(
            "music",
            {"name": ["Mystery Track"]},
            "unknown.mp3",
            None,
        )
        assert result == PurePosixPath("music/_unknown/Mystery Track.mp3")

    def test_no_tags(self):
        result = derive_path("music", {}, "track-01.mp3", None)
        assert result == PurePosixPath("music/_unknown/track-01.mp3")

    def test_various_artists_compilation(self):
        """[OP-4] Various Artists compilations preserve original filename (no track prepend)."""
        result = derive_path(
            "music",
            {
                "artist": ["Various Artists"],
                "album": ["8 Mile Music From and Inspired by the Motion Picture"],
                "year": ["2002"],
                "track": ["15"],
                "name": ["15 - Gang Starr - Battle"],
            },
            "15 - Gang Starr - Battle.mp3",
            None,
        )
        assert result == PurePosixPath(
            "music/Various Artists/[2002] 8 Mile Music From and Inspired by the Motion Picture/15 - Gang Starr - Battle.mp3"
        )


class TestBooks:
    def test_full_tags(self):
        result = derive_path(
            "books",
            {"author": ["tolkien"], "title": ["the-hobbit"], "name": ["chapter-1"]},
            "audio.m4a",
            None,
        )
        assert result == PurePosixPath("books/tolkien/the-hobbit/chapter-1.m4a")

    def test_author_only(self):
        result = derive_path(
            "books",
            {"author": ["tolkien"]},
            "the-hobbit.m4a",
            None,
        )
        assert result == PurePosixPath("books/tolkien/the-hobbit.m4a")


class TestPodcasts:
    def test_full_tags(self):
        result = derive_path(
            "podcasts",
            {"show": ["hardcore-history"], "name": ["ep-66-supernova-in-the-east"]},
            "episode.mp3",
            None,
        )
        assert result == PurePosixPath(
            "podcasts/hardcore-history/ep-66-supernova-in-the-east.mp3"
        )

    def test_no_tags(self):
        result = derive_path("podcasts", {}, "episode.mp3", None)
        assert result == PurePosixPath("podcasts/_unknown/episode.mp3")


class TestTV:
    def test_full_tags(self):
        result = derive_path(
            "tv",
            {"show": ["the-office"], "season": ["3"], "name": ["the-merger"]},
            "video.mkv",
            None,
        )
        assert result == PurePosixPath("tv/the-office/3/the-merger.mkv")

    def test_show_and_season(self):
        result = derive_path(
            "tv",
            {"show": ["the-office"], "season": ["3"]},
            "episode.mkv",
            None,
        )
        assert result == PurePosixPath("tv/the-office/3/episode.mkv")


class TestMovies:
    def test_standalone(self):
        result = derive_path(
            "movies",
            {"name": ["the-dark-knight [2008]"]},
            "movie.mkv",
            None,
        )
        assert result == PurePosixPath("movies/the-dark-knight [2008].mkv")

    def test_with_series(self):
        result = derive_path(
            "movies",
            {"series": ["indiana-jones"], "name": ["raiders-of-the-lost-ark [1981]"]},
            "movie.mkv",
            None,
        )
        assert result == PurePosixPath(
            "movies/indiana-jones/raiders-of-the-lost-ark [1981].mkv"
        )

    def test_no_tags(self):
        result = derive_path("movies", {}, "movie.mkv", None)
        assert result == PurePosixPath("movies/movie.mkv")


class TestComedy:
    def test_full_tags(self):
        result = derive_path(
            "comedy",
            {"artist": ["john-mulaney"], "name": ["kid-gorgeous [2018]"]},
            "special.mp4",
            None,
        )
        assert result == PurePosixPath(
            "comedy/john-mulaney/kid-gorgeous [2018].mp4"
        )

    def test_artist_only(self):
        result = derive_path(
            "comedy",
            {"artist": ["john-mulaney"]},
            "special.mp4",
            None,
        )
        assert result == PurePosixPath("comedy/john-mulaney/special.mp4")
