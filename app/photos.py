"""
Enregistrement des photos ajoutées depuis le formulaire de validation / modification d'une annonce.
Même traitement et même nommage que la page de création d'eraFA (app/adoption.py), qui écrit dans le
même dossier : les deux doivent rester identiques.
"""
import os
import warnings
from app.helpers import slugify_name

PHOTO_MAX_SIDE = 1600       # plus grand côté après réduction (px)
PHOTO_JPEG_QUALITY = 82
PHOTO_MAX_PIXELS = 60_000_000   # images plus grandes refusées (sauf JPEG, décodé directement à taille réduite)


class PhotoError(Exception):
    pass


def save_adoption_photo(file_storage, dest_path):
    """
    Enregistre une photo envoyée en JPEG : redressée (orientation EXIF), réduite à PHOTO_MAX_SIDE et
    SANS aucune métadonnée (EXIF, dont la position GPS). Lève PhotoError si le fichier n'est pas une image acceptée.
    """
    from PIL import Image, ImageOps

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", Image.DecompressionBombWarning)
            img = Image.open(file_storage.stream)
            fmt = img.format
            if fmt not in ("JPEG", "MPO", "PNG", "WEBP"):
                raise PhotoError(f"format non pris en charge ({fmt or 'inconnu'}) : utilisez une photo JPEG, PNG ou WebP")

            if fmt in ("JPEG", "MPO"):
                # décodage directement à taille réduite : peu de mémoire même pour une très grande photo
                img.draft("RGB", (PHOTO_MAX_SIDE * 2, PHOTO_MAX_SIDE * 2))
            elif img.width * img.height > PHOTO_MAX_PIXELS:
                raise PhotoError(f"image trop grande ({img.width}x{img.height} px)")

            img = ImageOps.exif_transpose(img)
            if img.mode in ("RGBA", "LA", "P"):
                img = img.convert("RGBA")
                background = Image.new("RGB", img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1])
                img = background
            else:
                img = img.convert("RGB")

            img.thumbnail((PHOTO_MAX_SIDE, PHOTO_MAX_SIDE), Image.LANCZOS)
            # pas de paramètre exif : aucune métadonnée n'est écrite (seul le profil de couleur est conservé)
            img.save(dest_path, "JPEG", quality=PHOTO_JPEG_QUALITY, optimize=True, progressive=True,
                     icc_profile=img.info.get("icc_profile"))
    except PhotoError:
        raise
    except Exception as e:
        raise PhotoError("fichier illisible ou image trop grande") from e


def photo_filenames(folder, cat_name, cat_uuid, count):
    """Noms de fichier libres 'Nom_débutuuid_N.jpg' pour count photos."""
    base = f"{slugify_name(cat_name)}_{cat_uuid.split('-')[0]}"
    names, i = [], 1
    while len(names) < count:
        candidate = f"{base}_{i}.jpg"
        if not os.path.exists(os.path.join(folder, candidate)):
            names.append(candidate)
        i += 1
    return names


def save_photos(uploads, folder, cat_name, cat_uuid):
    """
    Enregistre les photos envoyées, nommées d'après le chat de référence de l'annonce.
    Retourne les noms de fichier ; en cas d'erreur, les fichiers déjà écrits sont supprimés et PhotoError est levée.
    """
    os.makedirs(folder, exist_ok=True)
    filenames = photo_filenames(folder, cat_name, cat_uuid, len(uploads))
    written = []
    try:
        for upload, filename in zip(uploads, filenames):
            path = os.path.join(folder, filename)
            save_adoption_photo(upload, path)
            written.append(path)
    except Exception:
        remove_files(written)
        raise
    return filenames


def remove_files(paths):
    for path in paths:
        try:
            os.remove(path)
        except OSError:
            pass
