# Image — timeline (note du chef)

Les bots n'ont pas pu être lancés. Le chef a tenu ce rôle. Aucun seuil de restauration n'est changé.

Filtre, balayage tff : `bwdif=mode=send_frame:parity=tff,scale=L:H:force_original_aspect_ratio=decrease:flags=fast_bilinear,pad=ceil(iw/2)*2:ceil(ih/2)*2,setsar=1`

Pas de `bwdif` si le film est progressif. bff : `parity=bff`.
720×576, SAR 16/15, hauteur 72 → 96×72 (4:3). Grande image : hauteur 144.
Ordre des couleurs vérifié sur quatre plages (rouge, vert, bleu, jaune) par `QImage`, sans dépendance nouvelle.
