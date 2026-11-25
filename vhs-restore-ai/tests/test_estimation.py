"""Durée gardée, extrapolation, et phrase de place avant de lancer."""
from vhs_restore import estimation


def test_duree_gardee_deduit_debut_fin_et_coupes():
    assert estimation.duree_gardee(100, 0, 0, []) == 100
    # fenêtre 10 s → 80 s, moins le passage 30 s → 40 s
    assert estimation.duree_gardee(100, 10, 80, [(30, 40)]) == 60
    # coupe hors de la fenêtre : elle ne change rien
    assert estimation.duree_gardee(100, 0, 50, [(80, 90)]) == 50
    # deux coupes qui se touchent ne sont comptées qu'une fois
    assert estimation.duree_gardee(100, 0, 0, [(10, 20), (15, 25)]) == 85
    # moins d'une demi-seconde : ignorée
    assert estimation.duree_gardee(100, 0, 0, [(10, 10.2)]) == 100


def test_extrapoler_depuis_dix_secondes():
    assert estimation.extrapoler(2.5, 10, 60) == 15
    assert estimation.extrapoler(0, 10, 60) == 0
    assert estimation.extrapoler(4, 0, 60) == 0


def test_phrase_duree_et_place():
    assert estimation.phrase_temps(7200) == "environ 2 heures"
    assert estimation.phrase_temps(30) == "moins d'une minute"
    texte = estimation.phrase(7200, 6e9, 120e9)
    assert texte == ("Durée estimée : environ 2 heures sur cet ordinateur. "
                     "Il faut environ 6 Go ; il en reste 120 Go.")
    manque = estimation.phrase(7200, 6e9, 2e9)
    assert manque.startswith("Il manque de la place")
    assert "Durée estimée" in manque
    assert manque.index("Il manque") < manque.index("Durée estimée")
