"""
Commandes en ligne de commande du site (lancées par cron sur le serveur).

flask --app wsgi sync-facebook : met à jour les posts Facebook dont un chat a changé de statut en dehors du site,
par exemple un chat passé en ARCHIVED depuis eraFA (adopté, décédé...). Même mise à jour que l'archivage manuel.
"""
from datetime import datetime
from app import app, db, facebook, facebook_post


def log(message):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


@app.cli.command('sync-facebook')
def sync_facebook():
    """Met à jour les posts Facebook en retard sur le statut de leurs chats."""
    if not facebook.is_enabled():
        return  # Facebook coupé (FB_ENABLED) ou non configuré : rattrapé au premier passage après réactivation
    post_ids = facebook_post.pending_post_ids()
    if not post_ids:
        return  # rien à faire : pas de ligne dans le journal à chaque passage
    if not app.config.get('SITE_URL'):
        log("SITE_URL manquant dans la config : impossible de construire les liens des posts.")
        return
    # le texte des posts contient des liens vers le site : contexte de requête sur l'adresse publique du site
    with app.test_request_context('/', base_url=app.config['SITE_URL']):
        for post_id in post_ids:
            names = ", ".join(c.name for c in facebook_post.post_cats(post_id))
            try:
                facebook_post.update(post_id)
                log(f"Post {post_id} mis à jour ({names}).")
            except facebook_post.PostGone:
                log(f"Post {post_id} supprimé sur Facebook : suivi retiré ({names}).")
            except facebook.FacebookError as e:
                log(f"ERREUR post {post_id} ({names}) : {e}")
            db.session.commit()
