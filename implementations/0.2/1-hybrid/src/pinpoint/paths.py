from pathlib import PurePosixPath

from pinpoint.models import ROOT_DIRS


def _pad2(val: str) -> str:
    return val.zfill(2) if val.isdigit() else val


def _get(tags: dict, key: str) -> str:
    vals = tags.get(key, [])
    return vals[0] if vals else ""


def derive_path(root: str, tags: dict, original_filename: str) -> str:
    ext = PurePosixPath(original_filename).suffix
    root_dir = ROOT_DIRS.get(root, root)
    name = _get(tags, "name")

    if root == "memory":
        month = _get(tags, "month") or "unknown"
        event = _get(tags, "event")
        parts = [root_dir, month]
        if event:
            parts.extend(event.split(":"))
        if name:
            parts.append(f"{name}{ext}")
        else:
            parts.append(original_filename)
        return "/".join(parts)

    if root == "music":
        artist = _get(tags, "artist") or "_unknown"
        album = _get(tags, "album")
        year = _get(tags, "year")
        track = _get(tags, "track")

        parts = [root_dir, artist]

        if album:
            album_dir = f"[{year}] {album}" if year else album
            parts.append(album_dir)

        if name:
            if track:
                parts.append(f"{_pad2(track)} - {name}{ext}")
            else:
                parts.append(f"{name}{ext}")
        else:
            if track:
                parts.append(f"{_pad2(track)} - {original_filename}")
            else:
                parts.append(original_filename)
        return "/".join(parts)

    if root == "movie":
        series = _get(tags, "series")
        year = _get(tags, "year")
        parts = [root_dir]
        if series:
            parts.extend(series.split(":"))
        if name:
            fname = f"{name} [{year}]{ext}" if year else f"{name}{ext}"
            parts.append(fname)
        else:
            parts.append(original_filename)
        return "/".join(parts)

    if root == "tv":
        show = _get(tags, "show") or "_unknown"
        season = _get(tags, "season")
        episode = _get(tags, "episode")
        parts = [root_dir, show]
        if season:
            parts.append(f"Season {_pad2(season)}")
        if name:
            if episode:
                parts.append(f"{_pad2(episode)} - {name}{ext}")
            else:
                parts.append(f"{name}{ext}")
        else:
            if episode:
                parts.append(f"{_pad2(episode)}{ext}")
            else:
                parts.append(original_filename)
        return "/".join(parts)

    if root == "podcast":
        show = _get(tags, "show") or "_unknown"
        episode = _get(tags, "episode")
        parts = [root_dir, show]
        if name:
            if episode:
                parts.append(f"{_pad2(episode)} - {name}{ext}")
            else:
                parts.append(f"{name}{ext}")
        else:
            if episode:
                parts.append(f"{_pad2(episode)} - {original_filename}")
            else:
                parts.append(original_filename)
        return "/".join(parts)

    if root == "book":
        author = _get(tags, "author") or "_unknown"
        series = _get(tags, "series")
        parts = [root_dir, author]
        if series:
            parts.extend(series.split(":"))
        if name:
            parts.append(f"{name}{ext}")
        else:
            parts.append(original_filename)
        return "/".join(parts)

    if root == "comedy":
        artist = _get(tags, "artist") or "_unknown"
        year = _get(tags, "year")
        parts = [root_dir, artist]
        if name:
            fname = f"[{year}] {name}{ext}" if year else f"{name}{ext}"
            parts.append(fname)
        else:
            parts.append(original_filename)
        return "/".join(parts)

    return f"{root_dir}/{original_filename}"
