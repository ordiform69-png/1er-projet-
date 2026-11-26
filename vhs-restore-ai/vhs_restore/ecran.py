"""Disposition de la fenêtre de restauration. Les commandes gardent leurs signaux Qt."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFrame, QFormLayout, QGridLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)

from . import icons, lecteur, lumiere, theme
from .assistant import Assistant, phrase_son


def regles(echelle: float) -> str:
    """Styles de l'écran unique. La feuille du mode simple les ajoute (elle remplace le reste)."""
    bas = theme._icon(f"chevron-down{theme.CHEVRONS}.svg")
    haut = theme._icon(f"chevron-up{theme.CHEVRONS}.svg")
    return f"""
QPushButton#section {{
    text-align: left;
    font-weight: 700;
    font-size: 14pt;
    min-height: 35px;
    max-height: 35px;
    padding: 0px 36px 0px 12px;
    border-radius: 10px;
    border: 1px solid {theme.BORD};
    background-color: {theme.CARTE};
    color: {theme.TEXTE};
    background-image: url("{bas}");
    background-repeat: no-repeat;
    background-position: center right;
    background-origin: content;
}}
QPushButton#section:checked {{
    background-color: {theme.TUILE_ACTIVE};
    border: 2px solid {theme.ACCENT};
    color: {theme.TEXTE};
    font-weight: 700;
    background-image: url("{haut}");
    background-repeat: no-repeat;
    background-position: center right;
    background-origin: content;
}}
QPushButton#action[grand="true"] {{
    font-size: 16pt;
    font-weight: 700;
    padding: 0px 16px;
}}
QPushButton#accueil {{
    font-size: 22pt;
    font-weight: 700;
    min-height: 120px;
    padding: 12px 18px;
    border-radius: 14px;
}}
QLabel#etapeAccueil {{
    font-size: {18 * echelle:.0f}pt;
    font-weight: 700;
    color: {theme.TEXTE};
    padding: 6px 0px;
}}
QLabel#bandeauOriginal {{
    font-size: {12 * echelle:.0f}pt;
    font-weight: 600;
    color: {theme.TEXTE};
    background: {theme.CARTE};
    border: 1px solid {theme.BORD};
    border-radius: 8px;
    padding: 4px 10px;
}}
QPushButton#lien {{
    font-size: 10pt;
    font-weight: 400;
    border: none;
    background: transparent;
    color: {theme.ACCENT};
    padding: 2px 6px;
    min-height: 0px;
}}
QPushButton[serre="true"] {{
    min-height: 40px;
}}
QLabel#nomReglage, QLabel#valeurReglage {{
    font-weight: 700;
}}
QCheckBox[large="true"], QPushButton[large="true"], QLabel[large="true"] {{
    font-size: {max(14, 10 * echelle):.0f}pt;
}}
"""


class _Formes:
    """Deux colonnes de réglages, avec le même setRowVisible qu'un QFormLayout."""

    def __init__(self) -> None:
        self._ou: dict = {}
        self._labels: dict = {}

    def add(self, form, label, widget) -> None:
        form.addRow(label, widget)
        self._ou[widget] = form

    def setRowVisible(self, widget, visible: bool) -> None:
        form = self._ou.get(widget)
        if form is not None:
            form.setRowVisible(widget, visible)
            return
        widget.setVisible(visible)
        label = getattr(self, "_labels", {}).get(widget)
        if label is not None:
            label.setVisible(visible)


def ligne(*widgets):
    box = QHBoxLayout()
    for widget in widgets:
        box.addWidget(widget)
    return box


class CadreImage(QWidget):
    """Centre le moniteur 4:3 dans la place laissée par les commandes."""
    def __init__(self, vue):
        super().__init__()
        self.vue = vue
        vue.setParent(self)
        vue.setMinimumSize(0, 0)
        self.setMinimumSize(180, 180)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        largeur = min(self.width(), (self.height() - 22) * 4 // 3 + 22)
        hauteur = (largeur - 22) * 3 // 4 + 22
        self.vue.setGeometry((self.width() - largeur) // 2, (self.height() - hauteur) // 2,
                             largeur, hauteur)


def _hauteur_texte(label) -> int:
    """Hauteur réelle d'un libellé qui revient à la ligne (pas la hauteur déjà écrasée)."""
    largeur = label.width() if label.width() > 80 else 640
    rect = label.fontMetrics().boundingRect(0, 0, largeur, 2000, int(Qt.TextWordWrap), label.text())
    return max(rect.height() + 2, 1)


def ajuster_qualite(w) -> None:
    """Tuiles plus grandes tant que le conseil d'analyse est caché.
    Avec le conseil, elles baissent juste assez pour que le texte reste entier."""
    if not getattr(w, "profile_buttons", None):
        return
    conseil = w.s_advice.isVisible()
    photo = bool(getattr(w, "is_photo", False))
    if photo:
        tuile = 112
    elif conseil:
        tuile = 80
    else:
        tuile = 108
    for bouton in w.profile_buttons.values():
        bouton.setMinimumHeight(tuile)
    if w.profile_desc.text():
        w.profile_desc.setMinimumHeight(_hauteur_texte(w.profile_desc))
    if w.s_colorize_note.isVisible() and w.s_colorize_note.text():
        w.s_colorize_note.setMinimumHeight(_hauteur_texte(w.s_colorize_note))


def ajuster_son(w) -> None:
    """« Régler le son » replié : commandes plus grandes. Déplié : taille d'origine,
    sinon la section ne tient plus dans l'écran à 125 %."""
    grand = not w.plus_son.isChecked()
    for bouton, haut in ((w.ecouter, 64), (w.plus_son, 56), (w.audio_check, 48),
                         (w.libelle_decalage, 0)):
        bouton.setProperty("large", True if grand else False)
        if haut:
            bouton.setMinimumHeight(haut if grand else 0)
        bouton.style().unpolish(bouton)
        bouton.style().polish(bouton)
    for bouton in (w._son_moins, w._son_plus):
        bouton.setMinimumHeight(52 if grand else 32)
        bouton.setProperty("large", True if grand else False)
        bouton.style().unpolish(bouton)
        bouton.style().polish(bouton)
    w.offset_spin.setMinimumHeight(52 if grand else 44)


def installer(w):
    page = QWidget()
    page.setObjectName("page")
    w.setCentralWidget(page)
    page.setAcceptDrops(True)
    page.installEventFilter(w._drop_filter)
    w._simple = page
    root = QVBoxLayout(page)
    w.titre_fichier = QLabel()
    w.titre_fichier.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    w.titre_fichier.setTextFormat(Qt.PlainText)
    w.titre_fichier.setObjectName("nomFilm")
    for bouton in (w.help_btn, w.theme_btn, *w._taille_btns.values()):
        bouton.setObjectName("commandeEntete")
    w.details = QPushButton("Détails du fichier")
    w.autre = QPushButton("Choisir un autre film")
    w.autre.clicked.connect(w._choose_file)
    w.libre = QPushButton("Réglages libres")
    w.libre.setObjectName("lien")
    w.libre.setFlat(True)
    w.libre.setCursor(Qt.PointingHandCursor)
    w.libre.setCheckable(True)
    w.libre.setToolTip("Tous les réglages sur un écran, sans l'assistant pas à pas.")
    w.libre.toggled.connect(lambda on: mode_libre(w, on))
    root.setContentsMargins(8, 4, 8, 4)
    root.setSpacing(3)
    root.addLayout(ligne(w.titre_fichier, w.libre, w.details, w.autre, w.help_btn, w.theme_btn,
                         *w._taille_btns.values()))
    root.itemAt(0).layout().setStretch(0, 1)

    dialog = QDialog(w)
    dialog.setWindowTitle("Détails du fichier")
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setWidget(w._card_info)
    dv = QVBoxLayout(dialog)
    dv.addWidget(w.s_info)
    dv.addWidget(scroll)
    dv.addWidget(w.tools_label)
    actions = QGridLayout()
    for i, b in enumerate((w.vides_btn, w.separer_btn, w.montage_btn, w.partager_btn,
                           w.nommer_btn, w.check_btn)):
        actions.addWidget(b, i // 2, i % 2)
    dv.addLayout(actions)
    fermer = QPushButton("Fermer")
    fermer.clicked.connect(dialog.accept)
    dv.addWidget(fermer)
    dialog.resize(850, 580)
    w.details.clicked.connect(dialog.open)

    milieu = QHBoxLayout()
    root.addLayout(milieu, 1)
    w.gauche = QStackedWidget()
    milieu.addWidget(w.gauche, 5)
    accueil = QWidget()
    av = QVBoxLayout(accueil)
    av.setContentsMargins(16, 8, 16, 8)
    av.addStretch(1)
    w.choisir = QPushButton("Choisir un film ou une photo")
    w.choisir.setObjectName("accueil")
    w.choisir.setMinimumHeight(120)
    w.choisir.setCursor(Qt.PointingHandCursor)
    w.choisir.clicked.connect(w._choose_file)
    av.addWidget(w.choisir)
    av.addSpacing(10)
    av.addWidget(w.s_folder)
    av.addWidget(w._recents_box)
    av.addStretch(1)
    w.gauche.addWidget(accueil)
    image = QWidget()
    iv = QVBoxLayout(image)
    w.bandeau_original = QLabel("Votre original n'est jamais modifié. Une copie sera créée.")
    w.bandeau_original.setObjectName("bandeauOriginal")
    w.bandeau_original.setWordWrap(True)
    w.bandeau_original.setAlignment(Qt.AlignCenter)
    iv.addWidget(w.bandeau_original)
    w.moniteur = QStackedWidget()
    w.s_compare.setMinimumSize(0, 0)
    w.moniteur.addWidget(w.s_compare)
    w.lecteur = lecteur.Lecteur(w)
    if w.lecteur.video is not None:
        w.moniteur.addWidget(w.lecteur.video)
    w.lecteur.position.connect(w._position_lecteur)
    w.lecteur.etat.connect(w._etat_lecteur)
    w.lecteur.echec.connect(w._echec_lecteur)
    w.cadre_moniteur = CadreImage(w.moniteur)
    iv.addWidget(w.cadre_moniteur, 1)
    w.barre._compacte = True
    iv.addWidget(w.barre)
    w.lire_film = QPushButton("Lire le film")
    w.lire_film.setObjectName("action")
    w.lire_film.setMinimumHeight(40)
    w.lire_film.clicked.connect(w._lire_film)
    w.heure_lecture = QLabel("00:00 / 00:00")
    w.heure_lecture.setAccessibleName("Temps écoulé et durée")
    w.revenir_image = QPushButton("Image fixe")
    w.revenir_image.setToolTip("Arrêter la lecture et revoir l’image fixe.")
    w.revenir_image.clicked.connect(w._arreter_lecture)
    w.revenir_image.hide()
    w.commandes_lecture = QWidget()
    commandes = ligne(w.lire_film, w.heure_lecture, w.revenir_image)
    commandes.setContentsMargins(0, 0, 0, 0)
    commandes.setStretch(0, 1)
    w.commandes_lecture.setLayout(commandes)
    iv.addWidget(w.commandes_lecture)
    iv.addWidget(w.s_segments)
    # écran de 1024 px : le champ peut se réduire (sa largeur conseillée vient du plus long
    # moment possible), et la liste des images aussi
    w.start_spin.setMinimumWidth(140)
    iv.addLayout(ligne(w.start_label, w.start_spin, w.still_combo))
    iv.addLayout(ligne(w.preview_btn, w.play_btn))
    w.gauche.addWidget(image)

    droite = QVBoxLayout()
    milieu.addLayout(droite, 7)
    w.etapes = QWidget()
    ev = QVBoxLayout(w.etapes)
    ev.setContentsMargins(24, 12, 16, 12)
    ev.setSpacing(14)
    ev.addStretch(1)
    for texte in ("1. Choisir le film", "2. Voir l'avant / après", "3. Lancer la restauration"):
        ligne_etape = QLabel(texte)
        ligne_etape.setObjectName("etapeAccueil")
        ligne_etape.setWordWrap(True)
        ev.addWidget(ligne_etape)
    ev.addStretch(2)
    w.etapes.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
    droite.addWidget(w.etapes, 1)
    w.options = QWidget()
    ov = QVBoxLayout(w.options)
    ov.setContentsMargins(0, 0, 0, 0)
    ov.setSpacing(2)
    droite.addWidget(w.options)
    w.sections = {}
    # cinq titres de 35 px : la section ouverte garde la même hauteur qu'avec quatre titres de 44 px
    for nom in ("Qualité", "Lumière et couleurs", "Couper le film", "Régler l'image", "Régler le son"):
        bouton = QPushButton(nom)
        bouton.setObjectName("section")
        bouton.setCheckable(True)
        bouton.setCursor(Qt.PointingHandCursor)
        bouton.setMinimumHeight(35)
        bouton.setMaximumHeight(35)
        bouton.setMinimumWidth(0)
        bouton.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        zone = QScrollArea()
        zone.setWidgetResizable(True)
        zone.setFrameShape(QFrame.NoFrame)
        panneau = QWidget()
        disposition = QVBoxLayout(panneau)
        disposition.setContentsMargins(4, 2, 4, 2)
        disposition.setSpacing(2)
        disposition.setAlignment(Qt.AlignTop)
        zone.setWidget(panneau)
        ov.addWidget(bouton)
        ov.addWidget(zone, 1)
        zone.hide()
        w.sections[nom] = bouton, zone
        bouton.clicked.connect(lambda checked, n=nom: ouvrir(w, n if checked else None))

    def contenu(nom):
        return w.sections[nom][1].widget().layout()

    q = contenu("Qualité")
    q.setSpacing(3)
    q.addLayout(ligne(*w.profile_buttons.values()))
    q.addWidget(w.profile_desc)
    q.addWidget(w._row_res)
    q.addWidget(w.ai_check)
    q.addLayout(ligne(w.s_colorize, w.s_aide_couleur))
    q.addWidget(w.s_colorize_note)
    q.addLayout(ligne(w._out_btn, w.out_edit))
    q.addLayout(ligne(w.s_advice, w.s_aide_conseil))
    for wd, haut in ((w.ai_check, 40), (w.s_colorize, 36),
                     (w.s_advice, 36), (w._out_btn, 44), (w.res_combo, 36)):
        if haut:
            wd.setMinimumHeight(haut)
        wd.setProperty("large", True)

    # mêmes valeurs que l'étape « Lumière et couleurs » de l'assistant
    w.panneau_lumiere = lumiere.Panneau(w.lumiere, guide=False)
    contenu("Lumière et couleurs").addWidget(w.panneau_lumiere)

    c = contenu("Couper le film")
    bornes = QGridLayout()
    bornes.setHorizontalSpacing(8)
    bornes.setVerticalSpacing(0)
    # « Ici » à côté de chaque champ : le moment choisi sur la barre devient le début ou la fin
    # (même ligne que le champ : la section tient sans défiler à 125 %)
    for col, (libelle, champ, ici, nom) in enumerate((
            ("Le film commence à", w.trim_start, w.trim_ici_debut, "Le film commence ici"),
            ("Le film s'arrête à", w.trim_end, w.trim_ici_fin, "Le film s'arrête ici"))):
        ici.setText("Ici")
        ici.setAccessibleName(nom)
        ici.setToolTip(nom + " : au moment choisi sur la barre (« Début de l'extrait »).")
        bornes.addWidget(QLabel(libelle), 0, col)
        bornes.addLayout(ligne(champ, ici), 1, col)
    w.bornes_coupe = QWidget()                   # un bloc : l'assistant le cache (écran complet seulement)
    w.bornes_coupe.setLayout(bornes)
    bornes.setContentsMargins(0, 0, 0, 0)
    c.addWidget(w.bornes_coupe)
    eloigner, rapprocher, tout_le_film = (
        QPushButton(texte) for texte in ("Zoom −", "Zoom +", "Tout le film")
    )
    for bouton, sens, nom in ((eloigner, -1, "Voir une plus grande partie du film"),
                               (rapprocher, 1, "Zoomer autour du moment choisi"),
                               (tout_le_film, 0, "Voir tout le film")):
        bouton.setMinimumHeight(38)
        bouton.setToolTip(nom)
        bouton.clicked.connect(lambda _coche=False, sens=sens: w.barre.zoomer(sens))
    w.barre.zoom_change.connect(lambda possible, _agrandie: rapprocher.setEnabled(possible))
    w.barre.zoom_change.connect(lambda _zoom, agrandie: eloigner.setEnabled(agrandie))
    w.barre.zoom_change.connect(lambda _zoom, agrandie: tout_le_film.setEnabled(agrandie))
    w.barre.zoomer()
    zoom = ligne(eloigner, rapprocher, tout_le_film)
    zoom.addStretch(1)
    w.chercher_neige_libre = QPushButton("Chercher la neige…")
    w.chercher_neige_libre.setMinimumHeight(38)
    w.chercher_neige_libre.clicked.connect(lambda: w.assistant._chercher_vides())
    zoom.addWidget(w.chercher_neige_libre)
    c.addLayout(zoom)
    w.enlever_passage = QPushButton()
    w.enlever_passage.setMinimumHeight(38)
    w.enlever_passage.clicked.connect(w._enlever_passage_vide)
    w.enlever_tous_passages = QPushButton("Tout enlever")
    w.enlever_tous_passages.setMinimumHeight(38)
    w.enlever_tous_passages.setToolTip("Enlever tous les passages bleus de la copie.")
    w.enlever_tous_passages.clicked.connect(w._tout_enlever_vides)

    def afficher_passage_vide():
        passage = w.barre.passage_vide
        w.enlever_passage.setVisible(passage is not None)
        w.enlever_tous_passages.setVisible(sum(1 for _ in w.barre.passages_proposes()) > 1)
        if passage is not None:
            debut, fin = (lecteur.horloge(round(t)).removeprefix("0") for t in w.barre.bornes_passage(passage))
            w.enlever_passage.setText(f"Enlever {debut} – {fin}")
            w.enlever_passage.setToolTip(passage.genre.capitalize())

    w.barre.passage_choisi.connect(afficher_passage_vide)
    c.addLayout(ligne(w.enlever_passage, w.enlever_tous_passages))
    afficher_passage_vide()
    liste = QGridLayout()                        # passages enlevés, « Remettre » : sous la barre,
    liste.setHorizontalSpacing(12)               # deux par ligne (8 au plus)
    liste.setVerticalSpacing(2)
    for i, (_, _, row) in enumerate(w._passage_lignes):
        liste.addWidget(row, i // 2, i % 2)
    c.addLayout(liste)
    c.addLayout(ligne(w.s_guide_coupes, w.s_comment_faire))
    w.verifier_coupe = QPushButton("Vérifier la coupe")
    w.verifier_coupe.setToolTip("Lire quelques secondes autour de la coupe la plus proche du curseur.")
    w.verifier_coupe.clicked.connect(w._verifier_coupe)
    w.verifier_coupe.setEnabled(False)
    c.addLayout(ligne(w.s_couper, w.s_passage_annuler, w.trim_tout))
    c.addWidget(w.verifier_coupe)
    durees = w.coupes_rapides
    c.addLayout(ligne(*durees))
    c.addWidget(w.s_passages_note)
    # ancienne façon en deux boutons, l'heure du moment, « Montrer ce début », et la phrase sur
    # le début et la fin : doublons de « Couper ici », de l'image de gauche, de l'aperçu et de la
    # phrase sous les boutons. Gardés (tests, raccourcis), cachés.
    cache = QWidget()
    cv = QVBoxLayout(cache)
    for wd in (w.s_moment_heure, w.trim_passage_deb, w.trim_passage_fin, w.s_trim_voir, w.s_trim_note):
        cv.addWidget(wd)
    cache.hide()
    c.addWidget(cache)
    w._coupe_cachee = cache

    im = contenu("Régler l'image")
    pleine = QFormLayout()
    pleine.setVerticalSpacing(2)
    pleine.setContentsMargins(0, 0, 0, 0)
    couple = QHBoxLayout()
    couple.setSpacing(8)
    w.image_form = _Formes()
    for combo in (w.source_combo, w.scan_combo, w.dar_combo, w.cadence_combo):
        row = w.info_form.takeRow(combo)
        label = row.labelItem.widget()
        label.setMinimumWidth(0)
        combo.setMinimumWidth(0)
        combo.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        if combo in (w.scan_combo, w.dar_combo):
            couple.addWidget(label)
            couple.addWidget(combo, 1)
            w.image_form._labels[combo] = label
        else:
            w.image_form.add(pleine, label, combo)
    im.addLayout(pleine)
    im.addLayout(couple)
    for case, libelle in ((w.dust_check, "Poussières et rayures"), (w.tape_check, "Bruit de bande"),
                          (w.chroma_check, "Couleur des décrochages"), (w.dropout_check, "Taches isolées"),
                          (w.hq_check, "Débruitage haute qualité"), (w.stab_check, "Stabiliser l’image"),
                          (w.flicker_check, "Réduire le scintillement"), (w.rnnoise_check, "Souffle de la voix")):
        case.setToolTip(case.text() + "\n" + case.toolTip())
        case.setText(libelle)
    grid = QGridLayout()
    grid.setHorizontalSpacing(8)
    grid.setVerticalSpacing(0)
    im.addLayout(grid)
    for widget in (w._row_deint, w._row_mask, w._row_edge, w._row_chroma):
        widget.setMinimumWidth(0)
    grid.addWidget(w._row_deint, 0, 0, 1, 2)
    grid.addWidget(w._row_mask, 1, 0, 1, 2)
    # Libellé au-dessus du champ : côte à côte, la somme des deux lignes
    # dépassait la colonne à 150 % (défilement horizontal interdit).
    for row in (w._row_edge, w._row_chroma):
        lay = row.layout()
        lay.setSpacing(0)
        champs = []
        while lay.count():
            item = lay.takeAt(0)
            if item.widget() is not None:
                champs.append(item.widget())
        pile = QVBoxLayout()
        pile.setSpacing(0)
        pile.setContentsMargins(0, 0, 0, 0)
        for champ in champs:
            champ.setMinimumWidth(0)
            pile.addWidget(champ)
        host = QWidget()
        host.setLayout(pile)
        host.setMinimumWidth(0)
        lay.addWidget(host)
    grid.addWidget(w._row_edge, 2, 0)
    grid.addWidget(w._row_chroma, 2, 1)
    for index, widget in enumerate((
                                    w.cast_check, w.hq_check, w.stab_check, w.flicker_check,
                                    w.dust_check, w.tape_check, w.dropout_check, w.chroma_check)):
        widget.setMinimumWidth(0)
        grid.addWidget(widget, 3 + index // 2, index % 2)

    son = contenu("Régler le son")
    moins, plus = QPushButton("−"), QPushButton("+")
    moins.setAccessibleName("Avancer le son")
    plus.setAccessibleName("Retarder le son")
    moins.clicked.connect(w.offset_spin.stepDown)
    plus.clicked.connect(w.offset_spin.stepUp)
    moins.setFixedWidth(48)
    plus.setFixedWidth(48)
    w._son_moins, w._son_plus = moins, plus
    w.libelle_decalage = QLabel("Décalage entre la voix et les lèvres")
    w.libelle_decalage.setWordWrap(True)          # deux lignes sur un écran de 1024 px
    son.addLayout(ligne(w.libelle_decalage, moins, w.offset_spin, plus))
    w.ecouter = QPushButton("Écouter ces 10 secondes")
    w.ecouter.clicked.connect(w._ecouter_extrait)
    son.addWidget(w.ecouter)
    w.ai_check.setText("Amélioration IA")
    w.audio_check.setText("Nettoyer le son")
    son.addWidget(w.audio_check)
    w.plus_son = QPushButton("Plus de réglages…")
    w.plus_son.setCheckable(True)
    son.addWidget(w.plus_son)
    w.plus_son.toggled.connect(lambda _on: ajuster_son(w))
    fin = QWidget()
    fg = QGridLayout(fin)
    fg.setContentsMargins(0, 1, 0, 1)
    fg.setSpacing(3)
    for i, wd in enumerate((w.wind_check, w.rnnoise_check, w.presence_check, w.declip_check)):
        fg.addWidget(wd, i // 2, i % 2)
    fg.addLayout(ligne(QLabel("Dérive"), w.drift_spin), 2, 0)
    fg.addWidget(w.mains_combo, 2, 1)
    w.mains_combo.setMinimumContentsLength(8)
    fg.addWidget(w.copy_combo, 3, 0)
    fg.addWidget(w.channel_combo, 3, 1)
    son.addLayout(ligne(w.s_hear_orig, w.s_hear_new))
    son.addWidget(fin)
    fin.hide()
    w.plus_son.toggled.connect(fin.setVisible)
    droite.addWidget(w.s_fini)
    fv = w.s_fini.layout()
    boutons = QGridLayout()
    for i, b in enumerate((w.s_voir, w.s_ouvrir, w.s_nommer, w.s_partager,
                           w.s_separer, w.s_vides, w.s_montage, w.s_autre)):
        boutons.addWidget(b, i // 2, i % 2)
    fv.insertLayout(1, boutons)
    w._fini_boutons = boutons
    w.s_fini_texte.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
    w.s_fini_texte.setMinimumHeight(48)
    w.s_fini_texte.setAlignment(Qt.AlignTop | Qt.AlignLeft)
    w.s_fini_texte.setMaximumHeight(100)
    bilan = QPushButton("Lire le bilan complet")
    bilan.clicked.connect(w._afficher_bilan)
    fv.addWidget(bilan)
    w.bilan = bilan
    w.s_note.setText("L'original est conservé.")
    pied = QHBoxLayout()
    root.addLayout(pied)
    etat = QVBoxLayout()
    pied.addLayout(etat, 1)
    etat.addWidget(w.s_note)
    etat.addWidget(w.s_status)
    etat.addWidget(w.s_progress)
    w.son_zero = QPushButton("Remettre le son à zéro")
    w.son_zero.setToolTip("Enlève le décalage et la dérive du son réglés pour ce film.")
    w.son_zero.clicked.connect(lambda: son_a_zero(w))
    w.son_zero.hide()
    pied.addWidget(w.son_zero)
    pied.addWidget(w.s_cancel)
    w.note_lancer = QLabel()
    w.note_lancer.setObjectName("note")
    w.note_lancer.setWordWrap(True)
    w.note_lancer.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    w.note_lancer.setMaximumWidth(260)
    w.note_lancer.hide()
    pied.addWidget(w.note_lancer)
    pied.addWidget(w.run_btn)
    w.run_btn.setIcon(icons.icon("etincelle", theme.VERT_TEXTE, 24))
    w.run_btn.setProperty("grand", True)
    w.run_btn.setMinimumSize(400, 64)
    w.run_btn.setMaximumSize(400, 64)
    w.run_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    w.s_status.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    for combo in page.findChildren(QComboBox):
        combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(8)
        combo.view().setMinimumWidth(combo.view().sizeHintForColumn(0) + 24)
    w.still_combo.setMinimumContentsLength(6)      # « Image 2/3 » : assez court pour 1024 px
    ouvrir(w, "Qualité")
    ajuster_son(w)
    ajuster_qualite(w)
    w.assistant = Assistant(w)
    w.assistant.hide()
    droite.insertWidget(droite.indexOf(w.options), w.assistant, 1)
    w._serre = None                   # l'assistant existe maintenant : l'adapter à la hauteur
    adapter(w)


BAS = 600       # hauteur utile sous laquelle l'écran se resserre


def texte_selon_ecran(largeur: int, hauteur: int) -> int:
    """Taille du texte au premier lancement, d'après l'écran (hors barre des tâches, en points
    logiques). Grand écran sans zoom de Windows (1920 × 1080 à 100 % : 1920 × 1032), le texte
    normal y paraît petit : 125 %. Très grand (2560 × 1440 à 100 %, 4K à 150 %) : 150 %. Écran du
    père (1920 × 1080 à 150 % : 1280 × 688) et plus petits : 100 %. Les boutons A−, A, A+
    changent ensuite ce choix, qui est gardé."""
    if largeur >= 2400 and hauteur >= 1300:
        return 150
    if largeur >= 1700 and hauteur >= 950:
        return 125
    return 100


def adapter(w) -> None:
    """Appelé quand la fenêtre change de taille. Écran bas : bouton « Lancer » et boutons de
    l'assistant moins hauts, petites images de l'étape 1 réduites."""
    plafond = w.taille_texte_max()
    if getattr(w, "_texte_plafond", plafond) != plafond and hasattr(w, "_texte_voulu"):
        w.set_taille_texte(w._texte_voulu, annoncer=False)     # écran agrandi ou réduit
        return                                                  # (et rappelle adapter)
    serre = w.height() < BAS
    if getattr(w, "_serre", None) == serre:
        return
    w._serre = serre
    w.cadre_moniteur.setMinimumHeight(112 if serre else 180)
    h = 48 if serre else 64
    w.run_btn.setMinimumHeight(h)
    w.run_btn.setMaximumHeight(h)
    a = getattr(w, "assistant", None)
    if a is not None:
        a.serrer(serre)
    # la feuille de style impose 58 px aux boutons verts : levée sur un écran bas
    for b in (w.run_btn, *((a.suivant, a.retour) if a is not None else ())):
        b.setProperty("serre", serre)
        b.style().unpolish(b)
        b.style().polish(b)


def mode_libre(w, libre: bool) -> None:
    """« Réglages libres » : l'écran complet ; « Revenir à l'assistant » : pas à pas."""
    w.assistant.actif = not libre
    if libre:
        w.assistant.quitter()
        ouvrir(w, "Qualité")
    else:
        w.assistant.aller(w.assistant._etape())
    w._update_state()


def son_a_zero(w) -> None:
    for sp in (w.offset_spin, w.drift_spin):
        sp.setValue(0)
    for _lab, _e, champ in w.assistant.rangs_son.values():
        champ.setValue(0)
    w._update_state()


def ouvrir(w, nom):
    w.s_compare.montrer_position = nom == "Couper le film"
    w.s_compare.update()
    for titre, (bouton, zone) in w.sections.items():
        bouton.setText(titre)
        bouton.setAccessibleName(titre)
        bouton.setChecked(titre == nom)
        zone.setVisible(titre == nom)


def actualiser(w, charge, photo, occupe, termine):
    w.titre_fichier.setText(w.info.path.name if charge else "VHS Restore AI")
    w.titre_fichier.setToolTip(w.titre_fichier.text())
    w.gauche.setCurrentIndex(int(charge))
    film = charge and not photo
    w.barre.setVisible(film)
    w.barre.setEnabled(film and not occupe)
    w.commandes_lecture.setVisible(film)
    w.lire_film.setEnabled(film and not occupe)
    w.verifier_coupe.setEnabled(film and not occupe and w._a_une_coupe())
    w.enlever_passage.setEnabled(film and not occupe)
    w.enlever_tous_passages.setEnabled(film and not occupe)
    w.choisir.setEnabled(not occupe)
    w.details.setVisible(charge)
    w.etapes.setVisible(not charge and not termine)
    w.autre.setVisible(charge)
    w.autre.setEnabled(not occupe)
    a = getattr(w, "assistant", None)
    guide = a is not None and charge and not termine and a.actif
    # jamais l'assistant et l'écran complet ensemble, même un instant : la fenêtre grandirait
    libre = charge and not termine and not guide
    for cache, montre in ((a, w.options), (w.options, a)):   # d'abord cacher, puis montrer
        if cache is not None and not (guide if cache is a else libre):
            cache.setVisible(False)
    w.options.setVisible(libre)
    if a is not None:
        a.setVisible(guide)
    w.options.setEnabled(not occupe)
    for nom in ("Couper le film", "Régler le son"):
        bouton, zone = w.sections[nom]
        if photo and bouton.isChecked():
            ouvrir(w, "Qualité")
        bouton.setVisible(not photo)
    w.s_progress.setVisible(occupe)
    w.ecouter.setEnabled(charge and w.info.has_audio and not occupe)
    if a is None:
        return
    if charge and w.info is not a._info:
        # nouveau film : décalage et dérive du son sont propres à chaque cassette, on repart de zéro
        a._info = w.info
        for sp in (w.offset_spin, w.drift_spin):
            sp.blockSignals(True)
            sp.setValue(0)
            sp.blockSignals(False)
        w.lumiere.nouveau_film()
        a.demarrer()
    w.lumiere.actualiser()
    w.libre.setVisible(charge and not termine)
    w.libre.blockSignals(True)
    w.libre.setChecked(not a.actif)
    w.libre.blockSignals(False)
    w.libre.setText("Revenir à l'assistant" if not a.actif else "Réglages libres")
    if not guide:
        w.note_lancer.hide()
    if occupe and getattr(w, "_job", "") == "export":
        w.run_btn.setText("Restauration en cours…")
        w.run_btn.setToolTip("")
    elif not occupe:
        w.run_btn.setText("Lancer la restauration")
    if guide:
        a.style_assistant()
        a.actualiser()
        w.run_btn.setEnabled(a.peut_lancer() and not occupe)
        if not occupe and not a.peut_lancer():
            w.note_lancer.setText(a.phrase_attente())
            w.note_lancer.show()
            w.run_btn.setToolTip(a.phrase_attente())
        else:
            w.note_lancer.hide()
            w.run_btn.setToolTip("")
        for b in (a.retour, a.suivant, a.chercher, a.grand, a.voir):
            b.setEnabled(not occupe)
    phrase = phrase_son(w.offset_spin.value(), w.drift_spin.value()) if charge and not photo else ""
    w.s_note.setText("L'original est conservé." + (f" Correction du son : {phrase}." if phrase else ""))
    w.son_zero.setVisible(bool(phrase))
