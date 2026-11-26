"""Tests rapides des mesures du banc n°18. Aucune image n'est téléchargée.

Depuis ``vhs-restore-ai/`` ::

    python essais/n18/test_mesures.py

Les 34 paires ΔE2000 sont le jeu publié par Sharma, Wu et Dalal,
« The CIEDE2000 Color-Difference Formula: Implementation Notes, Supplementary
Test Data, and Mathematical Observations », Color Research and Application,
vol. 30, n° 1, p. 21-30, 2005. Fichier :
https://hajim.rochester.edu/ece/sites/gsharma/ciede2000/dataNprograms/ciede2000testdata.txt
Chaque ligne : L a b de la référence, L a b de l'échantillon, ΔE2000.
"""
from __future__ import annotations

import math
import shutil
import sys
import unittest

import numpy as np

import banc

# Jeu de Sharma, copié chiffre pour chiffre (34 paires).
SHARMA = """
50.0000 2.6772 -79.7751 50.0000 0.0000 -82.7485 2.0425
50.0000 3.1571 -77.2803 50.0000 0.0000 -82.7485 2.8615
50.0000 2.8361 -74.0200 50.0000 0.0000 -82.7485 3.4412
50.0000 -1.3802 -84.2814 50.0000 0.0000 -82.7485 1.0000
50.0000 -1.1848 -84.8006 50.0000 0.0000 -82.7485 1.0000
50.0000 -0.9009 -85.5211 50.0000 0.0000 -82.7485 1.0000
50.0000 0.0000 0.0000 50.0000 -1.0000 2.0000 2.3669
50.0000 -1.0000 2.0000 50.0000 0.0000 0.0000 2.3669
50.0000 2.4900 -0.0010 50.0000 -2.4900 0.0009 7.1792
50.0000 2.4900 -0.0010 50.0000 -2.4900 0.0010 7.1792
50.0000 2.4900 -0.0010 50.0000 -2.4900 0.0011 7.2195
50.0000 2.4900 -0.0010 50.0000 -2.4900 0.0012 7.2195
50.0000 -0.0010 2.4900 50.0000 0.0009 -2.4900 4.8045
50.0000 -0.0010 2.4900 50.0000 0.0010 -2.4900 4.8045
50.0000 -0.0010 2.4900 50.0000 0.0011 -2.4900 4.7461
50.0000 2.5000 0.0000 50.0000 0.0000 -2.5000 4.3065
50.0000 2.5000 0.0000 73.0000 25.0000 -18.0000 27.1492
50.0000 2.5000 0.0000 61.0000 -5.0000 29.0000 22.8977
50.0000 2.5000 0.0000 56.0000 -27.0000 -3.0000 31.9030
50.0000 2.5000 0.0000 58.0000 24.0000 15.0000 19.4535
50.0000 2.5000 0.0000 50.0000 3.1736 0.5854 1.0000
50.0000 2.5000 0.0000 50.0000 3.2972 0.0000 1.0000
50.0000 2.5000 0.0000 50.0000 1.8634 0.5757 1.0000
50.0000 2.5000 0.0000 50.0000 3.2592 0.3350 1.0000
60.2574 -34.0099 36.2677 60.4626 -34.1751 39.4387 1.2644
63.0109 -31.0961 -5.8663 62.8187 -29.7946 -4.0864 1.2630
61.2901 3.7196 -5.3901 61.4292 2.2480 -4.9620 1.8731
35.0831 -44.1164 3.7933 35.0232 -40.0716 1.5901 1.8645
22.7233 20.0904 -46.6940 23.0331 14.9730 -42.5619 2.0373
36.4612 47.8580 18.3852 36.2715 50.5065 21.2231 1.4146
90.8027 -2.0831 1.4410 91.1528 -1.6435 0.0447 1.4441
90.9257 -0.5406 -0.9208 88.6381 -0.8985 -0.7239 1.5381
6.7747 -0.2908 -2.4247 5.8714 -0.0985 -2.2286 0.6377
2.0776 0.0795 -1.1350 0.9033 -0.0636 -0.5514 0.9082
"""


def _paires_sharma():
    for ligne in SHARMA.strip().splitlines():
        nombres = [float(x) for x in ligne.split()]
        yield nombres[:3], nombres[3:6], nombres[6]


class TestMesures(unittest.TestCase):
    def test_images_identiques(self):
        image = np.random.default_rng(0).integers(0, 256, (48, 64, 3), dtype=np.uint8)
        mesures = banc.mesurer(image, image.copy())
        self.assertTrue(math.isinf(mesures.psnr))
        self.assertEqual(mesures.ssim, 1.0)
        self.assertEqual(mesures.delta_e, 0.0)

    def test_aplat_identique(self):
        image = np.full((32, 32, 3), 128, np.uint8)
        mesures = banc.mesurer(image, image.copy())
        self.assertTrue(math.isinf(mesures.psnr))
        self.assertEqual(mesures.ssim, 1.0)
        self.assertEqual(mesures.delta_e, 0.0)

    def test_psnr_ecart_unitaire(self):
        a = np.zeros((16, 16, 3), np.uint8)
        b = np.ones_like(a)
        self.assertAlmostEqual(banc.psnr(a, b), 20.0 * math.log10(255.0), places=9)

    def test_ssim_diminue_si_les_images_different(self):
        a = np.zeros((32, 32, 3), np.uint8)
        b = np.full_like(a, 255)
        self.assertLess(banc.ssim(a, b), 0.2)

    def test_blanc_neutre_en_lab(self):
        lab = banc.rgb_vers_lab(np.array([[[255, 255, 255]]], dtype=np.uint8))
        self.assertAlmostEqual(float(lab[0, 0, 0]), 100.0, places=6)
        self.assertAlmostEqual(float(lab[0, 0, 1]), 0.0, places=6)
        self.assertAlmostEqual(float(lab[0, 0, 2]), 0.0, places=6)

    def test_delta_e_sharma(self):
        n = 0
        for lab1, lab2, attendu in _paires_sharma():
            obtenu = float(np.asarray(banc.delta_e_2000(lab1, lab2)))
            inverse = float(np.asarray(banc.delta_e_2000(lab2, lab1)))
            self.assertEqual(round(obtenu, 4), attendu, msg=f"paire {n}")
            self.assertEqual(round(inverse, 4), attendu, msg=f"symétrie {n}")
            n += 1
        self.assertEqual(n, 34)

    def test_references_libres_et_empreintes(self):
        refs = banc.lire_references()
        sujets = {ref.sujet for ref in refs}
        for attendu in ("intérieur sombre", "extérieur", "visages", "peau", "ciel"):
            self.assertIn(attendu, sujets)
        vus = set()
        for ref in refs:
            self.assertTrue(banc.licence_libre(ref.licence), ref.identifiant)
            self.assertEqual(len(ref.sha256), 64)
            self.assertNotIn(ref.sha256, vus)
            vus.add(ref.sha256)
            self.assertTrue(ref.url.startswith("https://upload.wikimedia.org/"))

    def test_pas_de_dependance_hors_numpy(self):
        for nom in ("onnxruntime", "onnx", "cv2", "skimage", "PIL"):
            self.assertNotIn(nom, sys.modules)

    def test_chaine_du_profil_naturel(self):
        chaine = banc.chaine_naturelle()
        self.assertEqual(
            chaine,
            "removegrain=m0=1:m1=1:m2=1,hqdn3d=3:5:4.5:7,"
            "eq=contrast=1.04:saturation=1.08,cas=strength=0.3,setsar=16/15,format=yuv420p",
        )

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg absent")
    def test_gamma_assombrit_et_noirs_releves(self):
        gris = np.full((32, 32, 3), 128, np.uint8)
        sombre = banc.degrader(gris, banc.ReglagesVHS(
            gamma=1.4, saturation=1, dominante_r=1, dominante_g=1, dominante_b=1,
            noirs=0, bruit_luma=0, bruit_chroma=0, definition=1, etalement=1, images=1))
        self.assertLess(float(sombre.images.mean()), 110)
        noir = np.zeros((32, 32, 3), np.uint8)
        releve = banc.degrader(noir, banc.ReglagesVHS(
            gamma=1, saturation=1, dominante_r=1, dominante_g=1, dominante_b=1,
            noirs=0.08, bruit_luma=0, bruit_chroma=0, definition=1, etalement=1, images=1))
        self.assertGreater(float(releve.images.mean()), 15)
        self.assertLess(float(releve.images.mean()), 30)
        self.assertEqual(len(np.unique(releve.images)), 1)

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg absent")
    def test_degradation_reproductible_et_bruit_temporel(self):
        image = np.zeros((32, 32, 3), np.uint8)
        image[:, :16] = (180, 40, 40)
        image[:, 16:] = (40, 40, 180)
        reglages = banc.ReglagesVHS(images=3, graine=4, definition=0.5, etalement=4,
                                    bruit_luma=10, bruit_chroma=15)
        a = banc.degrader(image, reglages)
        b = banc.degrader(image, reglages)
        self.assertTrue(np.array_equal(a.images, b.images))
        self.assertFalse(np.array_equal(a.images[0], a.images[1]))
        self.assertEqual(a.milieu, 1)
        self.assertFalse(np.array_equal(a.images[a.milieu], image))


if __name__ == "__main__":
    unittest.main(verbosity=1)
