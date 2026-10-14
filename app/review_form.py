"""
Formulaire de validation ou de modification d'une annonce (un chat seul ou plusieurs chats à adopter ensemble).

Champs communs (identiques pour tous les chats d'une annonce, car ils rejoignent le même foyer
et partagent description et photos) : good_with_cats, good_with_children, outdoor_access, description, photos.
Champs propres à chaque chat : name, sex, birthdate, breed, fiv, felv.

Seuls les chats du statut traité (group.main_status) sont modifiés : en validation, un éventuel chat
déjà ACCEPTED lié à l'annonce n'est pas touché.
Les photos ne peuvent pas être ajoutées ici (page de création), seulement supprimées : le fichier est alors
effacé du disque s'il n'est plus utilisé par aucune fiche.
"""
import os
from datetime import date
from flask import current_app

# Champs oui / non : (nom, libellé, [(valeur formulaire, libellé), ...]).
# Entente et extérieur acceptent "Inconnu" (l'association peut ne pas savoir) ; FIV / FeLV sont obligatoires.
COMMON_BOOL = [
    ('good_with_cats', "Entente avec les chats", [('1', "Sociable"), ('0', "Non souhaité"), ('', "Inconnu")]),
    ('good_with_children', "Entente avec les enfants", [('1', "Sociable"), ('0', "Non recommandé"), ('', "Inconnu")]),
    ('outdoor_access', "Accès extérieur", [('1', "Nécessaire"), ('0', "Vie en intérieur"), ('', "Inconnu")]),
]
OWN_BOOL = [
    ('fiv', "Test FIV", [('0', "Négatif"), ('1', "Positif")]),
    ('felv', "Test FeLV", [('0', "Négatif"), ('1', "Positif")]),
]
SEX_CHOICES = [('MALE', "Mâle"), ('FEMALE', "Femelle")]
# Annonce de plusieurs chats uniquement
MODE_CHOICES = [('TOGETHER', "À adopter ensemble"), ('SEPARATE', "Adoptables séparément")]

COMMON_LABELS = dict([(f, l) for f, l, _ in COMMON_BOOL] + [('description', "Description"), ('photos', "Photos"),
                                                             ('adoption_mode', "Mode d'adoption")])


def bool_to_form(value):
    """None (pas encore renseigné) -> aucun choix coché."""
    return '' if value is None else ('1' if value else '0')


def form_to_bool(raw):
    """'1' -> True, '0' -> False, '' -> None (non connu)."""
    return {'1': True, '0': False}.get(raw)


def editable_cats(group):
    """Chats modifiés par le formulaire : ceux du statut traité (UNDER_REVIEW en validation, ACCEPTED en modification)."""
    return [c for c in group.cats if c.status == group.main_status]


def all_photos_of(cats):
    """Photos d'une liste de chats, sans doublon et dans l'ordre."""
    photos = []
    for c in cats:
        for p in (c.photos if isinstance(c.photos, list) else []):
            if p and p not in photos:
                photos.append(p)
    return photos


def all_photos(group):
    """Toutes les photos des chats modifiables de l'annonce, parmi lesquelles choisir."""
    return all_photos_of(editable_cats(group))


def photos_main_first(photos, main):
    """Ordre d'affichage du formulaire : la photo principale d'abord, les autres dans leur ordre."""
    return ([main] if main in photos else []) + [p for p in photos if p != main]


def initial_values(group):
    """
    Valeurs pré-remplies du formulaire.
    Les champs communs sont repris du chat de référence ; si les chats du groupe ont des valeurs
    différentes, le champ est signalé (la page de création devrait les rendre identiques).
    """
    cats = editable_cats(group)
    ref = cats[0]
    common = {f: bool_to_form(getattr(ref, f)) for f, _, _ in COMMON_BOOL}
    common['description'] = ref.description or ''
    common['adoption_mode'] = ref.adoption_mode or 'TOGETHER'
    common['photos_delete'] = []
    ref_photos = [p for p in (ref.photos if isinstance(ref.photos, list) else []) if p]
    common['photo_main'] = ref_photos[0] if ref_photos else ''

    differences = []
    for field in [f for f, _, _ in COMMON_BOOL] + ['description', 'photos', 'adoption_mode']:
        if len({repr(getattr(c, field) or None) for c in cats}) > 1:
            differences.append(COMMON_LABELS[field])

    own = {}
    for c in cats:
        own[c.id] = {
            'name': c.name or '',
            'sex': c.sex or '',
            'birthdate': c.birthdate.isoformat() if c.birthdate else '',
            'breed': c.breed or '',
            'fiv': bool_to_form(c.fiv),
            'felv': bool_to_form(c.felv),
        }
    return common, own, differences


def parse_form(form, group):
    """
    Lit et valide le formulaire soumis.
    Retourne (common, own, errors) : valeurs telles que saisies (pour réafficher le formulaire)
    et dictionnaire d'erreurs {clé de champ: message}.
    """
    errors = {}
    cats = editable_cats(group)

    common = {}
    for field, label, choices in COMMON_BOOL:
        common[field] = form.get(field, '')
        if common[field] not in [v for v, _ in choices]:
            errors[field] = "Choisissez une valeur."
    common['description'] = form.get('description', '').strip()
    if not common['description']:
        errors['description'] = "La description est obligatoire."

    # Mode d'adoption : choisi seulement pour une annonce de plusieurs chats, sinon inchangé
    if group.size > 1:
        common['adoption_mode'] = form.get('adoption_mode', '')
        if common['adoption_mode'] not in [v for v, _ in MODE_CHOICES]:
            errors['adoption_mode'] = "Choisissez une valeur."
    else:
        common['adoption_mode'] = cats[0].adoption_mode or 'TOGETHER'

    # Photos : celles du groupe, moins celles marquées pour suppression (jamais de chemin arbitraire)
    available = all_photos(group)
    common['photos_delete'] = [p for p in form.getlist('photos_delete') if p in available]
    common['photos'] = [p for p in available if p not in common['photos_delete']]
    # Photo principale choisie (cliquée) : placée en premier ; si elle est supprimée, la suivante prend sa place
    common['photo_main'] = form.get('photo_main', '')
    if common['photo_main'] in common['photos']:
        common['photos'].remove(common['photo_main'])
        common['photos'].insert(0, common['photo_main'])
    max_photos = current_app.config.get('MAX_PHOTOS', 6)
    if not common['photos']:
        errors['photos'] = "Gardez au moins une photo."
    elif len(common['photos']) > max_photos:
        errors['photos'] = f"{max_photos} photos maximum : supprimez-en."

    own = {}
    for c in cats:
        prefix = f"c{c.id}_"
        values = {
            'name': form.get(prefix + 'name', '').strip(),
            'sex': form.get(prefix + 'sex', ''),
            'birthdate': form.get(prefix + 'birthdate', '').strip(),
            'breed': form.get(prefix + 'breed', '').strip(),
            'fiv': form.get(prefix + 'fiv', ''),
            'felv': form.get(prefix + 'felv', ''),
        }
        own[c.id] = values

        if not values['name']:
            errors[prefix + 'name'] = "Le nom est obligatoire."
        elif len(values['name']) > 100:
            errors[prefix + 'name'] = "100 caractères maximum."
        if values['sex'] not in [v for v, _ in SEX_CHOICES]:
            errors[prefix + 'sex'] = "Choisissez le sexe."
        if not values['birthdate']:
            errors[prefix + 'birthdate'] = "La date de naissance est obligatoire (estimée si inconnue)."
        else:
            try:
                birth = date.fromisoformat(values['birthdate'])
                if birth > date.today():
                    errors[prefix + 'birthdate'] = "La date ne peut pas être dans le futur."
                elif birth.year < 1990:
                    errors[prefix + 'birthdate'] = "Date improbable."
            except ValueError:
                errors[prefix + 'birthdate'] = "Date invalide."
        if len(values['breed']) > 100:
            errors[prefix + 'breed'] = "100 caractères maximum."
        for field, _, choices in OWN_BOOL:
            if values[field] not in [v for v, _ in choices]:
                errors[prefix + field] = "Choisissez une valeur."

    return common, own, errors


def apply_values(group, common, own):
    """Écrit les valeurs validées dans les chats modifiables du groupe (sans commit)."""
    for c in editable_cats(group):
        for field, _, _ in COMMON_BOOL:
            setattr(c, field, form_to_bool(common[field]))
        c.description = common['description']
        c.adoption_mode = common['adoption_mode']
        c.photos = list(common['photos'])

        values = own[c.id]
        c.name = values['name']
        c.sex = values['sex']
        c.birthdate = date.fromisoformat(values['birthdate']) if values['birthdate'] else None
        c.breed = values['breed'] or 'Européen'
        c.fiv = form_to_bool(values['fiv'])
        c.felv = form_to_bool(values['felv'])


def delete_photo_files(photos, upload_folder, logger):
    """
    Supprime du disque les fichiers photo qui ne sont plus utilisés par aucune fiche (tous statuts).
    À appeler après le commit. Seuls les simples noms de fichier situés dans le dossier d'upload sont
    concernés (jamais de chemin ou d'URL arbitraire). Retourne la liste des fichiers non supprimés.
    """
    from app.models import AdoptionCat

    still_used = set()
    for c in AdoptionCat.query.filter(AdoptionCat.photos.isnot(None)).all():
        still_used.update(p for p in (c.photos if isinstance(c.photos, list) else []) if p)

    root = os.path.realpath(upload_folder)
    failed = []
    for photo in photos:
        if photo in still_used or os.path.basename(photo) != photo or photo.startswith('.'):
            continue
        path = os.path.realpath(os.path.join(root, photo))
        if os.path.dirname(path) != root:
            continue
        try:
            os.remove(path)
            logger.info("Photo supprimée : %s", path)
        except FileNotFoundError:
            pass
        except OSError:
            logger.exception("Impossible de supprimer la photo %s", path)
            failed.append(photo)
    return failed
