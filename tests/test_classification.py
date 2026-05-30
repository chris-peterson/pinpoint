from pathlib import Path

from pinpoint.defaults import parse_artists
from pinpoint.discovery import infer_root, _exif_capture_date, _filename_date


def test_single_artist_no_feat():
    assert parse_artists(["Pink Floyd"]) == ("Pink Floyd", [])


def test_feat_marker_in_one_string():
    assert parse_artists(["Jay-Z feat. Alicia Keys"]) == ("Jay-Z", ["Alicia Keys"])


def test_ft_abbreviation():
    assert parse_artists(["Drake ft. Rihanna"]) == ("Drake", ["Rihanna"])


def test_feat_in_parens():
    assert parse_artists(["Drake (feat. Rihanna)"]) == ("Drake", ["Rihanna"])


def test_multiple_featured_after_marker():
    primary, feats = parse_artists(["Calvin Harris feat. Pharrell, Katy Perry & Big Sean"])
    assert primary == "Calvin Harris"
    assert feats == ["Pharrell", "Katy Perry", "Big Sean"]


def test_multiple_frames_primary_plus_feat():
    assert parse_artists(["Eminem", "Dido"]) == ("Eminem", ["Dido"])


def test_band_name_with_ampersand_not_split():
    # Without a feat marker the primary is never split — band names stay whole.
    assert parse_artists(["Earth, Wind & Fire"]) == ("Earth, Wind & Fire", [])


def test_featured_dedup_against_primary():
    primary, feats = parse_artists(["Drake feat. Drake"])
    assert primary == "Drake"
    assert feats == []


def test_infer_image_is_memory():
    assert infer_root(Path("/x/photo.jpg"), "image") == "memory"


def test_infer_audio_is_music():
    assert infer_root(Path("/x/song.mp3"), "audio") == "music"


def test_infer_video_with_episode_is_tv():
    assert infer_root(Path("/x/Show.S01E04.mkv"), "video") == "tv"


def test_infer_video_with_year_is_movie():
    assert infer_root(Path("/x/The Matrix (1999).mp4"), "video") == "movie"


def test_infer_video_ambiguous_is_none():
    assert infer_root(Path("/x/clip.mov"), "video") is None


def test_infer_document_book_extension():
    assert infer_root(Path("/x/novel.epub"), "document") == "book"


def test_infer_unknown_document_is_none():
    assert infer_root(Path("/x/archive.zip"), "document") is None


def test_exif_capture_date_reads_datetimeoriginal(tmp_path):
    from PIL import Image
    from PIL.ExifTags import IFD

    path = tmp_path / "photo.jpg"
    img = Image.new("RGB", (8, 8), (10, 20, 30))
    exif = img.getexif()
    exif.get_ifd(IFD.Exif)[36867] = "2025:01:15 10:30:00"
    img.save(str(path), "JPEG", exif=exif.tobytes())

    assert _exif_capture_date(path) == "2025-01-15"


def test_exif_capture_date_none_without_exif(tmp_path):
    from PIL import Image

    path = tmp_path / "plain.png"
    Image.new("RGB", (8, 8), (10, 20, 30)).save(str(path), "PNG")

    assert _exif_capture_date(path) is None


def test_filename_date_hyphenated():
    assert _filename_date(Path("/x/screenshot_2025-03-01.png")) == "2025-03-01"


def test_filename_date_compact():
    assert _filename_date(Path("/x/IMG_20250115_103000.jpg")) == "2025-01-15"


def test_filename_date_dotted():
    assert _filename_date(Path("/x/2024.12.20 party.mp4")) == "2024-12-20"


def test_filename_date_bare_year_month():
    assert _filename_date(Path("/x/PXL_2025-06.jpg")) == "2025-06-01"


def test_filename_date_rejects_implausible():
    # 99 is not a month — not a date.
    assert _filename_date(Path("/x/order-2025-99-01.jpg")) is None


def test_filename_date_ignores_plain_name():
    assert _filename_date(Path("/x/vacation_sunset.jpg")) is None
