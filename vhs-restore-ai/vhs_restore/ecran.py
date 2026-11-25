"""Disposition de la fenêtre de restauration. Les commandes gardent leurs signaux Qt."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFrame, QFormLayout, QGridLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)


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
    root.setContentsMargins(8, 4, 8, 4)
    root.setSpacing(3)
    root.addLayout(ligne(w.titre_fichier, w.details, w.autre, w.help_btn, w.theme_btn,
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
    av.addStretch()
    w.choisir = QPushButton("Choisir un film ou une photo")
    w.choisir.setMinimumHeight(54)
    w.choisir.clicked.connect(w._choose_file)
    av.addWidget(w.choisir)
    av.addWidget(w.s_folder)
    av.addWidget(w._recents_box)
    av.addStretch()
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
    w.options = QWidget()
    ov = QVBoxLayout(w.options)
    ov.setContentsMargins(0, 0, 0, 0)
    ov.setSpacing(3)
    droite.addWidget(w.options)
    w.sections = {}
    for nom in ("Qualité", "Couper le film", "Régler l'image", "Régler le son"):
        bouton = QPushButton(nom)
        bouton.setCheckable(True)
        zone = QScrollArea()
        zone.setWidgetResizable(True)
        zone.setFrameShape(QFrame.NoFrame)
        panneau = QWidget()
        disposition = QVBoxLayout(panneau)
        disposition.setContentsMargins(4, 2, 4, 2)
        disposition.setSpacing(3)
        disposition.setAlignment(Qt.AlignTop)
        zone.setWidget(panneau)
        bouton.setStyleSheet("text-align:left; padding:1px 8px;")
        ov.addWidget(bouton)
        ov.addWidget(zone, 1)
        zone.hide()
        w.sections[nom] = bouton, zone
        bouton.clicked.connect(lambda checked, n=nom: ouvrir(w, n if checked else None))

    def contenu(nom):
        return w.sections[nom][1].widget().layout()

    q = contenu("Qualité")
    q.addLayout(ligne(*w.profile_buttons.values()))
    q.addWidget(w.profile_desc)
    q.addWidget(w._row_res)
    q.addWidget(w.ai_check)
    q.addLayout(ligne(w.s_colorize, w.s_aide_couleur))
    q.addWidget(w.s_colorize_note)
    q.addLayout(ligne(w._out_btn, w.out_edit))
    q.addLayout(ligne(w.s_advice, w.s_aide_conseil))

    c = contenu("Couper le film")
    bornes = QGridLayout()
    for col, (libelle, champ) in enumerate((("Le film commence à", w.trim_start),
                                             ("Le film s'arrête à", w.trim_end))):
        bornes.addWidget(QLabel(libelle), 0, col)
        bornes.addWidget(champ, 1, col)
    c.addLayout(bornes)
    c.addWidget(w.barre)
    c.addLayout(ligne(w.s_guide_coupes, w.s_comment_faire))
    c.addLayout(ligne(w.s_couper, w.s_passage_annuler, w.trim_tout))
    durees = w.coupes_rapides
    c.addLayout(ligne(*durees))
    c.addWidget(w.s_passages_note)
    details_coupe = QPushButton("Détails des coupes…")
    dlg = QDialog(w)
    dlg.setWindowTitle("Détails des coupes")
    cv = QVBoxLayout(dlg)
    cv.addWidget(w.s_moment_heure)
    cv.addWidget(w.s_trim_note)
    cv.addLayout(ligne(w.trim_ici_debut, w.trim_ici_fin))
    cv.addLayout(ligne(w.trim_passage_deb, w.trim_passage_fin))
    cv.addWidget(w.s_trim_voir)
    for _, _, row in w._passage_lignes:
        cv.addWidget(row)
    details_coupe.clicked.connect(dlg.open)
    c.addWidget(details_coupe)

    im = contenu("Régler l'image")
    w.image_form = QFormLayout()
    for combo in (w.source_combo, w.scan_combo, w.dar_combo, w.cadence_combo):
        row = w.info_form.takeRow(combo)
        w.image_form.addRow(row.labelItem.widget(), combo)
    im.addLayout(w.image_form)
    for case, libelle in ((w.dust_check, "Poussières et rayures"), (w.tape_check, "Bruit de bande"),
                          (w.chroma_check, "Couleur des décrochages"), (w.dropout_check, "Taches isolées"),
                          (w.hq_check, "Débruitage haute qualité"), (w.stab_check, "Stabiliser l’image"),
                          (w.flicker_check, "Réduire le scintillement"), (w.rnnoise_check, "Souffle de la voix")):
        case.setToolTip(case.text() + "\n" + case.toolTip())
        case.setText(libelle)
    grid = QGridLayout()
    im.addLayout(grid)
    for index, widget in enumerate((w._row_deint, w._row_mask, w._row_chroma, w._row_edge)):
        grid.addWidget(widget, index, 0, 1, 2)
    for index, widget in enumerate((
                                    w.cast_check, w.hq_check, w.stab_check, w.flicker_check,
                                    w.dust_check, w.tape_check, w.dropout_check, w.chroma_check)):
        grid.addWidget(widget, 4 + index // 2, index % 2)

    son = contenu("Régler le son")
    moins, plus = QPushButton("−"), QPushButton("+")
    moins.setAccessibleName("Avancer le son")
    plus.setAccessibleName("Retarder le son")
    moins.clicked.connect(w.offset_spin.stepDown)
    plus.clicked.connect(w.offset_spin.stepUp)
    moins.setFixedWidth(42)
    plus.setFixedWidth(42)
    son.addLayout(ligne(QLabel("Décalage entre la voix et les lèvres"), moins, w.offset_spin, plus))
    w.ecouter = QPushButton("Écouter ces 10 secondes")
    w.ecouter.clicked.connect(w._ecouter_extrait)
    son.addWidget(w.ecouter)
    w.ai_check.setText("Amélioration IA")
    w.audio_check.setText("Nettoyer le son")
    son.addWidget(w.audio_check)
    w.plus_son = QPushButton("Plus de réglages…")
    w.plus_son.setCheckable(True)
    son.addWidget(w.plus_son)
    fin = QWidget()
    fg = QGridLayout(fin)
    fg.setContentsMargins(0, 1, 0, 1)
    fg.setSpacing(3)
    for i, wd in enumerate((w.wind_check, w.rnnoise_check, w.presence_check, w.declip_check)):
        fg.addWidget(wd, i // 2, i % 2)
    fg.addLayout(ligne(QLabel("Dérive"), w.drift_spin), 2, 0)
    fg.addWidget(w.mains_combo, 2, 1)
    w.mains_combo.setMinimumContentsLength(8)
    fg.addWidget(w.copy_combo, 3, 0, 1, 2)
    fg.addWidget(w.channel_combo, 4, 0, 1, 2)
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
    pied.addWidget(w.s_cancel)
    pied.addWidget(w.run_btn)
    w.run_btn.setMinimumHeight(52)
    w.s_status.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    for combo in page.findChildren(QComboBox):
        combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(8)
        combo.view().setMinimumWidth(combo.view().sizeHintForColumn(0) + 24)
    ouvrir(w, "Qualité")


def ouvrir(w, nom):
    w.s_compare.montrer_position = nom == "Couper le film"
    w.s_compare.update()
    for titre, (bouton, zone) in w.sections.items():
        bouton.setText(("▾  " if titre == nom else "▸  ") + titre)
        bouton.setAccessibleName(titre)
        bouton.setChecked(titre == nom)
        zone.setVisible(titre == nom)


def actualiser(w, charge, photo, occupe, termine):
    w.titre_fichier.setText(w.info.path.name if charge else "VHS Restore AI")
    w.titre_fichier.setToolTip(w.titre_fichier.text())
    w.gauche.setCurrentIndex(int(charge))
    w.choisir.setEnabled(not occupe)
    w.autre.setVisible(charge)
    w.autre.setEnabled(not occupe)
    w.options.setVisible(charge and not termine)
    w.options.setEnabled(not occupe)
    for nom in ("Couper le film", "Régler le son"):
        bouton, zone = w.sections[nom]
        if photo and bouton.isChecked():
            ouvrir(w, "Qualité")
        bouton.setVisible(not photo)
    w.s_progress.setVisible(occupe)
    w.ecouter.setEnabled(charge and w.info.has_audio and not occupe)
