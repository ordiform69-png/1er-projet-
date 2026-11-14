"""Adaptateur pour Real-ESRGAN ncnn-vulkan (exécutable portable, GPU via Vulkan).

Interface minimale pour pouvoir remplacer le moteur : upscale_dir(entrée, sortie).
L'exécutable traite un dossier d'images PNG et écrit les images agrandies x4.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable

from .tools import Tool, ToolError, run


class RealEsrganUpscaler:
    scale = 4

    def __init__(self, tool: Tool, model: str = "realesrgan-x4plus", tile: int = 0, gpu: str = "auto"):
        if not tool.ok:
            raise ToolError("Real-ESRGAN n'est pas installé : "
                            + (tool.problem or "exécutable realesrgan-ncnn-vulkan introuvable."))
        self.tool, self.model, self.tile, self.gpu = tool, model, tile, gpu

    def upscale_dir(self, src: Path, dst: Path, cancel: threading.Event | None = None,
                    on_count: Callable[[int], None] | None = None) -> None:
        dst.mkdir(parents=True, exist_ok=True)
        cmd = [self.tool.path, "-i", str(src), "-o", str(dst), "-n", self.model,
               "-s", str(self.scale), "-f", "png", "-t", str(self.tile)]
        if self.gpu != "auto":
            cmd += ["-g", self.gpu]

        def poll() -> None:
            if on_count:
                on_count(sum(1 for _ in dst.glob("*.png")))

        run(cmd, cancel=cancel, poll=poll, what="Real-ESRGAN")
        n_in = sum(1 for _ in src.glob("*.png"))
        n_out = sum(1 for _ in dst.glob("*.png"))
        if n_out != n_in:
            raise ToolError(f"Real-ESRGAN n'a produit que {n_out} images sur {n_in} "
                            "(carte graphique compatible Vulkan requise ; essayez une taille de tuile plus petite).")
