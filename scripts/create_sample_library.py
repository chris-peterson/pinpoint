#!/usr/bin/env python3
"""Populate a sample library's _input/ tree with real files across all roots.

Files have real metadata (EXIF for images, ID3 for MP3, Vorbis for FLAC) and are
written into <library>/_input/<root>/ — the same drop tree the running server
watches — so the first run exercises the full discovery → defaults → path
derivation → import pipeline. A few files are dropped directly in _input/ to
exercise content-based root inference and the _stuck fallback.

Usage:
    uv run python scripts/create_sample_library.py [--output /path/to/library]

Default output: ./sample_output/ (matches config.yaml's `library:`)
"""

from __future__ import annotations

import argparse
import wave
from pathlib import Path


def _ensure_pillow():
    from PIL import Image
    from PIL.ExifTags import Base as ExifBase
    return Image, ExifBase


def _ensure_mutagen():
    import mutagen
    from mutagen.id3 import ID3, TALB, TDRC, TIT2, TPE1, TPE2, TRCK
    from mutagen.flac import FLAC
    from mutagen.mp4 import MP4
    return mutagen, ID3, TALB, TDRC, TIT2, TPE1, TPE2, TRCK, FLAC, MP4


def create_jpeg(path: Path, width: int = 64, height: int = 64,
                color: tuple = (100, 149, 237),
                exif_date: str | None = None) -> None:
    """Create a minimal JPEG with optional EXIF DateTimeOriginal."""
    Image, ExifBase = _ensure_pillow()
    img = Image.new("RGB", (width, height), color)
    path.parent.mkdir(parents=True, exist_ok=True)

    if exif_date:
        from PIL.ExifTags import IFD
        exif = img.getexif()
        exif_ifd = exif.get_ifd(IFD.Exif)
        # 36867 = DateTimeOriginal, 36868 = DateTimeDigitized
        exif_ifd[36867] = exif_date
        exif_ifd[36868] = exif_date
        img.save(str(path), "JPEG", exif=exif.tobytes())
    else:
        img.save(str(path), "JPEG")


def create_png(path: Path, width: int = 64, height: int = 64,
               color: tuple = (100, 149, 237)) -> None:
    """Create a minimal PNG."""
    Image, _ = _ensure_pillow()
    img = Image.new("RGB", (width, height), color)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(path), "PNG")


def create_wav(path: Path, duration_s: float = 0.1, sample_rate: int = 8000) -> None:
    """Create a minimal WAV file (silence)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    n_frames = int(sample_rate * duration_s)
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * n_frames)


def create_mp3(path: Path, *, artist: str = "", album: str = "",
               title: str = "", track: str = "", year: str = "",
               albumartist: str = "") -> None:
    """Create a minimal MP3 with ID3 tags via ffmpeg + mutagen."""
    path.parent.mkdir(parents=True, exist_ok=True)

    # Generate a real (tiny) MP3 via ffmpeg from a WAV
    wav_path = path.with_suffix(".wav")
    create_wav(wav_path, duration_s=0.05)

    import subprocess
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(wav_path), "-c:a", "libmp3lame", "-b:a", "32k", str(path)],
            capture_output=True, check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        # No ffmpeg — write a minimal MP3 frame manually
        # MPEG1, Layer 3, 128kbps, 44100Hz, Joint Stereo
        frame_header = b"\xff\xfb\x90\x04"
        frame_data = b"\x00" * 413
        path.write_bytes((frame_header + frame_data) * 3)
    finally:
        wav_path.unlink(missing_ok=True)

    # Add ID3 tags via mutagen
    from mutagen.id3 import ID3, TALB, TDRC, TIT2, TPE1, TPE2, TRCK
    try:
        tags = ID3(str(path))
    except Exception:
        tags = ID3()
    if artist:
        tags.add(TPE1(encoding=3, text=[artist]))
    if albumartist:
        tags.add(TPE2(encoding=3, text=[albumartist]))
    if album:
        tags.add(TALB(encoding=3, text=[album]))
    if title:
        tags.add(TIT2(encoding=3, text=[title]))
    if track:
        tags.add(TRCK(encoding=3, text=[track]))
    if year:
        tags.add(TDRC(encoding=3, text=[year]))
    tags.save(str(path))


def create_flac(path: Path, *, artist: str = "", album: str = "",
                title: str = "", track: str = "", year: str = "") -> None:
    """Create a minimal FLAC with Vorbis comments."""
    path.parent.mkdir(parents=True, exist_ok=True)

    # Create a tiny WAV first, then convert via FLAC wrapper
    # Simpler: write raw FLAC with mutagen
    # Actually, mutagen needs an existing FLAC. Create minimal one.
    wav_path = path.with_suffix(".wav")
    create_wav(wav_path, duration_s=0.05)

    # Use ffmpeg if available, otherwise fall back to raw copy
    import subprocess
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(wav_path), "-c:a", "flac", str(path)],
            capture_output=True, check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        # No ffmpeg — just rename the wav and skip FLAC encoding
        # mutagen won't be able to read it, but the file will exist
        wav_path.rename(path)
        return
    finally:
        wav_path.unlink(missing_ok=True)

    # Add Vorbis comments
    from mutagen.flac import FLAC
    audio = FLAC(str(path))
    if artist:
        audio["artist"] = [artist]
    if album:
        audio["album"] = [album]
    if title:
        audio["title"] = [title]
    if track:
        audio["tracknumber"] = [track]
    if year:
        audio["date"] = [year]
    audio.save()


def create_m4a(path: Path, *, artist: str = "", album: str = "",
               title: str = "", track: str = "", year: str = "") -> None:
    """Create a minimal M4A (AAC) with iTunes-style tags."""
    path.parent.mkdir(parents=True, exist_ok=True)

    # Create via ffmpeg from a tiny WAV
    wav_path = path.with_suffix(".wav")
    create_wav(wav_path, duration_s=0.05)

    import subprocess
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(wav_path), "-c:a", "aac", "-b:a", "32k", str(path)],
            capture_output=True, check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        wav_path.rename(path)
        return
    finally:
        wav_path.unlink(missing_ok=True)

    from mutagen.mp4 import MP4
    audio = MP4(str(path))
    if artist:
        audio["\xa9ART"] = [artist]
    if album:
        audio["\xa9alb"] = [album]
    if title:
        audio["\xa9nam"] = [title]
    if track:
        try:
            audio["trkn"] = [(int(track), 0)]
        except ValueError:
            pass
    if year:
        audio["\xa9day"] = [year]
    audio.save()


def create_video_stub(path: Path) -> None:
    """Create a minimal file with .mp4/.mkv extension (not playable, but discoverable)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # A per-file trailer keeps each stub's content distinct, so content-hash
    # dedup doesn't collapse the (otherwise byte-identical) stubs into one.
    unique = b"\x00" + path.name.encode("utf-8")
    if path.suffix.lower() in (".mp4", ".m4v", ".mov"):
        ftyp = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"
        path.write_bytes(ftyp + unique)
    else:
        # MKV/other — just write some bytes
        path.write_bytes(b"\x1a\x45\xdf\xa3" + b"\x00" * 100 + unique)


def create_pdf_stub(path: Path) -> None:
    """Create a minimal valid PDF."""
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf = b"""%PDF-1.0
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj
xref
0 4
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
trailer<</Size 4/Root 1 0 R>>
startxref
190
%%EOF"""
    path.write_bytes(pdf)


def build_sample_library(base: Path) -> None:
    """Populate the _input/ drop tree. `base` is the library's _input directory.

    Per-root files go in `base/<root>/`; the root names match the input roots the
    server creates (memory, music, movie, tv, podcast, book, comedy). A few files
    are dropped directly in `base/` to exercise content-based root inference.
    """
    print(f"Populating sample _input tree at: {base}")

    # ── memory ────────────────────────────────────────────────
    mem = base / "memory"

    # Vacation photos
    create_jpeg(mem / "Hawaii Vacation" / "IMG_4521.jpg",
                color=(30, 144, 255), exif_date="2025:01:15 10:30:00")
    create_jpeg(mem / "Hawaii Vacation" / "IMG_4522.jpg",
                color=(0, 191, 255), exif_date="2025:01:15 14:22:00")
    create_jpeg(mem / "Hawaii Vacation" / "Snorkeling" / "IMG_4530.jpg",
                color=(0, 128, 128), exif_date="2025:01:16 09:15:00")

    # Birthday party
    create_jpeg(mem / "Birthday Party" / "DSC_0001.jpg",
                color=(255, 20, 147), exif_date="2024:12:20 15:00:00")
    create_jpeg(mem / "Birthday Party" / "DSC_0002.jpg",
                color=(255, 105, 180), exif_date="2024:12:20 15:30:00")

    # Random unsorted photos. The screenshot has no EXIF — its date comes from
    # the filename; photo_from_phone carries an EXIF capture date.
    create_png(mem / "screenshot_2025-03-01.png", color=(50, 50, 50))
    create_jpeg(mem / "photo_from_phone.jpg",
                color=(200, 200, 100), exif_date="2025:02:14 09:45:00")

    # Video. No EXIF is read for video, so the phone-style filename date is used.
    create_video_stub(mem / "Hawaii Vacation" / "sunset_timelapse.mp4")
    create_video_stub(mem / "PXL_20250116_lagoon.mp4")

    print("  ✓ memory")

    # ── music ─────────────────────────────────────────────────
    mus = base / "music"

    # Full album: Pink Floyd - Dark Side of the Moon
    dsotm = mus / "Pink Floyd" / "Dark Side of the Moon"
    for i, title in enumerate(["Speak to Me", "Breathe", "On the Run", "Time", "Money"], 1):
        create_mp3(dsotm / f"{i:02d} - {title}.mp3",
                   artist="Pink Floyd", album="Dark Side of the Moon",
                   title=title, track=str(i), year="1973")

    # Single track, no album
    create_mp3(mus / "Radiohead" / "Creep.mp3",
               artist="Radiohead", title="Creep", year="1992")

    # FLAC album
    ok_computer = mus / "Radiohead" / "OK Computer"
    for i, title in enumerate(["Airbag", "Paranoid Android", "Let Down"], 1):
        create_flac(ok_computer / f"{i:02d} {title}.flac",
                    artist="Radiohead", album="OK Computer",
                    title=title, track=str(i), year="1997")

    # VA compilation
    va = mus / "Various Artists" / "8 Mile Soundtrack"
    create_mp3(va / "01 - Eminem - Lose Yourself.mp3",
               artist="Eminem", albumartist="Various Artists",
               album="8 Mile Soundtrack", title="Lose Yourself",
               track="1", year="2002")
    create_mp3(va / "15 - Gang Starr - Battle.mp3",
               artist="Gang Starr", albumartist="Various Artists",
               album="8 Mile Soundtrack", title="Battle",
               track="15", year="2002")

    # Collaboration: primary artist + featured. The "feat." credit is split so
    # the track files under Jay-Z with feat:Alicia Keys recorded separately.
    create_mp3(mus / "Jay-Z" / "The Blueprint 3" / "03 - Empire State of Mind.mp3",
               artist="Jay-Z feat. Alicia Keys", album="The Blueprint 3",
               title="Empire State of Mind", track="3", year="2009")

    print("  ✓ music")

    # ── movie ─────────────────────────────────────────────────
    mov = base / "movie"

    create_video_stub(mov / "The Dark Knight (2008).mkv")
    create_video_stub(mov / "Inception.2010.mkv")

    # Series
    create_video_stub(mov / "Indiana Jones" / "Raiders of the Lost Ark (1981).mkv")
    create_video_stub(mov / "Indiana Jones" / "Temple of Doom (1984).mkv")

    # Lord of the Rings
    create_video_stub(mov / "Lord of the Rings" / "The Fellowship of the Ring (2001).mkv")
    create_video_stub(mov / "Lord of the Rings" / "The Two Towers (2002).mkv")

    print("  ✓ movie")

    # ── tv ────────────────────────────────────────────────────
    tv = base / "tv"

    # The Office
    office = tv / "The Office" / "Season 3"
    create_video_stub(office / "The.Office.S03E01.Gay.Witch.Hunt.mkv")
    create_video_stub(office / "The.Office.S03E02.The.Convention.mkv")
    create_video_stub(office / "The.Office.S03E03.The.Coup.mkv")

    # Breaking Bad
    bb = tv / "Breaking Bad" / "Season 1"
    create_video_stub(bb / "Breaking.Bad.S01E01.Pilot.mkv")
    create_video_stub(bb / "Breaking.Bad.S01E02.Cats.in.the.Bag.mkv")

    print("  ✓ tv")

    # ── podcast ───────────────────────────────────────────────
    pod = base / "podcast"

    create_mp3(pod / "Hardcore History" / "ep66-Supernova in the East.mp3",
               artist="Dan Carlin", album="Hardcore History",
               title="Supernova in the East", track="66", year="2018")
    create_mp3(pod / "Hardcore History" / "ep67-Supernova in the East II.mp3",
               artist="Dan Carlin", album="Hardcore History",
               title="Supernova in the East II", track="67", year="2019")
    create_mp3(pod / "Serial" / "ep01-The Alibi.mp3",
               artist="Sarah Koenig", album="Serial",
               title="The Alibi", track="1", year="2014")

    print("  ✓ podcast")

    # ── book (audiobooks) ─────────────────────────────────────
    books = base / "book"

    hobbit = books / "J.R.R. Tolkien" / "The Hobbit"
    for i, ch in enumerate(["An Unexpected Party", "Roast Mutton", "A Short Rest"], 1):
        create_mp3(hobbit / f"Chapter {i:02d} - {ch}.mp3",
                   artist="J.R.R. Tolkien", album="The Hobbit",
                   title=ch, track=str(i), year="1937")

    create_mp3(books / "Frank Herbert" / "Dune" / "Chapter 01 - A Beginning.mp3",
               artist="Frank Herbert", album="Dune",
               title="A Beginning", track="1", year="1965")

    print("  ✓ book")

    # ── comedy ────────────────────────────────────────────────
    com = base / "comedy"

    create_mp3(com / "John Mulaney" / "Kid Gorgeous at Radio City.mp3",
               artist="John Mulaney", title="Kid Gorgeous at Radio City", year="2018")
    create_video_stub(com / "Bo Burnham" / "Inside (2021).mp4")

    print("  ✓ comedy")

    # ── bare drops (no subdir) — exercise content-based inference ──
    # Dropped directly in _input/: pinpoint infers the root from content.
    create_jpeg(base / "loose_phone_photo.jpg",
                color=(180, 140, 90), exif_date="2025:05:10 17:30:00")  # → memory
    create_mp3(base / "Gorillaz - Feel Good Inc.mp3",
               artist="Gorillaz feat. De La Soul", title="Feel Good Inc",
               album="Demon Days", track="6", year="2005")  # → music
    # No content signal pinpoint can classify → parked in _input/_stuck/.
    (base / "scan_2025_invoice.dat").write_bytes(b"opaque binary blob, unknown type")

    print("  ✓ bare drops (memory, music, and one for _stuck)")

    # ── summary ───────────────────────────────────────────────
    total = sum(1 for _ in base.rglob("*") if _.is_file())
    print(f"\nDone: {total} files dropped into {base.resolve()}")


def main():
    parser = argparse.ArgumentParser(
        description="Populate a sample Pinpoint library's _input/ tree"
    )
    parser.add_argument(
        "--output", "-o",
        default="./sample_output",
        help="Library directory (default: ./sample_output, matching config.yaml)",
    )
    parser.add_argument(
        "--clean", action="store_true",
        help="Remove the existing library before populating",
    )
    args = parser.parse_args()

    library = Path(args.output)
    input_dir = library / "_input"

    if args.clean and library.exists():
        import shutil
        shutil.rmtree(library)
        print(f"Cleaned {library}")

    if input_dir.exists() and any(input_dir.iterdir()):
        print(f"Error: {input_dir} already exists and is not empty. Use --clean to replace.")
        raise SystemExit(1)

    build_sample_library(input_dir)

    print("\nPoint config.yaml at this library, then start the server:")
    print(f"  library: {library.resolve()}")
    print("Discovery imports everything from _input/ on first run.")


if __name__ == "__main__":
    main()
