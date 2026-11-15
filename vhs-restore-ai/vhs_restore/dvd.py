"""DVD VIDEO_TS : un titre découpé en VOB (1 Go chacun) redevient un seul film.

On ignore les menus (`VTS_xx_0.VOB`, `VIDEO_TS.VOB`). Les morceaux d'un titre
sont lus par le démultiplexeur `concat` de FFmpeg, sans recopier le DVD
(le disque peut être en lecture seule). Aucune nouvelle dépendance.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

from .probe import MediaInfo, analyze
from .tools import ToolError, Toolset, run_capture

_VTS = re.compile(r"^VTS_(\d+)_(\d+)\.VOB$", re.IGNORECASE)


def is_menu(name: str) -> bool:
    """Menu DVD, jamais le film."""
    if name.upper() == "VIDEO_TS.VOB":
        return True
    m = _VTS.match(name)
    return bool(m and int(m.group(2)) == 0)


def title_key(name: str) -> str | None:
    """`VTS_01` pour un morceau de film, rien pour un menu ou un autre fichier."""
    m = _VTS.match(name)
    if not m or int(m.group(2)) == 0:
        return None
    return f"VTS_{int(m.group(1)):02d}"


def titles_in(folder: Path) -> list[list[Path]]:
    """Un groupe par titre, morceaux dans l'ordre (VTS_01_1, VTS_01_2…)."""
    groups: dict[str, list[Path]] = {}
    if not folder.is_dir():
        return []
    for p in folder.iterdir():
        if not p.is_file():
            continue
        key = title_key(p.name)
        if key:
            groups.setdefault(key, []).append(p)
    out = []
    for key in sorted(groups):
        out.append(sorted(groups[key], key=lambda p: int(_VTS.match(p.name).group(2))))
    return out


def parts_for(path: Path) -> list[Path]:
    """Tous les morceaux du titre si `path` en est un, sinon le fichier seul."""
    path = Path(path)
    key = title_key(path.name)
    if not key:
        return [path]
    for title in titles_in(path.parent):
        if any(p.resolve() == path.resolve() for p in title):
            return title
    return [path]


def input_args(info: MediaInfo) -> list[str]:
    """`-i` du fichier, ou le démultiplexeur concat si le film a plusieurs VOB."""
    parts = tuple(info.parts)
    if len(parts) <= 1:
        return ["-i", str(info.path)]
    lst = info.concat_list
    if lst is None or not Path(lst).is_file():
        d = Path(tempfile.mkdtemp(prefix="vhsrestore_dvd_", dir=os.environ.get("VHSRA_TMP") or None))
        lst = d / "concat.txt"
        lines = []
        for p in parts:
            text = Path(p).resolve().as_posix().replace("'", "'\\''")
            lines.append(f"file '{text}'\n")
        lst.write_text("".join(lines), encoding="utf-8")
        info.concat_list = lst
    return ["-f", "concat", "-safe", "0", "-i", str(lst)]


def _duration(path: Path, tools: Toolset) -> float:
    res = run_capture([tools.ffprobe.path, "-v", "error", "-print_format", "json",
                       "-show_format", str(path)], timeout=60)
    if res.returncode != 0:
        raise ToolError(f"Morceau DVD illisible : {path.name}\n{res.stderr.strip()[-300:]}")
    raw = json.loads(res.stdout or "{}").get("format", {}).get("duration")
    try:
        return float(raw or 0)
    except (TypeError, ValueError):
        return 0.0


def open_media(path: str | Path, tools: Toolset) -> MediaInfo:
    """Analyse un fichier. Un VOB de titre entraîne tous les morceaux du même titre."""
    p = Path(path)
    if is_menu(p.name):
        raise ToolError(
            "Ce fichier est un menu de DVD, pas le film.\n"
            "Choisissez un morceau VTS_xx_1.VOB (ou le dossier VIDEO_TS).")
    parts = parts_for(p)
    info = analyze(parts[0], tools)
    key = title_key(parts[0].name)
    if key:
        info.output_stem = key
    if len(parts) == 1:
        return info
    extra = sum(_duration(part, tools) for part in parts[1:])
    info.duration += extra
    info.parts = tuple(parts)
    info.warnings.insert(0, f"DVD : {len(parts)} morceaux du titre {info.output_stem} "
                            "réunis en un seul film. Les menus ne sont pas restaurés.")
    return info
