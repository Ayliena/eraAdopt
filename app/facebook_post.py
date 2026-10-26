"""
Publication des annonces sur la page Facebook : texte du post, photos, et suivi du post (table adoption_cat_posts).

Le texte est toujours reconstruit entièrement à partir des chats du post (jamais modifié morceau par morceau) :
- état de l'annonce : « À l'adoption », puis « Adopté(e)(s) » quand tous ses chats sont archivés ;
- une ligne courte par chat (sexe, âge, couleur ; « (adopté) » pour un chat archivé d'une annonce multiple),
  puis la description, les infos communes et le lien vers l'annonce (ou vers l'accueil une fois adoptés).
Les chats d'un post sont ceux qui pointent vers son identifiant : un chat archivé reste dans le post (adopté).
"""
from datetime import date
from flask import current_app, request, url_for
from app import db
from app.models import AdoptionCat, AdoptionCatPost, join_names_fr, photo_public_url
from app import facebook

NETWORK = 'FACEBOOK'


class PostGone(facebook.FacebookError):
    """Le post n'existe plus sur Facebook (supprimé à la main) : l'annonce n'y est plus rattachée."""

# valeurs courtes : le libellé « Autres chats » est déjà en début de ligne
OTHER_CATS = {'NONE': "non", 'OK': "OK", 'REQUIRED': "nécessaires"}
CHILDREN = {True: "Sociable", False: "Non recommandé"}
OUTDOOR = {'INDOOR': "Intérieur uniquement", 'OPTIONAL': "Sortie possible", 'REQUIRED': "Sortie nécessaire"}
# même emoji pour les deux modes, différent du 🐾 de la ligne d'état juste au-dessus
MODE = {'TOGETHER': "À adopter ensemble 🐱", 'SEPARATE': "Adoptables séparément 🐱"}


# --- Suivi des posts

def rows_of(cats):
    """Lignes de suivi Facebook des chats donnés."""
    uuids = [c.uuid for c in cats]
    if not uuids:
        return []
    return AdoptionCatPost.query.filter(AdoptionCatPost.cat_uuid.in_(uuids), AdoptionCatPost.network == NETWORK).all()


def listing_post(cats):
    """
    État Facebook d'une annonce : (post_id, post_url, last_error).
    post_id None et last_error renseigné : la première publication a échoué. Tout à None : jamais publiée.
    """
    rows = rows_of(cats)
    with_post = [r for r in rows if r.post_id]
    if with_post:
        row = max(with_post, key=lambda r: r.updated_at)
        return row.post_id, row.post_url, row.last_error
    failed = [r for r in rows if r.last_error]
    if failed:
        return None, None, max(failed, key=lambda r: r.updated_at).last_error
    return None, None, None


def post_cats(post_id):
    """Chats d'un post (tous statuts), du plus ancien au plus récent."""
    uuids = [r.cat_uuid for r in AdoptionCatPost.query.filter_by(post_id=post_id, network=NETWORK).all()]
    return AdoptionCat.query.filter(AdoptionCat.uuid.in_(uuids)).order_by(AdoptionCat.id).all() if uuids else []


def save_rows(cats, post_id=None, post_url=None, error=None):
    """Enregistre l'état Facebook des chats (crée ou met à jour leur ligne) ; sans commit."""
    existing = {r.cat_uuid: r for r in rows_of(cats)}
    for c in cats:
        row = existing.get(c.uuid) or AdoptionCatPost(cat_uuid=c.uuid, network=NETWORK)
        if post_id:
            row.post_id, row.post_url = post_id, post_url
        row.last_error = error[:500] if error else None
        db.session.add(row)


# --- Texte du post

def site_url(path):
    """Adresse publique d'une page ou d'un fichier du site (SITE_URL dans la config, sinon l'adresse de la requête)."""
    base = current_app.config.get('SITE_URL') or request.url_root
    return base.rstrip('/') + path


def is_adopted(cat):
    return cat.status == 'ARCHIVED'


def _agree(word, cats):
    """'adopté' accordé : féminin si toutes des femelles, pluriel si plusieurs."""
    female = all(c.sex == 'FEMALE' for c in cats)
    agreed = word + ('e' if female else '') + ('s' if len(cats) > 1 else '')
    return agreed.upper() if word.isupper() else agreed


def _test(value):
    return "Positif" if value else "Négatif"


def _common_lines(ref):
    """Infos communes à l'annonce (les valeurs inconnues sont omises)."""
    lines = []
    if ref.good_with_cats in OTHER_CATS:
        lines.append(f"🐈 Autres chats : {OTHER_CATS[ref.good_with_cats]}")
    if ref.good_with_children in CHILDREN:
        lines.append(f"👶 Enfants : {CHILDREN[ref.good_with_children]}")
    if ref.outdoor_access in OUTDOOR:
        lines.append(f"🏡 Extérieur : {OUTDOOR[ref.outdoor_access]}")
    return lines


def _short_age(birthdate):
    """Âge court pour le post : en mois avant 1 an ('4 mois'), en années ensuite ('2 ans')."""
    today = date.today()
    months = (today.year - birthdate.year) * 12 + today.month - birthdate.month - (today.day < birthdate.day)
    if months < 1:
        return "moins d'un mois"
    if months < 12:
        return f"{months} mois"
    years = months // 12
    return f"{years} an{'s' if years > 1 else ''}"


def _color_phrase(color):
    """
    Couleur en fin de phrase : 'Tigré' -> 'au pelage tigré', 'Noir et blanc, poil long' -> 'au pelage noir et
    blanc et au poil long'. « Pelage » (masculin) évite d'accorder la couleur avec le sexe du chat.
    Un texte saisi autrement par un admin est repris tel quel après « au pelage ».
    """
    main, _, rest = color.strip().partition(', ')
    hair = rest if rest.startswith('poil ') else None
    if rest and not hair:
        main = color.strip()
    if main.startswith('Ecaille'):
        main = 'é' + main[1:]  # « Ecaille de tortue » d'eraFA, sans accent
    main = main[:1].lower() + main[1:]
    return f"au pelage {main}" + (f" et au {hair}" if hair else "")


def _cat_summary(cat):
    """'mâle de 2 ans au pelage noir plastron blanc et au poil mi-long' (couleur omise si inconnue)."""
    summary = f"{cat.sex_label.lower()} de {_short_age(cat.birthdate)}"
    return f"{summary} {_color_phrase(cat.color)}" if cat.color and cat.color.strip() else summary


def build_text(cats):
    """Texte du post pour les chats donnés (tous ceux du post, disponibles ou adoptés)."""
    cats = sorted(cats, key=lambda c: c.id)
    available = [c for c in cats if not is_adopted(c)]
    ref = (available or cats)[0]

    # État de l'annonce (un seul emoji, en fin de ligne)
    if not available:
        lines = [f"{_agree('ADOPTÉ', cats)} ! 🎉"]
    elif len(cats) == 1:
        lines = ["À L'ADOPTION 🐾"]
    else:
        lines = [f"À L'ADOPTION : {join_names_fr(c.name for c in available).upper()} 🐾"]
        # mode d'adoption : seulement s'il reste au moins 2 chats à adopter (sinon il n'a plus de sens)
        if len(available) > 1 and ref.adoption_mode in MODE:
            lines.append(MODE[ref.adoption_mode])
    lines.append("")

    # Une ligne par chat
    if len(cats) == 1:
        lines.append(f"{cats[0].name}, {_cat_summary(cats[0])}")
    else:
        for c in cats:
            adopted = f" ({_agree('adopté', [c])})" if is_adopted(c) else ""
            lines.append(f"{c.name} : {_cat_summary(c)}{adopted}")
    lines.append("")

    # Description juste après les chats : c'est elle qu'on voit avant le « Voir plus » de Facebook
    if ref.description:
        lines += [ref.description.strip(), ""]

    # Infos communes
    lines += _common_lines(ref)
    if len(cats) == 1:
        lines.append(f"🩺 FIV / FeLV : {_test(cats[0].fiv)} / {_test(cats[0].felv)}")
    elif not any(c.fiv or c.felv for c in cats):
        lines.append("🩺 FIV / FeLV : tous négatifs")
    else:
        lines.append("🩺 FIV / FeLV : " + " ; ".join(f"{c.name} {_test(c.fiv)} / {_test(c.felv)}" for c in cats))

    lines.append("")
    if available:
        target = join_names_fr(c.name for c in available)
        lines.append(f"👉 Toutes les infos et le contact pour adopter {target} :")
        lines.append(site_url(url_for('cat_detail', uuid=available[0].uuid)))
    else:
        lines.append("👉 D'autres chats attendent encore leur famille :")
        lines.append(site_url(url_for('index')))
    return "\n".join(lines).replace("\r\n", "\n")


def photo_urls(cats):
    """Adresses publiques des photos de l'annonce, la principale en premier (8 au maximum)."""
    ref = sorted(cats, key=lambda c: c.id)[0]
    return [site_url(photo_public_url(p)) for p in (ref.photos or [])][:current_app.config.get('MAX_PHOTOS', 8)]


# --- Publication et mise à jour

def publish(cats):
    """
    Publie l'annonce (texte et photos) et enregistre le post pour chacun de ses chats ; sans commit.
    En cas d'échec, l'erreur est enregistrée pour pouvoir réessayer, puis FacebookError est relevée.
    """
    try:
        post_id = facebook.publish_photos_post(build_text(cats), photo_urls(cats))
    except facebook.FacebookError as e:
        save_rows(cats, error=str(e))
        raise
    try:
        url = facebook.post_link(post_id)
    except facebook.FacebookError:
        url = None  # le post existe : le lien n'est qu'un plus
    save_rows(cats, post_id=post_id, post_url=url)
    return post_id


def update(post_id):
    """Réécrit le texte d'un post d'après l'état actuel de ses chats ; sans commit. Lève FacebookError."""
    cats = post_cats(post_id)
    if not cats:
        return
    try:
        facebook.update_post_text(post_id, build_text(cats))
    except facebook.FacebookError as e:
        if facebook.post_exists(post_id) is False:
            # post supprimé à la main sur Facebook : l'annonce n'est plus suivie (comme une annonce sans Facebook)
            for row in AdoptionCatPost.query.filter_by(post_id=post_id, network=NETWORK).all():
                db.session.delete(row)
            raise PostGone("La publication n'existe plus sur Facebook (supprimée sur la page) : "
                           "l'annonce n'y est plus rattachée.") from e
        save_rows(cats, error=str(e))
        raise
    save_rows(cats)


def sync_after_status_change(cats):
    """
    Après un archivage ou une remise en ligne : met à jour les posts concernés (sans aperçu).
    Retourne None, ou (message d'erreur, post supprimé sur Facebook) : l'action sur le site reste faite.
    """
    if not facebook.is_enabled():
        return None
    post_ids = {r.post_id for r in rows_of(cats) if r.post_id}
    error, gone = None, False
    for post_id in sorted(post_ids):
        try:
            update(post_id)
        except PostGone as e:
            error, gone = str(e), True
        except facebook.FacebookError as e:
            error = str(e)
    db.session.commit()
    return (error, gone) if error else None
