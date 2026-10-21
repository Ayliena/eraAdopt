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


class FacebookError(Exception):
    pass


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
            message = error.get('message') or str(e)
        except ValueError:
            message = str(e)
        # le message de Meta ne contient pas le jeton : il peut être affiché et journalisé
        current_app.logger.warning("Erreur de l'API Facebook (%s %s) : %s", method, path, message)
        raise FacebookError(message) from e
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


def post_link(post_id):
    """Lien public du post."""
    return _call('GET', post_id, {'fields': 'permalink_url'}).get('permalink_url')


def delete_post(post_id):
    _call('DELETE', post_id)
