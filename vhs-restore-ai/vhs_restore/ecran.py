"""Disposition de la fenêtre de restauration. Les commandes gardent leurs signaux Qt."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFrame, QFormLayout, QGridLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)

from . import theme
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
    min-height: 44px;
    max-height: 44px;
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
    iv.addWidget(CadreImage(w.s_compare), 1)
    iv.addWidget(w.s_segments)
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
    ov.setSpacing(3)
    droite.addWidget(w.options)
    w.sections = {}
    for nom in ("Qualité", "Couper le film", "Régler l'image", "Régler le son"):
        bouton = QPushButton(nom)
        bouton.setObjectName("section")
        bouton.setCheckable(True)
        bouton.setCursor(Qt.PointingHandCursor)
        bouton.setMinimumHeight(44)
        bouton.setMaximumHeight(44)
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
    c.addLayout(bornes)
    w.barre._compacte = True
    c.addWidget(w.barre)
    liste = QGridLayout()                        # passages enlevés, « Remettre » : sous la barre,
    liste.setHorizontalSpacing(12)               # deux par ligne (8 au plus)
    liste.setVerticalSpacing(2)
    for i, (_, _, row) in enumerate(w._passage_lignes):
        liste.addWidget(row, i // 2, i % 2)
    c.addLayout(liste)
    c.addLayout(ligne(w.s_guide_coupes, w.s_comment_faire))
    c.addLayout(ligne(w.s_couper, w.s_passage_annuler, w.trim_tout))
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
    pied.addWidget(w.run_btn)
    w.run_btn.setProperty("grand", True)
    w.run_btn.setMinimumSize(400, 64)
    w.run_btn.setMaximumSize(400, 64)
    w.run_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    w.s_status.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    for combo in page.findChildren(QComboBox):
        combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(8)
        combo.view().setMinimumWidth(combo.view().sizeHintForColumn(0) + 24)
    ouvrir(w, "Qualité")
    ajuster_son(w)
    ajuster_qualite(w)
    w.assistant = Assistant(w)
    w.assistant.hide()
    droite.insertWidget(droite.indexOf(w.options), w.assistant, 1)


def mode_libre(w, libre: bool) -> None:
    """« Réglages libres » : l'écran complet ; « Revenir à l'assistant » : pas à pas."""
    w.assistant.actif = not libre
    if libre:
        w.assistant.quitter()
        ouvrir(w, "Qualité")
    else:
        w.assistant.aller(w.assistant.pages.currentIndex())
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
        a.demarrer()
    w.libre.setVisible(charge and not termine)
    w.libre.blockSignals(True)
    w.libre.setChecked(not a.actif)
    w.libre.blockSignals(False)
    w.libre.setText("Revenir à l'assistant" if not a.actif else "Réglages libres")
    if guide:
        a.style_assistant()
        a.actualiser()
        w.run_btn.setEnabled(a.peut_lancer() and not occupe)
        for b in (a.retour, a.suivant, a.chercher, a.grand, a.voir):
            b.setEnabled(not occupe)
    phrase = phrase_son(w.offset_spin.value(), w.drift_spin.value()) if charge and not photo else ""
    w.s_note.setText("L'original est conservé." + (f" Correction du son : {phrase}." if phrase else ""))
    w.son_zero.setVisible(bool(phrase))
