"""Colorisation facultative des photos noir et blanc (mode Photo uniquement).

Les couleurs sont INVENTÉES par une IA : ce ne sont pas les vraies couleurs de la scène.
Règles de l'application :
- jamais activée par défaut ;
- seulement pour une photo noir et blanc ;
- produit un fichier SUPPLÉMENTAIRE (« …_colorisee_ia.png ») : la photo restaurée en noir et
  blanc est toujours écrite, et l'original n'est jamais modifié ;
- la luminance (le dessin, les détails) vient de la photo restaurée, pixel pour pixel : l'IA ne
  fournit que la couleur, à basse résolution, puis lissée.

Modèle : DDColor-tiny (ICCV 2023, licence Apache-2.0), export ONNX 512×512 publié sur Hugging
Face (edgetools/ddcolor), révision et empreinte figées ci-dessous. Calcul sur le processeur avec
onnxruntime, sans carte graphique.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import threading
from pathlib import Path

from .tools import TOOLS_DIR, Cancelled, Tool, ToolError, run_capture, user_tools_dir

MODEL_NAME = "ddcolor-tiny-fp16.onnx"
MODEL_URL = ("https://huggingface.co/edgetools/ddcolor/resolve/"
             "4755ae9f1f7a35a9e7693b96c2a88f3432cb6ab0/ddcolor-tiny-fp16.onnx")
MODEL_SHA256 = "2653da00dc15e54a45e5200b61dbf82ee9ceaf56b02bb9b9657569ac775e82e6"
SIZE = 512
LABEL = "Couleurs inventées par l'IA (DDColor), pas les vraies couleurs"

_verified: dict[str, bool] = {}
_session_lock = threading.Lock()
_sessions: dict[str, object] = {}


def model_path() -> Path | None:
    env = os.environ.get("VHSRA_DDCOLOR")
    for p in ([Path(env)] if env else []) + [TOOLS_DIR / "ddcolor" / MODEL_NAME,
                                             user_tools_dir() / "ddcolor" / MODEL_NAME]:
        if p.is_file():
            return p
    return None


def detect() -> Tool:
    """Outil « Colorisation » : onnxruntime importable et modèle présent."""
    t = Tool("Colorisation (DDColor)")
    p = model_path()
    if p is None:
        return t
    t.path = str(p)
    try:
        import numpy  # noqa: F401
        import onnx  # noqa: F401
        import onnxruntime
        t.version = f"onnxruntime {onnxruntime.__version__}"
    except Exception as exc:          # paquet absent ou cassé : l'outil est simplement indisponible
        t.problem = f"onnxruntime ou onnx indisponible ({type(exc).__name__})"
    return t


def _check_model(path: Path) -> None:
    key = str(path)
    if key not in _verified:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        _verified[key] = h.hexdigest() == MODEL_SHA256
    if not _verified[key]:
        raise ToolError(f"Le modèle de colorisation est abîmé ou n'est pas le bon : {path}. "
                        "Relancez l'installation des outils (option -AvecCouleurs).")


def _fp32_bytes(path: Path) -> bytes:
    """Le modèle publié stocke ses poids en demi-précision (fp16) : sur un processeur,
    onnxruntime le calcule alors plus de 100 fois plus lentement (plus de 3 minutes au lieu
    d'une seconde, mesuré). On le convertit en pleine précision, en mémoire, au chargement.
    Le fichier sur le disque reste celui publié (vérifié par son empreinte)."""
    import numpy as np
    import onnx
    from onnx import TensorProto, numpy_helper

    m = onnx.load(str(path))

    def to32(t) -> None:
        if t.data_type == TensorProto.FLOAT16:
            t.CopyFrom(numpy_helper.from_array(numpy_helper.to_array(t).astype(np.float32), t.name))

    for t in m.graph.initializer:
        to32(t)
    for n in m.graph.node:
        for a in n.attribute:
            if a.type == onnx.AttributeProto.TENSOR:
                to32(a.t)
            elif n.op_type == "Cast" and a.name == "to" and a.i == TensorProto.FLOAT16:
                a.i = TensorProto.FLOAT
    for vi in list(m.graph.value_info) + list(m.graph.input) + list(m.graph.output):
        if vi.type.tensor_type.elem_type == TensorProto.FLOAT16:
            vi.type.tensor_type.elem_type = TensorProto.FLOAT
    return m.SerializeToString()


def _session(path: Path):
    import onnxruntime as ort
    with _session_lock:
        s = _sessions.get(str(path))
        if s is None:
            opts = ort.SessionOptions()
            opts.log_severity_level = 3
            s = ort.InferenceSession(_fp32_bytes(path), sess_options=opts,
                                     providers=["CPUExecutionProvider"])
            _sessions[str(path)] = s
        return s


# --- CIE Lab (D65, convention OpenCV en flottants : L 0..100, a/b ~ -127..127) ---------------

_XN, _ZN = 0.950456, 1.088754


def _srgb_to_linear(c):
    import numpy as np
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _linear_to_srgb(c):
    import numpy as np
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def gray_to_L(g):
    """Gris sRGB 0..1 -> L de Lab (pour un gris, Y = valeur linéaire)."""
    import numpy as np
    y = _srgb_to_linear(g)
    return np.where(y > 0.008856, 116.0 * np.cbrt(y) - 16.0, 903.3 * y)


def lab_to_rgb(L, a, b):
    """Lab -> sRGB 0..1 (tableaux H×W)."""
    import numpy as np
    fy = (L + 16.0) / 116.0
    fx = fy + a / 500.0
    fz = fy - b / 200.0

    def finv(f):
        f3 = f ** 3
        return np.where(f3 > 0.008856, f3, (f - 16.0 / 116.0) / 7.787)

    x, y, z = finv(fx) * _XN, finv(fy), finv(fz) * _ZN
    r = 3.240479 * x - 1.537150 * y - 0.498535 * z
    g = -0.969256 * x + 1.875992 * y + 0.041556 * z
    bb = 0.055648 * x - 0.204043 * y + 1.057311 * z
    return np.stack([_linear_to_srgb(r), _linear_to_srgb(g), _linear_to_srgb(bb)], axis=-1)


def _read_gray(ffmpeg: str, src: Path, size: tuple[int, int] | None = None):
    import numpy as np
    vf = [f"scale={size[0]}:{size[1]}:flags=area"] if size else []
    cmd = [ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error", "-i", str(src)]
    cmd += (["-vf", ",".join(vf)] if vf else []) + ["-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"]
    r = subprocess.run(cmd, capture_output=True, timeout=300, stdin=subprocess.DEVNULL,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode:
        raise ToolError("Lecture de la photo impossible : " + r.stderr.decode("utf-8", "replace")[-300:])
    return np.frombuffer(r.stdout, dtype=np.uint8)


def _size(ffprobe: str, src: Path) -> tuple[int, int]:
    r = run_capture([ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
                     "stream=width,height", "-of", "csv=p=0:s=x", str(src)], timeout=60)
    try:
        w, h = (int(v) for v in r.stdout.strip().split("x")[:2])
    except ValueError as exc:
        raise ToolError("Taille de la photo illisible.") from exc
    return w, h


def colorize(src: Path, dst: Path, ffmpeg: str, ffprobe: str, model: Path, *,
             cancel: threading.Event | None = None) -> Path:
    """Colorise une photo noir et blanc `src` (déjà restaurée) vers `dst` (PNG RGB, même taille).
    La luminance de `dst` est celle de `src` ; seule la couleur vient de l'IA."""
    import numpy as np
    src, dst = Path(src), Path(dst)
    if dst.resolve() == src.resolve():
        raise ToolError("La photo colorisée ne peut pas remplacer la photo d'origine.")
    _check_model(model)
    w, h = _size(ffprobe, src)
    small = _read_gray(ffmpeg, src, (SIZE, SIZE)).reshape(SIZE, SIZE).astype(np.float32) / 255.0
    if cancel is not None and cancel.is_set():
        raise Cancelled()
    sess = _session(model)
    x = np.repeat(small[None, None], 3, axis=1)                 # gris -> RGB gris (a = b = 0)
    ab = sess.run(None, {sess.get_inputs()[0].name: x})[0][0].astype(np.float32)   # 2×512×512
    if cancel is not None and cancel.is_set():
        raise Cancelled()
    full = _read_gray(ffmpeg, src).reshape(h, w).astype(np.float32) / 255.0
    out = np.empty((h, w, 3), dtype=np.uint8)
    band = 512                       # par bandes : une grande photo ne sature pas la mémoire
    for y in range(0, h, band):
        y2 = min(h, y + band)
        ab_band = _band(ab, h, w, y, y2)
        rgb = lab_to_rgb(gray_to_L(full[y:y2]), ab_band[0], ab_band[1])
        out[y:y2] = np.round(rgb * 255.0).astype(np.uint8)
    part_path = dst.with_name(dst.stem + ".partiel.png")
    r = subprocess.run([ffmpeg, "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
                        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-i", "-",
                        "-frames:v", "1", "-c:v", "png", "-f", "image2", str(part_path)],
                       input=out.tobytes(), capture_output=True, timeout=300,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode:
        part_path.unlink(missing_ok=True)
        raise ToolError("Écriture de la photo colorisée impossible : "
                        + r.stderr.decode("utf-8", "replace")[-300:])
    os.replace(part_path, dst)
    return dst


def _band(ab, h: int, w: int, y: int, y2: int):
    """Couleur d'une bande de lignes [y, y2) à pleine taille, sans calculer toute l'image."""
    import numpy as np
    _, h0, w0 = ab.shape
    ys = np.clip((np.arange(y, y2, dtype=np.float32) + 0.5) * h0 / h - 0.5, 0, h0 - 1)
    xs = np.clip((np.arange(w, dtype=np.float32) + 0.5) * w0 / w - 0.5, 0, w0 - 1)
    y0, x0 = np.floor(ys).astype(int), np.floor(xs).astype(int)
    y1, x1 = np.minimum(y0 + 1, h0 - 1), np.minimum(x0 + 1, w0 - 1)
    wy, wx = (ys - y0)[None, :, None], (xs - x0)[None, None, :]
    top = ab[:, y0][:, :, x0] * (1 - wx) + ab[:, y0][:, :, x1] * wx
    bot = ab[:, y1][:, :, x0] * (1 - wx) + ab[:, y1][:, :, x1] * wx
    return (top * (1 - wy) + bot * wy).astype(np.float32)


__all__ = ["LABEL", "MODEL_NAME", "MODEL_SHA256", "MODEL_URL", "colorize", "detect", "model_path"]
