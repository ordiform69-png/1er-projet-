"""Essai n°18, agent F3 : téléchargement des poids et conversion en ONNX (À PART, une fois).

Dépendances d'ESSAI seulement (jamais dans requirements*.txt) :
    pip install torch spandrel onnx cryptography
(cryptography sert uniquement au lien Mega de « 1x VHS Sharpen », chiffré par Mega.)

    python essais/n18/f3_convertir_onnx.py            # les 4 modèles
    python essais/n18/f3_convertir_onnx.py baldrick   # un seul

Les poids (.pth) et les .onnx vont dans le cache HORS dépôt (variable VHSRA_N18_CACHE,
par défaut ~/.cache/vhsrestore-n18/f3). L'empreinte SHA-256 de chaque .pth est vérifiée ;
celle de chaque .onnx obtenu est écrite dans <nom>.onnx.sha256 (la sortie d'export peut
varier d'une version de torch à l'autre : f3_vhs.py la vérifie contre ce fichier).
"""
from __future__ import annotations

import base64
import hashlib
import json
import struct
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from f3_modeles import CACHE, MODELES, chemin_onnx, chemin_pth, par_cle  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (essai VHS Restore AI n18)"}


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def _copier(reponse, dest: Path, dechiffre=None) -> None:
    with open(dest, "wb") as o:
        while bloc := reponse.read(1 << 20):
            o.write(dechiffre(bloc) if dechiffre else bloc)


def _mega(url: str, dest: Path) -> None:
    """Lien public Mega : la clé est dans l'adresse (après « # ») ; fichier chiffré AES-CTR."""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    def b64(s: str) -> bytes:
        s = s.replace("-", "+").replace("_", "/")
        return base64.b64decode(s + "=" * (-len(s) % 4))

    poignee, cle = url.split("/file/")[1].split("#")
    k = struct.unpack(">8I", b64(cle))
    aes = struct.pack(">4I", k[0] ^ k[4], k[1] ^ k[5], k[2] ^ k[6], k[3] ^ k[7])
    iv = struct.pack(">2I", k[4], k[5]) + b"\0" * 8
    req = urllib.request.Request("https://g.api.mega.co.nz/cs?id=1",
                                 data=json.dumps([{"a": "g", "g": 1, "p": poignee}]).encode(),
                                 headers={"Content-Type": "application/json", **UA})
    rep = json.loads(urllib.request.urlopen(req, timeout=60).read())[0]
    if isinstance(rep, int):
        raise RuntimeError(f"Mega a refusé le lien (code {rep})")
    dec = Cipher(algorithms.AES(aes), modes.CTR(iv)).decryptor()
    lien = rep["g"].replace("http://", "https://")
    with urllib.request.urlopen(urllib.request.Request(lien, headers=UA), timeout=120) as r:
        _copier(r, dest, dec.update)


def telecharger(m: dict) -> Path:
    dest = chemin_pth(m)
    if dest.is_file() and _sha256(dest) == m["sha256"]:
        print(f"  déjà présent, SHA-256 vérifiée : {dest}")
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    src = m["source"]
    print(f"  téléchargement depuis {src['url']}")
    if src["type"] == "mega":
        _mega(src["url"], tmp)
    else:
        url = src["url"] if src["type"] == "direct" else (
            f"https://drive.usercontent.google.com/download?id={src['id']}&export=download&confirm=t")
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
            _copier(r, tmp)
    empreinte = _sha256(tmp)
    if empreinte != m["sha256"]:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"SHA-256 différente pour {m['fichier']} : {empreinte} (attendu {m['sha256']})")
    tmp.replace(dest)
    print(f"  SHA-256 vérifiée : {empreinte}")
    return dest


def convertir(m: dict) -> Path:
    import torch
    from spandrel import ModelLoader

    pth, onnx_path = telecharger(m), chemin_onnx(m)
    desc = ModelLoader().load_from_file(str(pth))
    if desc.scale != m["echelle"]:
        raise RuntimeError(f"échelle lue {desc.scale}, attendue {m['echelle']}")
    print(f"  architecture lue par spandrel : {desc.architecture.name} {getattr(desc, 'size_requirements', '')}")
    net = desc.model.eval().float()
    exemple = torch.rand(1, 3, 64, 64)
    torch.onnx.export(net, (exemple,), str(onnx_path), input_names=["image"], output_names=["sortie"],
                      dynamic_axes={"image": {2: "h", 3: "w"}, "sortie": {2: "H", 3: "W"}},
                      opset_version=17, dynamo=False)
    # contrôle : même résultat en ONNX Runtime qu'en PyTorch
    import numpy as np
    import onnxruntime as ort
    s = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    x = torch.rand(1, 3, 48, 40)
    with torch.no_grad():
        ref = net(x).numpy()
    sortie = s.run(None, {"image": x.numpy()})[0]
    ecart = float(np.abs(ref - sortie).max())
    print(f"  écart max PyTorch / ONNX Runtime : {ecart:.2e}")
    empreinte = _sha256(onnx_path)
    Path(str(onnx_path) + ".sha256").write_text(
        json.dumps({"sha256": empreinte, "pth_sha256": m["sha256"], "torch": torch.__version__,
                    "ecart_max_torch_onnx": ecart}, indent=1), encoding="utf-8")
    print(f"  ONNX : {onnx_path} ({onnx_path.stat().st_size} octets) SHA-256 {empreinte}")
    return onnx_path


def main() -> int:
    cles = sys.argv[1:] or [m["cle"] for m in MODELES]
    print(f"Cache (hors dépôt) : {CACHE}")
    erreurs = 0
    for cle in cles:
        m = par_cle(cle)
        print(f"- {m['nom']} ({m['licence_modele']})")
        try:
            convertir(m)
        except Exception as exc:   # on continue avec les autres modèles
            erreurs += 1
            print(f"  ÉCHEC : {exc}")
    return 1 if erreurs else 0


if __name__ == "__main__":
    sys.exit(main())
