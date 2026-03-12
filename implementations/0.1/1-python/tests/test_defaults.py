"""Tests for default tag derivation — slugify, Title Case, and source splitting."""

from pinpoint.defaults import defaults_from_source_split, slugify, title_case


class TestSlugify:
    def test_basic(self):
        assert slugify("pink floyd") == "Pink Floyd"

    def test_underscores(self):
        assert slugify("dark_side_of_the_moon") == "Dark Side of the Moon"

    def test_minor_words_lowercase(self):
        assert slugify("lord of the rings") == "Lord of the Rings"

    def test_first_word_always_capitalized(self):
        assert slugify("the wall") == "The Wall"

    def test_already_hyphenated(self):
        assert slugify("kid-gorgeous") == "Kid Gorgeous"

    def test_strips_junk(self):
        assert slugify("  hello   world  ") == "Hello World"

    def test_numbers(self):
        assert slugify("ep 66 supernova in the east") == "Ep 66 Supernova in the East"

    def test_apostrophes(self):
        assert slugify("don't look back in anger") == "Don't Look Back in Anger"
        assert slugify("it's a beautiful day") == "It's a Beautiful Day"

    def test_possessive(self):
        assert slugify("sgt. pepper's lonely hearts club band") == "Sgt. Pepper's Lonely Hearts Club Band"

    def test_parentheses(self):
        assert slugify("Life's On The Line (Bonus Track)") == "Life's on the Line (Bonus Track)"


class TestTitleCase:
    def test_minor_words(self):
        assert title_case("lord of the rings") == "Lord of the Rings"

    def test_first_last_always_capped(self):
        assert title_case("the hobbit") == "The Hobbit"
        assert title_case("back to the") == "Back to The"


class TestDefaultsSplit:
    def test_music_filename_defaults(self):
        """Filename defaults come from folder structure, not metadata."""
        fn, meta = defaults_from_source_split(
            "/music/Pink Floyd/Dark Side/01 - Time.mp3",
            "music",
            "/music",
        )
        assert fn["artist"] == "Pink Floyd"
        assert fn["album"] == "Dark Side"
        assert fn["name"] == "Time"  # track number stripped
        # meta depends on actual file, but for non-existent file returns empty
        assert isinstance(meta, dict)

    def test_memories_no_metadata(self):
        """Memories root should have no metadata defaults."""
        fn, meta = defaults_from_source_split(
            "/photos/vacation/IMG001.jpg",
            "memories",
            "/photos",
        )
        assert fn["event"] == "Vacation"
        assert fn["name"] == "Img001"  # slugify Title Cases
        assert meta == {}
