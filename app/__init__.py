from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
import os

app = Flask(__name__)

# Détection de l'environnement : config-dev si en développement, sinon config (prod)
devel_site = any(path in os.getcwd() for path in ['era-devel', 'devel', 'Adopt-devel'])

if devel_site:
    app.config.from_object('config-dev')
else:
    app.config.from_object('config')

# Exposé dans la config pour les routes et templates réservés au dev
app.config['DEVEL_SITE'] = devel_site

db = SQLAlchemy(app)

# Connexion unique avec eraFA : la session (cookie partagé sur le domaine) est créée par eraFA,
# eraAdopt se contente de la lire. Voir SESSION_COOKIE_* et SECRET_KEY dans la config.
login_manager = LoginManager()
login_manager.init_app(app)

# Protection CSRF de tous les formulaires POST (jeton {{ csrf_token() }} dans chaque formulaire).
# Pas d'expiration du jeton : une annonce peut être relue longuement avant validation.
app.config.setdefault('WTF_CSRF_TIME_LIMIT', None)
csrf = CSRFProtect(app)

from app import routes, models
