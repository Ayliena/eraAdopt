"""
Publication sur la page Facebook de l'association, via l'API Graph de Meta.

La page visée est choisie par la configuration : page de test sur le site de développement, page officielle
d'ERA en production (FB_PAGE_ID, FB_PAGE_TOKEN). Le jeton de page reste côté serveur et n'est jamais
envoyé au navigateur.
"""
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from flask import current_app

DEFAULT_GRAPH_VERSION = 'v26.0'
TIMEOUT = 15  # secondes : une panne de Facebook ne doit pas bloquer le site
REQUIRED_SCOPES = {'pages_manage_posts', 'pages_read_engagement'}


class FacebookError(Exception):
    """Erreur de l'API Graph ; code et subcode : codes d'erreur de Meta (None si Facebook n'a pas répondu)."""

    def __init__(self, message, code=None, subcode=None):
        super().__init__(message)
        self.code = code
        self.subcode = subcode


def is_enabled():
    """Publication des annonces active : configurée, et non coupée par FB_ENABLED = False."""
    return is_configured() and current_app.config.get('FB_ENABLED', True)


def is_configured():
    return bool(current_app.config.get('FB_PAGE_ID') and current_app.config.get('FB_PAGE_TOKEN'))


def _call(method, path, params=None):
    """Appel de l'API Graph avec le jeton de page ; retourne la réponse JSON ou lève FacebookError."""
    if not is_configured():
        raise FacebookError("Facebook n'est pas configuré (FB_PAGE_ID et FB_PAGE_TOKEN dans la config).")
    version = current_app.config.get('FB_GRAPH_VERSION', DEFAULT_GRAPH_VERSION)
    params = dict(params or {}, access_token=current_app.config['FB_PAGE_TOKEN'])
    url = f"https://graph.facebook.com/{version}/{path}"
    data = None
    if method in ('GET', 'DELETE'):
        url += '?' + urlencode(params)
    else:
        data = urlencode(params).encode()
    try:
        with urlopen(Request(url, data=data, method=method), timeout=TIMEOUT) as response:
            return json.loads(response.read().decode() or '{}')
    except HTTPError as e:
        try:
            error = json.loads(e.read().decode()).get('error', {})
        except ValueError:
            error = {}
        message = error.get('message') or str(e)
        code, subcode = error.get('code'), error.get('error_subcode')
        # le message de Meta ne contient pas le jeton : il peut être affiché et journalisé
        current_app.logger.warning("Erreur de l'API Facebook (%s %s) : %s [code %s, sous-code %s]",
                                   method, path, message, code, subcode)
        raise FacebookError(message, code, subcode) from e
    except (URLError, TimeoutError, ValueError) as e:
        current_app.logger.warning("Facebook injoignable (%s %s) : %s", method, path, e)
        raise FacebookError(f"Facebook injoignable : {e}") from e


def page_info():
    """Nom et lien de la page visée (vérifie aussi que le jeton fonctionne)."""
    return _call('GET', current_app.config['FB_PAGE_ID'], {'fields': 'name,link'})


def token_info():
    """
    Informations sur le jeton (un jeton peut s'inspecter lui-même) : validité, expiration, droits.
    expires_at = 0 : le jeton n'expire jamais. data_access_expires_at : fin de l'accès aux données accordé par
    l'utilisateur qui a généré le jeton (90 jours, renouvelés quand il utilise l'app).
    """
    token = current_app.config['FB_PAGE_TOKEN']
    return _call('GET', 'debug_token', {'input_token': token}).get('data', {})


def publish_text(message):
    """Publie un texte sur la page ; retourne l'identifiant du post ('<page>_<post>')."""
    return _call('POST', f"{current_app.config['FB_PAGE_ID']}/feed", {'message': message})['id']


def publish_photos_post(message, photo_urls):
    """
    Publie un post avec plusieurs photos (dans l'ordre donné) ; retourne l'identifiant du post.
    Les photos sont d'abord envoyées sans être publiées (Facebook les récupère à leur adresse publique),
    puis rattachées au post. En cas d'échec, les photos déjà envoyées sont supprimées (au mieux).
    """
    page_id = current_app.config['FB_PAGE_ID']
    media_ids = []
    try:
        for url in photo_urls:
            media_ids.append(_call('POST', f"{page_id}/photos", {'url': url, 'published': 'false'})['id'])
        params = {'message': message}
        for i, media_id in enumerate(media_ids):
            params[f'attached_media[{i}]'] = json.dumps({'media_fbid': media_id})
        return _call('POST', f"{page_id}/feed", params)['id']
    except FacebookError:
        for media_id in media_ids:
            try:
                _call('DELETE', media_id)
            except FacebookError:
                pass
        raise


def update_post_text(post_id, message):
    """Remplace le texte d'un post existant (les photos ne changent pas)."""
    _call('POST', post_id, {'message': message})


def post_link(post_id):
    """Lien public du post."""
    return _call('GET', post_id, {'fields': 'permalink_url'}).get('permalink_url')


def post_exists(post_id):
    """
    True si le post existe, False s'il n'existe plus (supprimé à la main sur la page), None si on ne peut pas
    savoir (Facebook injoignable, jeton en cause...).
    Facebook ne distingue pas « post supprimé » d'un manque de droits : lire un post supprimé renvoie
    « (#10) Object does not exist, cannot be loaded due to missing permission... » (ou #100 / 33). On vérifie
    donc aussi que la page elle-même reste lisible et que le jeton est valide avec ses droits : si oui, c'est
    bien le post qui a disparu. Au moindre doute (Facebook injoignable, autre erreur), on ne conclut pas.
    """
    try:
        _call('GET', post_id, {'fields': 'id'})
        return True
    except FacebookError as e:
        if e.code not in (10, 100):
            return None
    try:
        page_info()
        token = token_info()
    except FacebookError:
        return None  # le jeton ou la page posent problème : on ne conclut pas
    # jeton valide et toujours muni des droits de lecture et de publication : c'est bien le post qui a disparu
    if not token.get('is_valid') or not REQUIRED_SCOPES <= set(token.get('scopes') or []):
        return None
    return False


def delete_post(post_id):
    _call('DELETE', post_id)
