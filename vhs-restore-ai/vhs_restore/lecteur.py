"""Lecture locale dans le moniteur. La barre conserve le temps du film source."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QGuiApplication

try:
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
    from PySide6.QtMultimediaWidgets import QVideoWidget
except (ImportError, OSError):
    QMediaPlayer = None


def horloge(secondes: float) -> str:
    minutes, secondes = divmod(max(0, int(secondes)), 60)
    heures, minutes = divmod(minutes, 60)
    return f"{heures}:{minutes:02d}:{secondes:02d}" if heures else f"{minutes:02d}:{secondes:02d}"


class Lecteur(QObject):
    position = Signal(float)
    etat = Signal()
    echec = Signal(str)

    def __init__(self, parent: QObject) -> None:
        super().__init__(parent)
        self.video = self.media = self.audio = None
        self.mode = ""
        self.plages: tuple[tuple[float, float], ...] = ()
        self._saut: int | None = None
        self._reprendre: bool | None = None
        self._essais_reprise = 0
        self._attente = QTimer(self, singleShot=True, interval=8000)
        self._attente.timeout.connect(lambda: self._echec("Le lecteur n’a reçu aucune image à temps."))
        if QMediaPlayer is None:
            return
        self.video = QVideoWidget()
        self.video.setAspectRatioMode(Qt.KeepAspectRatio)
        self.video.setMinimumSize(0, 0)
        self.video.setStyleSheet("background-color: #0e1218;")
        self.video.setAccessibleName("Vidéo avec le son")

    def _initialiser(self) -> None:
        self.media = QMediaPlayer(self)
        # Les fabrications et tests hors écran vérifient le flux audio sans périphérique.
        if QGuiApplication.platformName() not in ("offscreen", "minimal"):
            self.audio = QAudioOutput(self)
            self.media.setAudioOutput(self.audio)
        self.media.setVideoOutput(self.video)
        self.media.positionChanged.connect(self._position_changee)
        self.media.durationChanged.connect(lambda _: self.etat.emit())
        self.media.playbackStateChanged.connect(self._etat_lecture)
        self.media.mediaStatusChanged.connect(self._etat_media)
        self.media.errorOccurred.connect(lambda _, raison: self._echec(raison))
        self.video.videoSink().videoFrameChanged.connect(self._image)

    @property
    def actif(self) -> bool:
        return bool(self.mode)

    @property
    def joue(self) -> bool:
        if self._reprendre is True:
            return True
        return self.media is not None and self.media.playbackState() == QMediaPlayer.PlayingState

    def ouvrir(self, chemin: Path, mode: str, *, debut: float = 0,
               plages: tuple[tuple[float, float], ...] = ()) -> None:
        self.fermer()
        if self.video is None:
            self.echec.emit("Le lecteur vidéo est indisponible.")
            return
        if self.media is None:
            self._initialiser()
        self.mode = mode
        self.plages = plages
        self._reprendre = None
        self._saut = round(1000 * debut) if debut > 0 else None
        self._attente.start()
        self.media.setSource(QUrl.fromLocalFile(str(chemin.resolve())))
        if self.actif:
            self.media.play()
            self.etat.emit()

    def remplacer(self, chemin: Path) -> None:
        """Ouvre un autre fichier à la même position. Lecture ou pause reste ce qu'elle était."""
        if self.mode != "original" or self.media is None or self.video is None:
            return
        jouait = self.media.playbackState() == QMediaPlayer.PlayingState or self._reprendre is True
        pos = self._saut if self._saut is not None else self.media.position()
        self._reprendre = jouait
        self._essais_reprise = 0
        self._saut = max(0, int(pos))
        self._attente.start()
        self.media.setSource(QUrl.fromLocalFile(str(Path(chemin).resolve())))
        if jouait:
            self.media.play()
        self.etat.emit()

    def basculer(self) -> None:
        if not self.actif or self.media is None:
            return
        if self.joue:
            if self._reprendre is True:
                self._reprendre = False
            self.media.pause()
        else:
            self._reprendre = None
            if self.media.mediaStatus() == QMediaPlayer.EndOfMedia:
                self.media.setPosition(0)
            self.media.play()

    def aller(self, secondes: float) -> bool:
        """Un clic sur la barre déplace le film original déjà ouvert."""
        if self.mode != "original" or self.media is None:
            return False
        self._saut = round(1000 * secondes)
        self._faire_saut()
        return True

    def fermer(self) -> None:
        if not self.actif:
            return
        self.mode = ""
        self.plages = ()
        self._saut = None
        self._reprendre = None
        self._essais_reprise = 0
        self._attente.stop()
        self.media.stop()
        self.media.setSource(QUrl())
        self.etat.emit()

    def _image(self, image) -> None:
        if self.actif and image.isValid() and self._saut is None:
            self._attente.stop()

    def _echec(self, raison: str) -> None:
        if self.actif:
            self.fermer()
            self.echec.emit(raison)

    def _faire_saut(self) -> None:
        if self._saut is not None and self.media.isSeekable():
            saut, self._saut = self._saut, None
            self.media.setPosition(saut)

    def _etat_media(self, etat) -> None:
        if not self.actif:
            return
        if etat in (QMediaPlayer.LoadedMedia, QMediaPlayer.BufferedMedia):
            if self._saut is not None and not self.media.isSeekable():
                self.etat.emit()
                return
            self._faire_saut()
            if self._reprendre is True and self.media.playbackState() != QMediaPlayer.PlayingState:
                self.media.play()
            elif self._reprendre is False:
                if self.media.playbackState() != QMediaPlayer.PausedState:
                    self.media.pause()
                self._reprendre = None
        if etat == QMediaPlayer.EndOfMedia and self.mode == "raccord":
            self.fermer()
        self.etat.emit()

    def _etat_lecture(self, etat) -> None:
        if self._reprendre is True and etat == QMediaPlayer.PlayingState:
            self._reprendre = None
        elif (self._reprendre is True and etat == QMediaPlayer.StoppedState
              and self._saut is None and self.actif and self._essais_reprise < 3):
            self._essais_reprise += 1
            self.media.play()
        self.etat.emit()

    def _position_changee(self, millisecondes: int) -> None:
        if not self.actif:
            return
        if self._saut is not None:
            self._faire_saut()
            return
        temps = millisecondes / 1000
        if self.mode == "comparaison" and self.plages and self.media.duration() > 0:
            debut, fin = self.plages[0]
            temps = debut + min(1.0, millisecondes / self.media.duration()) * (fin - debut)
        elif self.mode == "raccord" and self.plages:
            for debut, fin in self.plages:
                if temps < fin - debut:
                    temps += debut
                    break
                temps -= fin - debut
            else:
                temps = self.plages[-1][1]
        self.position.emit(temps)
