"""Essai n°18, agent F1 : export ONNX d'IAT, UNE fois, à part du logiciel.

Seul script de l'essai qui demande PyTorch (+ timm, requis par le code des auteurs). À lancer dans
un environnement séparé, jamais dans celui du logiciel :
    python -m venv venv-export && venv-export/bin/pip install torch timm onnx onnxruntime numpy
    venv-export/bin/python essais/n18/iat_export_onnx.py

1. télécharge le code du modèle et les poids RETENUS (lol_v1, lol_v2) au commit figé, SHA-256 vérifié ;
   les poids « exposure » (MIT-Adobe FiveK, recherche seulement) ne sont jamais téléchargés ;
2. exporte deux ONNX par poids (opset 17, hauteur et largeur libres) :
     iat_<poids>_global.onnx  : image -> (gamma, matrice 3 x 3)          [partie globale seule]
     iat_<poids>_complet.onnx : image -> (mul, add, gamma, matrice)      [modèle complet]
3. vérifie onnxruntime contre PyTorch (écart max) et écrit export_iat.json (empreintes SHA-256).
Rien n'est écrit dans le dépôt : tout va dans le cache (VHS_N18_CACHE ou ~/.cache/vhs-restore-n18).
"""
from __future__ import annotations

import argparse
import json
import sys
import types
from pathlib import Path

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI))
import f1_iat  # noqa: E402


def charger_code(cache: Path, m: dict) -> None:
    src = cache / "src_iat"
    (src / "model").mkdir(parents=True, exist_ok=True)
    (src / "model" / "__init__.py").touch()
    for rel, e in m["sources_code"].items():
        f1_iat.telecharger(e["url"], src / rel, e["sha256"])
    if "imp" not in sys.modules:            # global_net.py fait « import imp » (inutilisé), absent
        sys.modules["imp"] = types.ModuleType("imp")   # de Python 3.12+ : module vide, code intact
    sys.path.insert(0, str(src))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--poids", default=",".join(f1_iat.POIDS_RETENUS))
    ap.add_argument("--opset", type=int, default=17)
    a = ap.parse_args()

    import numpy as np
    import torch
    import onnxruntime as ort

    m = f1_iat.manifeste()
    cache = f1_iat.dossier_cache()
    charger_code(cache, m)
    from model.IAT_main import IAT           # code officiel, non modifié

    class Global(torch.nn.Module):
        def __init__(self, net):
            super().__init__()
            self.g = net.global_net

        def forward(self, image):
            gamma, color = self.g(image)
            return gamma, color

    class Complet(torch.nn.Module):
        def __init__(self, net):
            super().__init__()
            self.net = net

        def forward(self, image):
            mul, add = self.net.local_net(image)
            gamma, color = self.net.global_net(image)
            return mul, add, gamma, color

    rapport = {"torch": torch.__version__, "onnxruntime": ort.__version__, "opset": a.opset,
               "commit_iat": m["commit"], "onnx": {}, "verification": {}}
    for nom in a.poids.split(","):
        e = m["poids"][nom]
        if not e.get("retenu"):
            raise SystemExit(f"{nom} : poids exclu ({e['licence_donnees']})")
        pth = f1_iat.telecharger(e["url"], cache / e["fichier"], e["sha256"])
        net = IAT(type=e.get("type_global", "lol"))
        net.load_state_dict(torch.load(pth, map_location="cpu"), strict=True)
        net.eval()
        for partie, mod, sorties in (("global", Global(net), ["gamma", "color"]),
                                     ("complet", Complet(net), ["mul", "add", "gamma", "color"])):
            out = cache / f"iat_{nom}_{partie}.onnx"
            axes = {"image": {2: "h", 3: "w"}}
            axes.update({s: {2: "h", 3: "w"} for s in sorties if s in ("mul", "add")})
            torch.onnx.export(mod.eval(), torch.rand(1, 3, 288, 360), str(out), input_names=["image"],
                              output_names=sorties, dynamic_axes=axes, opset_version=a.opset,
                              do_constant_folding=True, dynamo=False)
            rapport["onnx"][out.name] = {"sha256": f1_iat.sha256(out), "octets": out.stat().st_size,
                                         "poids": e["fichier"], "poids_sha256": e["sha256"]}
        # vérification : sortie finale PyTorch (IAT.forward officiel) contre ONNX recomposé en numpy
        s_g = ort.InferenceSession(str(cache / f"iat_{nom}_global.onnx"), providers=["CPUExecutionProvider"])
        s_c = ort.InferenceSession(str(cache / f"iat_{nom}_complet.onnx"), providers=["CPUExecutionProvider"])
        rng = np.random.default_rng(0)
        ecarts = {}
        for h, w in ((576, 720), (240, 320)):
            x = rng.random((1, 3, h, w), dtype=np.float32) * 0.4
            with torch.no_grad():
                _, _, ref = net(torch.from_numpy(x))
                g_ref, c_ref = net.global_net(torch.from_numpy(x))
            g_o, c_o = s_g.run(None, {"image": x})
            mul, add, g2, c2 = s_c.run(None, {"image": x})
            haut = (x[0] * mul[0] + add[0]).transpose(1, 2, 0)
            y = np.clip(haut @ c2[0].T, 1e-8, 1.0) ** g2.reshape(-1)[0]
            ecarts[f"{w}x{h}"] = {
                "global_gamma": float(abs(g_o.reshape(-1)[0] - g_ref.item())),
                "global_matrice": float(np.abs(c_o - c_ref.numpy()).max()),
                "complet_image": float(np.abs(y - ref[0].numpy().transpose(1, 2, 0)).max())}
        rapport["verification"][nom] = ecarts
        print(nom, json.dumps(ecarts))
    (cache / "export_iat.json").write_text(json.dumps(rapport, indent=2), encoding="utf-8")
    for k, v in rapport["onnx"].items():
        print(f"{v['sha256']}  {k}  ({v['octets']} octets)")
    print("manifeste :", cache / "export_iat.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
