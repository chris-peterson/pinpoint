"""Tests for AI analysis modules."""

from pinpoint.analysis.tmdb import parse_media_filename
from pinpoint.analysis.vision import _parse_vision_response


class TestParseMediaFilename:
    def test_tv_sxxexx(self):
        result = parse_media_filename("The.Office.S03E05.720p.mkv")
        assert result["title"] == "The Office"
        assert result["season"] == "3"
        assert result["episode"] == "5"

    def test_movie_with_year_parens(self):
        result = parse_media_filename("There Will Be Blood (2007).mp4")
        assert result["title"] == "There Will Be Blood"
        assert result["year"] == "2007"

    def test_movie_with_year_dots(self):
        result = parse_media_filename("John.Mulaney.Kid.Gorgeous.2018.WEBRip.mp4")
        assert result["title"] == "John Mulaney Kid Gorgeous"
        assert result["year"] == "2018"

    def test_movie_no_year(self):
        result = parse_media_filename("Inception.1080p.BluRay.mkv")
        assert result["title"] == "Inception"

    def test_tv_lowercase(self):
        result = parse_media_filename("breaking.bad.s05e16.felina.mkv")
        assert result["title"] == "breaking bad"
        assert result["season"] == "5"
        assert result["episode"] == "16"

    def test_brackets_year(self):
        result = parse_media_filename("The Matrix [1999].mkv")
        assert result["title"] == "The Matrix"
        assert result["year"] == "1999"


class TestParseVisionResponse:
    def test_full_response(self):
        text = """event: beach vacation
people: group of friends swimming
name: sunset at the beach"""
        suggestions = _parse_vision_response(text)
        kinds = {s["kind"]: s["value"] for s in suggestions}
        assert kinds["event"] == "beach vacation"
        assert kinds["person"] == "group of friends swimming"
        assert kinds["name"] == "sunset at the beach"

    def test_no_people(self):
        text = """event: landscape
people: none
name: mountain vista"""
        suggestions = _parse_vision_response(text)
        kinds = {s["kind"]: s["value"] for s in suggestions}
        assert "person" not in kinds
        assert kinds["event"] == "landscape"
        assert kinds["name"] == "mountain vista"

    def test_empty_response(self):
        suggestions = _parse_vision_response("")
        assert suggestions == []
