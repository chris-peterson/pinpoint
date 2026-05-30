import re
from pathlib import Path

from pinpoint.models import SOURCE_WEIGHTS


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
        track_match = re.match(r"^(\d{1,3})\s*[-\u2013.]\s*(.*)", stem)
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
        ep_match = re.match(r"^(\d{1,4})\s*[-\u2013.]\s*(.*)", stem)
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


def source_for_field(field: str, filename_defs: dict, metadata_defs: dict) -> str:
    if field in metadata_defs:
        return "metadata"
    if field in filename_defs:
        return "filename"
    return "fallback"


def confidence_for_source(source: str) -> float:
    return SOURCE_WEIGHTS.get(source, 0.1)


# A "feat." marker — possibly opened by a paren/bracket — separates the primary
# artist from featured collaborators. Within the featured segment, collaborators
# are separated by commas, ampersands, slashes, or "and"/"with".
_FEAT_SPLIT = re.compile(r"[\s(\[]+(?:feat|ft|featuring)\.?\s+", re.IGNORECASE)
_COLLAB_SPLIT = re.compile(r"\s*[,&/;]\s*|\s+(?:and|with)\s+", re.IGNORECASE)


def parse_artists(raw_values: list[str]) -> tuple[str, list[str]]:
    """Split raw artist metadata into a primary artist and featured collaborators.

    Handles both multi-valued artist frames (the first value is primary, the rest
    are featured) and a single string crediting collaborators with a "feat." marker
    (e.g. "Jay-Z feat. Alicia Keys"). The primary artist string is never split on
    "&"/"," so band names like "Earth, Wind & Fire" stay intact; only the segment
    after an explicit feat marker is broken into multiple collaborators.
    """
    primary = ""
    feats: list[str] = []
    for i, entry in enumerate(raw_values):
        entry = (entry or "").strip()
        if not entry:
            continue
        segments = _FEAT_SPLIT.split(entry)
        head = segments[0].strip().rstrip(" ([")
        if i == 0:
            primary = head
        elif head:
            feats.append(head)
        for seg in segments[1:]:
            seg = seg.strip().rstrip(")]").strip()
            for name in _COLLAB_SPLIT.split(seg):
                name = name.strip().strip(")]").strip()
                if name:
                    feats.append(name)

    seen = {primary.lower()}
    deduped: list[str] = []
    for f in feats:
        if f.lower() not in seen:
            seen.add(f.lower())
            deduped.append(f)
    return primary, deduped


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
            primary, feats = parse_artists(list(mf["artist"]))
            if primary:
                defs["artist"] = primary
            if feats:
                defs["feat"] = feats
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
    file_ext = Path(source_path).suffix.lower()
    audio_exts = {".mp3", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".wma", ".aiff"}
    if file_ext in audio_exts:
        metadata_defs = await extract_audio_metadata(source_path)

    merged = {**filename_defs, **metadata_defs}
    return {
        "filename_defs": filename_defs,
        "metadata_defs": metadata_defs,
        "merged": merged,
    }


def compute_file_confidence(tags: dict, sources: dict, root: str) -> float:
    from pinpoint.models import EXPECTED_TAGS
    expected = EXPECTED_TAGS.get(root, [])

    if not tags:
        return 0.1

    total_weight = 0.0
    total_score = 0.0

    for field, values in tags.items():
        if not values:
            continue
        source = sources.get(field, "fallback")
        conf = confidence_for_source(source)
        weight = 2.0 if field in expected else 1.0
        total_weight += weight
        total_score += conf * weight

    for field in expected:
        if field not in tags or not tags[field]:
            total_weight += 2.0
            total_score += 0.1 * 2.0

    return round(total_score / total_weight, 2) if total_weight > 0 else 0.1
