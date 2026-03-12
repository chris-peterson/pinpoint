import re
from pathlib import Path

from pinpoint.models import ROOT_FIELDS


def defaults_from_filename(source_path: str, root: str, input_path: str) -> dict:
    defs = {}
    rel = source_path
    if input_path and source_path.startswith(input_path):
        rel = source_path[len(input_path):].lstrip("/")

    parts = rel.split("/")
    filename = parts[-1] if parts else ""
    dirs = parts[:-1]

    stem = Path(filename).stem

    if root == "memory":
        if dirs:
            defs["event"] = dirs[-1]

    elif root == "music":
        if len(dirs) >= 1:
            defs["artist"] = dirs[0]
        if len(dirs) >= 2:
            album_dir = dirs[1]
            year_match = re.match(r"\[(\d{4})\]\s*(.*)", album_dir)
            if year_match:
                defs["year"] = year_match.group(1)
                defs["album"] = year_match.group(2)
            else:
                defs["album"] = album_dir
        track_match = re.match(r"^(\d{1,3})\s*[-–.]\s*(.*)", stem)
        if track_match:
            defs["track"] = track_match.group(1).zfill(2)
            defs["name"] = track_match.group(2)

    elif root == "movie":
        year_match = re.search(r"[\(\[]((?:19|20)\d{2})[\)\]]", stem)
        if year_match:
            defs["year"] = year_match.group(1)
            title = stem[:year_match.start()].strip().rstrip(".-_ ")
            if title:
                defs["name"] = title.replace(".", " ")
        else:
            cleaned = stem.replace(".", " ")
            if cleaned:
                defs["name"] = cleaned

    elif root == "tv":
        se_match = re.search(r"[Ss](\d{1,2})[Ee](\d{1,3})", stem)
        if se_match:
            defs["season"] = se_match.group(1).zfill(2)
            defs["episode"] = se_match.group(2).zfill(2)
            show = stem[:se_match.start()].strip().rstrip(".-_ ").replace(".", " ")
            if show:
                defs["show"] = show
            after = stem[se_match.end():].strip().lstrip(".-_ ").replace(".", " ")
            if after:
                defs["name"] = after

    elif root == "podcast":
        ep_match = re.match(r"^(\d{1,4})\s*[-–.]\s*(.*)", stem)
        if ep_match:
            defs["episode"] = ep_match.group(1).zfill(2)
            defs["name"] = ep_match.group(2)
        if dirs:
            defs["show"] = dirs[0]

    elif root == "book":
        if dirs:
            defs["author"] = dirs[0]
        defs["name"] = stem.replace(".", " ")

    elif root == "comedy":
        if dirs:
            defs["artist"] = dirs[0]
        year_match = re.search(r"[\(\[]((?:19|20)\d{2})[\)\]]", stem)
        if year_match:
            defs["year"] = year_match.group(1)
            title = stem[:year_match.start()].strip().rstrip(".-_ ")
            if title:
                defs["name"] = title.replace(".", " ")
        else:
            defs["name"] = stem.replace(".", " ")

    return defs


async def extract_audio_metadata(file_path: str) -> dict:
    defs = {}
    try:
        from mutagen import File as MutagenFile
        mf = MutagenFile(file_path, easy=True)
        if mf is None:
            return defs
        if "title" in mf:
            defs["name"] = mf["title"][0]
        if "artist" in mf:
            defs["artist"] = mf["artist"][0]
        if "album" in mf:
            defs["album"] = mf["album"][0]
        if "date" in mf:
            defs["year"] = mf["date"][0][:4]
        if "tracknumber" in mf:
            raw = mf["tracknumber"][0]
            num = raw.split("/")[0]
            defs["track"] = num.zfill(2)
    except Exception:
        pass
    return defs


async def defaults_from_source(source_path: str, root: str, input_path: str) -> dict:
    filename_defs = defaults_from_filename(source_path, root, input_path)

    metadata_defs = {}
    file_class = Path(source_path).suffix.lower()
    audio_exts = {".mp3", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".wma", ".aiff"}
    if file_class in audio_exts:
        metadata_defs = await extract_audio_metadata(source_path)

    merged = {**filename_defs, **metadata_defs}
    return {
        "filename_defs": filename_defs,
        "metadata_defs": metadata_defs,
        "merged": merged,
    }
