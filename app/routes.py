import os
import re
import shutil
from datetime import datetime
from functools import wraps
from urllib.parse import quote
from flask import render_template, jsonify, request, abort, redirect, url_for
from flask_login import current_user
from sqlalchemy import func
from sqlalchemy.orm import aliased
from app import app, db, login_manager
from app.photos import PhotoError, remove_files
from app.models import AdoptionCat, AdoptionCatPost, User, build_groups, build_review_groups, photo_public_url, join_names_fr
from app import review_form, facebook, facebook_post
from app.seed_data import SEED_CATS, COLOR_PHOTOS
from app.helpers import slugify_name, build_contact_mailto, fold_text, MAIL_BODY_LINES

ADOPTION_MAILADDR = 'adoptions@association-era.org'

@login_manager.user_loader
def load_user(user_id):
    # user_id = username, comme dans eraFA
    return User.query.filter_by(username=user_id).first()

def dev_only(view):
    """Réserve une route au site de développement : 404 en production."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not app.config.get('DEVEL_SITE'):
            abort(404)
        return view(*args, **kwargs)
    return wrapper

def admin_required(view):
    """Réserve une route aux comptes qui valident les annonces (droit eraFA PRIV_ANNVAL, connexion via eraFA)."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(f"{app.config['ERAFA_URL']}/login/?next={quote(request.url, safe='')}")
        if not current_user.is_adoption_admin:
            abort(403)
        return view(*args, **kwargs)
    return wrapper

app.add_template_filter(photo_public_url, 'photo_url')

@app.context_processor
def inject_static_version():
    """static_v(fichier) : version (date de modification) d'un fichier statique, ajoutée à son URL pour
    que les navigateurs rechargent le fichier quand il change au lieu de garder une ancienne version en cache."""
    def static_v(filename):
        try:
            return int(os.path.getmtime(os.path.join(app.static_folder, filename)))
        except OSError:
            return 0
    return {'static_v': static_v}

@app.context_processor
def inject_admin_info():
    """Nombre de fiches à valider, affiché dans la barre utilisateur des admins."""
    if current_user.is_authenticated and current_user.is_adoption_admin:
        try:
            return {'review_count': len(build_review_groups())}
        except Exception:
            app.logger.exception("Erreur lors du comptage des fiches à valider")
    return {}

# Valeurs acceptées pour chaque critère de recherche
FILTER_VALUES = {
    'good_with_cats': {'1'},
    'good_with_children': {'1'},
    'no_outdoor': {'1'},
    'multiple_adoption': {'0', '1'},
}

@app.route('/')
def index():
    try:
        # Seuls les chats avec le statut ACCEPTED sont affichés publiquement
        query = AdoptionCat.query.filter(AdoptionCat.status == 'ACCEPTED')

        # Une annonce = une carte : pour des chats à adopter ensemble, seul le plus ancien (chat de référence)
        # est listé. Hypothèse : dans une annonce, chaque chat est lié à tous les autres.
        older = aliased(AdoptionCat)
        has_older_linked = db.select(older.id).where(
            older.status == 'ACCEPTED',
            older.id < AdoptionCat.id,
            func.json_contains(AdoptionCat.linked_cats, func.json_quote(older.uuid)) == 1
        ).exists()
        query = query.filter(~has_older_linked)

        # Récupération des filtres
        good_with_cats = request.args.get('good_with_cats')
        good_with_children = request.args.get('good_with_children')
        no_outdoor = request.args.get('no_outdoor')
        multiple_adoption = request.args.get('multiple_adoption')
        name_search = request.args.get('nom', '').strip()[:100]

        # 0. Recherche par nom : l'annonce apparaît si l'un de ses chats correspond (le chat de référence ou
        # un chat lié publié). Majuscules et accents sont ignorés grâce à l'interclassement utf8mb4_unicode_ci
        # de la table : "felix" trouve "Félix".
        if name_search:
            pattern = '%' + name_search.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
            same_listing = aliased(AdoptionCat)
            linked_name_match = db.select(same_listing.id).where(
                same_listing.status == 'ACCEPTED',
                same_listing.name.like(pattern, escape='\\'),
                func.json_contains(AdoptionCat.linked_cats, func.json_quote(same_listing.uuid)) == 1
            ).exists()
            query = query.filter(db.or_(AdoptionCat.name.like(pattern, escape='\\'), linked_name_match))

        # 1. Filtre entente chats (si coché: le foyer a des chats, donc le chat doit être sociable chats)
        if good_with_cats == '1':
            query = query.filter(AdoptionCat.good_with_cats.in_(['OK', 'REQUIRED']))

        # 2. Filtre entente enfants (si coché: le foyer a des enfants, donc le chat doit être ok enfants)
        if good_with_children == '1':
            query = query.filter(AdoptionCat.good_with_children.is_(True))

        # 3. Filtre accès extérieur (si coché: pas d'extérieur au foyer, donc on cache les chats qui en ont besoin ;
        #    intérieur uniquement, sortie possible et inconnu restent affichés)
        if no_outdoor == '1':
            query = query.filter(db.or_(AdoptionCat.outdoor_access.is_(None), AdoptionCat.outdoor_access != 'REQUIRED'))

        # 4. Filtre adoption seul / à plusieurs : "peut-on n'adopter qu'un seul chat ?"
        #    - à plusieurs (1) : annonces de plusieurs chats à adopter ensemble uniquement
        #    - seul (0) : chats seuls et annonces de chats adoptables séparément
        # Annonce de plusieurs chats = au moins un chat lié ACCEPTED (même règle que le badge).
        # JSON_CONTAINS gère aussi bien le NULL SQL que la valeur JSON 'null'.
        if multiple_adoption in ('1', '0'):
            linked = aliased(AdoptionCat)
            has_accepted_linked = db.select(linked.id).where(
                linked.status == 'ACCEPTED',
                func.json_contains(AdoptionCat.linked_cats, func.json_quote(linked.uuid)) == 1
            ).exists()
            together = db.and_(has_accepted_linked, AdoptionCat.adoption_mode == 'TOGETHER')
            query = query.filter(together if multiple_adoption == '1' else ~together)

        # Pagination (12 annonces par page, ajustable via CATS_PER_PAGE dans la config)
        page = request.args.get('page', 1, type=int)
        pagination = query.order_by(AdoptionCat.id.desc()).paginate(
            page=page, per_page=app.config.get('CATS_PER_PAGE', 12), error_out=False
        )
        cats = pagination.items
    except Exception:
        app.logger.exception("Erreur lors du chargement de la liste des chats")
        pagination = None
        cats = []
        good_with_cats = None
        good_with_children = None
        no_outdoor = None
        multiple_adoption = None
        name_search = ''

    active_filters = {
        'good_with_cats': good_with_cats,
        'good_with_children': good_with_children,
        'no_outdoor': no_outdoor,
        'multiple_adoption': multiple_adoption,
    }

    # Critères effectivement appliqués (repris dans les liens de pagination)
    applied = {k: v for k, v in active_filters.items() if v in FILTER_VALUES[k]}
    if name_search:
        applied['nom'] = name_search

    # ?partial=1 : uniquement la liste des annonces (mise à jour sans rechargement par les filtres)
    template = '_results.html' if request.args.get('partial') == '1' else 'index.html'
    return render_template(
        template,
        cats=cats,
        pagination=pagination,
        filters=active_filters,
        name_search=name_search,
        applied_filters=applied,
    )

@app.route('/chat/<uuid>')
def cat_detail(uuid):
    """
    Affiche l'annonce d'un chat, ou des chats à adopter ensemble, à partir de l'UUID de l'un d'eux.
    L'URL de n'importe quel chat de l'annonce fonctionne et redirige vers celle du chat de référence (le plus ancien).
    """
    cat = AdoptionCat.query.filter_by(uuid=uuid).first_or_404()

    # Chat archivé (ex. adopté seul) dont des chats liés sont encore en ligne : son ancienne adresse
    # mène à l'annonce de ces chats, avec un bandeau d'explication
    if cat.status == 'ARCHIVED':
        remaining = cat.get_linked_cats
        if not remaining:
            abort(404)
        reference = min(remaining, key=lambda c: c.id).adoption_group[0]
        return redirect(url_for('cat_detail', uuid=reference.uuid, indisponible=cat.uuid))
    if cat.status != 'ACCEPTED':
        abort(404)

    reference = cat.adoption_group[0]
    if reference.uuid != cat.uuid:
        return redirect(url_for('cat_detail', uuid=reference.uuid))

    # Bandeau : uniquement pour un chat archivé réellement lié à cette annonce
    unavailable = None
    if request.args.get('indisponible'):
        candidate = AdoptionCat.query.filter_by(uuid=request.args['indisponible'], status='ARCHIVED').first()
        group_uuids = {c.uuid for c in cat.adoption_group}
        if candidate and group_uuids & set(candidate.linked_cats or []):
            unavailable = candidate

    return render_template(
        'cat_detail.html',
        cat=cat,
        unavailable=unavailable,
        contact_mailto=build_contact_mailto(cat, ADOPTION_MAILADDR),
        mail_address=ADOPTION_MAILADDR,
        mail_body_lines=MAIL_BODY_LINES
    )

@app.errorhandler(404)
def page_not_found(error):
    """Page 404 aux couleurs du site ; message dédié pour une annonce (/chat/...) qui n'est plus disponible."""
    return render_template('error_404.html', cat_link=request.path.startswith('/chat/')), 404

@app.route('/mentions-legales')
def legal_notice():
    return render_template('legal_notice.html')

@app.route('/confidentialite')
def privacy():
    return render_template('privacy.html')

@app.route('/admin/validation')
@admin_required
def admin_review_list():
    """Liste des fiches en attente de validation, regroupées par adoption (chats liés ensemble)."""
    # Confirmation après publication (passée dans l'URL pour ne pas écrire dans la session partagée avec eraFA)
    published = None
    if request.args.get('publie'):
        published = AdoptionCat.query.filter_by(uuid=request.args['publie'], status='ACCEPTED').first()
    return render_template('admin_review_list.html', groups=build_review_groups(), published=published,
                           published_on_facebook=request.args.get('facebook') == '1',
                           facebook_scheduled=request.args.get('programme'),
                           photo_errors=request.args.get('photos_erreur', 0, type=int))

@app.route('/admin/annonces')
@admin_required
def admin_listings():
    """Toutes les annonces publiées (ou archivées avec ?statut=archivees), regroupées par adoption."""
    archived = request.args.get('statut') == 'archivees'
    search = request.args.get('q', '').strip()[:100]
    published_groups = build_groups('ACCEPTED')
    archived_groups = build_groups('ARCHIVED')

    # Recherche : nom d'un des chats (contient, sans accents ni majuscules) ou référence (début de l'uuid,
    # celle citée dans les mails de demande d'adoption). Appliquée aux deux onglets, pour leurs compteurs.
    if search:
        name_part, ref_part = fold_text(search), search.lower()
        def matches(group):
            return any(name_part in fold_text(c.name) or c.uuid.lower().startswith(ref_part) for c in group.cats)
        published_groups = [g for g in published_groups if matches(g)]
        archived_groups = [g for g in archived_groups if matches(g)]

    groups = archived_groups if archived else published_groups
    groups.sort(key=lambda g: g.created_at, reverse=True)  # plus récentes d'abord
    return render_template(
        'admin_listings.html',
        groups=groups,
        archived=archived,
        search=search,
        archived_notice=request.args.get('archivee'),
        remaining_cat=(AdoptionCat.query.filter_by(uuid=request.args['reste'], status='ACCEPTED').first()
                       if request.args.get('reste') else None),
        restored_notice=request.args.get('remise'),
        still_archived_notice=request.args.get('encore_archive'),
        deleted_notice=request.args.get('supprimee'),
        photo_errors=request.args.get('photos_erreur', 0, type=int),
        fb_error=request.args.get('fb_erreur'),
        fb_error_uuid=request.args.get('fb_annonce'),
        fb_gone=request.args.get('fb_supprime') == '1',
        fb_ok=request.args.get('fb_ok') == '1',
        published_count=len(published_groups),
        archived_count=len(archived_groups),
    )

def find_group(main_status, uuid, linked_statuses=()):
    """Annonce (groupe de chats) du statut main_status contenant le chat uuid, ou 404."""
    group = next((g for g in build_groups(main_status, linked_statuses)
                  if any(c.uuid == uuid and c.status == main_status for c in g.cats)), None)
    if group is None:
        abort(404)
    return group

def group_form_page(group, mode):
    """
    Formulaire d'une annonce, commun à la validation (mode 'review', chats UNDER_REVIEW)
    et à la modification d'une annonce publiée (mode 'edit', chats ACCEPTED).
    """
    errors = {}
    if request.method == 'POST':
        common, own, errors = review_form.parse_form(request.form, request.files, group)
        written = []
        if not errors:
            try:
                written = review_form.save_new_photos(group, common, own, app.config['UPLOAD_FOLDER'])
            except PhotoError as e:
                errors['photos'] = f"Une photo n'a pas pu être traitée : {e}."
        if not errors:
            review_form.apply_values(group, common, own)
            publish = mode == 'review' and request.form.get('action') == 'publish'
            # Publication / mise à jour Facebook demandée : enregistrement, puis aperçu du post avant envoi
            # (l'annonce n'est mise en ligne qu'après l'envoi, ou sans Facebook depuis l'aperçu)
            to_facebook = request.form.get('facebook') == '1' and facebook.is_enabled() and (
                publish or (mode == 'edit' and facebook_post.listing_post(group.cats)[0]))
            if publish and not to_facebook:
                for cat in review_form.editable_cats(group):
                    cat.status = 'ACCEPTED'
            try:
                db.session.commit()
            except Exception:
                # base inchangée : les photos ajoutées ne servent à rien
                db.session.rollback()
                remove_files(written)
                raise

            # Fichiers des photos retirées : supprimés du disque une fois la base à jour
            failed = review_form.delete_photo_files(common['photos_delete'], app.config['UPLOAD_FOLDER'], app.logger)
            extra = {'photos_erreur': len(failed)} if failed else {}
            if to_facebook:
                endpoint = 'admin_review_facebook' if mode == 'review' else 'admin_edit_facebook'
                return redirect(url_for(endpoint, uuid=group.main_cat.uuid, **extra))
            if publish:
                return redirect(url_for('admin_review_list', publie=group.main_cat.uuid, **extra))
            endpoint = 'admin_review_group' if mode == 'review' else 'admin_edit_listing'
            return redirect(url_for(endpoint, uuid=group.main_cat.uuid, enregistre=1, **extra))
    else:
        common, own, _ = review_form.initial_values(group)

    _, _, differences = review_form.initial_values(group)
    fb_post_id, fb_post_url, fb_error = facebook_post.listing_post(group.cats)
    fb_scheduled = facebook_post.scheduled_at(group.cats) if fb_post_id else None
    return render_template(
        'admin_review_group.html',
        mode=mode,
        group=group,
        cats=review_form.editable_cats(group),
        published_cats=[c for c in group.cats if c.status == 'ACCEPTED'] if mode == 'review' else [],
        common=common,
        own=own,
        errors=errors,
        differences=differences,
        available_photos=review_form.photos_main_first(review_form.all_photos(group), common.get('photo_main')),
        saved=request.args.get('enregistre') == '1' and request.method == 'GET',
        photo_errors=request.args.get('photos_erreur', 0, type=int) if request.method == 'GET' else 0,
        new_photos_lost=bool(errors and common.get('photos_new')),
        max_photos=app.config.get('MAX_PHOTOS', 8),
        form=review_form,
        fb_enabled=facebook.is_enabled(),
        fb_post_id=fb_post_id,
        fb_post_url=fb_post_url,
        fb_error=fb_error,
        fb_scheduled=fb_scheduled,
        fb_updated=request.args.get('facebook') == '1',
        fb_gone=request.args.get('fb_supprime') == '1',
    )

@app.route('/admin/validation/<uuid>', methods=['GET', 'POST'])
@admin_required
def admin_review_group(uuid):
    """Relecture, modification et validation d'une annonce en attente."""
    return group_form_page(find_group('UNDER_REVIEW', uuid, ('ACCEPTED',)), 'review')

@app.route('/admin/annonces/<uuid>/modifier', methods=['GET', 'POST'])
@admin_required
def admin_edit_listing(uuid):
    """Modification d'une annonce publiée."""
    return group_form_page(find_group('ACCEPTED', uuid), 'edit')

def facebook_preview_page(group, mode):
    """
    Aperçu du post Facebook d'une annonce, puis envoi :
    - mode 'review' : publication du post, puis mise en ligne de l'annonce (ou mise en ligne sans Facebook) ;
    - mode 'edit' : mise à jour du texte du post existant, ou nouvel essai si la publication avait échoué.
    """
    if not facebook.is_enabled():
        abort(404)
    post_id, post_url, last_error = facebook_post.listing_post(group.cats)
    if mode == 'edit' and not post_id and not last_error:
        abort(404)  # annonce publiée sans Facebook : pas de post à créer après coup
    cats = facebook_post.post_cats(post_id) if post_id else list(group.cats)
    form_endpoint = 'admin_review_group' if mode == 'review' else 'admin_edit_listing'
    error = None
    # Programmation de la publication : seulement à la validation (les autres envois mettent à jour un post)
    can_schedule = mode == 'review' and not post_id
    default_day, default_time = facebook_post.default_schedule()
    schedule = {'on': False, 'day': default_day, 'time': default_time, 'error': None}

    if request.method == 'POST':
        action = request.form.get('action')
        if mode == 'review' and action == 'without':
            for cat in review_form.editable_cats(group):
                cat.status = 'ACCEPTED'
            db.session.commit()
            return redirect(url_for('admin_review_list', publie=group.main_cat.uuid))
        if action != 'send':
            abort(400)
        scheduled = None
        if can_schedule and request.form.get('schedule') == '1':
            schedule.update(on=True, day=request.form.get('schedule_day', ''), time=request.form.get('schedule_time', ''))
            scheduled, schedule['error'] = facebook_post.parse_schedule(schedule['day'], schedule['time'])
        # date de programmation invalide : rien n'est envoyé, la page se réaffiche avec l'erreur
        if not schedule['error']:
            try:
                if post_id:
                    facebook_post.update(post_id)
                else:
                    facebook_post.publish(cats, scheduled)
                    if mode == 'review':
                        for cat in review_form.editable_cats(group):
                            cat.status = 'ACCEPTED'
                db.session.commit()
                if mode == 'review':
                    return redirect(url_for('admin_review_list', publie=group.main_cat.uuid, facebook=1,
                                            programme=scheduled.strftime('%d/%m/%Y à %H:%M') if scheduled else None))
                return redirect(url_for('admin_edit_listing', uuid=group.main_cat.uuid, facebook=1))
            except facebook_post.PostGone:
                db.session.commit()  # suivi retiré : l'annonce est désormais sans Facebook
                return redirect(url_for(form_endpoint, uuid=group.main_cat.uuid, fb_supprime=1))
            except facebook.FacebookError as e:
                db.session.commit()  # l'erreur est gardée avec l'annonce, pour pouvoir réessayer plus tard
                error = str(e)

    return render_template(
        'admin_facebook_preview.html',
        mode=mode,
        group=group,
        update=bool(post_id),
        post_url=post_url,
        text=facebook_post.build_text(cats),
        photos=[] if post_id else facebook_post.photo_urls(cats),
        error=error,
        last_error=None if error else last_error,
        form_url=url_for(form_endpoint, uuid=group.main_cat.uuid),
        can_schedule=can_schedule,
        schedule=schedule,
        schedule_min_day=facebook_post.schedule_bounds()[0],
        schedule_max_day=facebook_post.schedule_bounds()[1],
        time_slots=facebook_post.time_slots(),
    )

@app.route('/admin/validation/<uuid>/facebook', methods=['GET', 'POST'])
@admin_required
def admin_review_facebook(uuid):
    """Aperçu et publication sur Facebook d'une annonce en attente, puis mise en ligne."""
    return facebook_preview_page(find_group('UNDER_REVIEW', uuid, ('ACCEPTED',)), 'review')

@app.route('/admin/annonces/<uuid>/facebook', methods=['GET', 'POST'])
@admin_required
def admin_edit_facebook(uuid):
    """Aperçu et mise à jour (ou nouvel essai de publication) du post Facebook d'une annonce publiée."""
    return facebook_preview_page(find_group('ACCEPTED', uuid), 'edit')

def facebook_notice(result, uuid):
    """Paramètres d'URL de l'avertissement Facebook après un archivage ou une remise en ligne (vide si tout va bien)."""
    if not result:
        return {}
    error, gone = result
    # post supprimé sur Facebook : rien à réessayer, l'annonce n'y est plus rattachée
    return {'fb_erreur': error, 'fb_supprime': 1} if gone else {'fb_erreur': error, 'fb_annonce': uuid}

@app.route('/admin/annonces/<uuid>/facebook/synchroniser', methods=['POST'])
@admin_required
def admin_sync_facebook(uuid):
    """Nouvel essai de mise à jour du post Facebook après un archivage ou une remise en ligne (sans aperçu)."""
    cat = AdoptionCat.query.filter(AdoptionCat.uuid == uuid,
                                   AdoptionCat.status.in_(['ACCEPTED', 'ARCHIVED'])).first_or_404()
    group = find_group(cat.status, uuid)
    result = facebook_post.sync_after_status_change(group.cats)
    extra = {'statut': 'archivees'} if cat.status == 'ARCHIVED' else {}
    extra.update(facebook_notice(result, uuid) or {'fb_ok': 1})
    return redirect(url_for('admin_listings', **extra))

def selected_cats(group):
    """Chats d'une annonce visés par une action : ceux cochés dans la popup (choix=1), sinon tous."""
    if request.form.get('choix') == '1':
        selected = set(request.form.getlist('cat_uuids'))
        return [c for c in group.cats if c.uuid in selected]
    return list(group.cats)

@app.route('/admin/annonces/<uuid>/archiver', methods=['POST'])
@admin_required
def admin_archive_listing(uuid):
    """
    Archive une annonce publiée : tous ses chats, ou seulement ceux cochés (cat_uuids), par exemple un chat
    adopté seul. Les chats restants gardent leur annonce ; leurs liens (linked_cats) sont conservés, si bien
    qu'un chat remis en ligne rejoint automatiquement son groupe.
    """
    group = find_group('ACCEPTED', uuid)
    to_archive = selected_cats(group)
    if not to_archive:
        return redirect(url_for('admin_listings'))
    remaining = [c for c in group.cats if c not in to_archive]

    for cat in to_archive:
        cat.status = 'ARCHIVED'
    db.session.commit()

    # Post Facebook de l'annonce : « adopté » pour les chats archivés (mis à jour sans aperçu)
    extra = facebook_notice(facebook_post.sync_after_status_change(group.cats), to_archive[0].uuid)

    archived_names = join_names_fr(c.name for c in to_archive)
    if remaining:
        # rappel : la description et les photos communes parlent peut-être encore des chats archivés
        return redirect(url_for('admin_listings', archivee=archived_names, reste=remaining[0].uuid, **extra))
    return redirect(url_for('admin_listings', archivee=archived_names, **extra))

@app.route('/admin/annonces/<uuid>/remettre-en-ligne', methods=['POST'])
@admin_required
def admin_restore_listing(uuid):
    """
    Remet en ligne une annonce archivée : tous ses chats, ou seulement ceux cochés (cat_uuids). Photos intactes.
    Un chat remis en ligne rejoint automatiquement les chats de son annonce encore publiés (linked_cats conservés).
    """
    group = find_group('ARCHIVED', uuid)
    to_restore = selected_cats(group)
    if not to_restore:
        return redirect(url_for('admin_listings', statut='archivees'))
    still_archived = [c for c in group.cats if c not in to_restore]

    # Les chats qui rejoignent une annonce encore publiée en reprennent le mode d'adoption
    # (il a pu être modifié pendant leur archivage)
    published = {c.id: c for cat in to_restore for c in cat.get_linked_cats}
    if published:
        mode = published[min(published)].adoption_mode
        for cat in to_restore:
            cat.adoption_mode = mode

    for cat in to_restore:
        cat.status = 'ACCEPTED'
    db.session.commit()

    # Post Facebook de l'annonce : de nouveau « à l'adoption » pour les chats remis en ligne
    extra = facebook_notice(facebook_post.sync_after_status_change(group.cats), to_restore[0].uuid)
    return redirect(url_for('admin_listings', statut='archivees', remise=join_names_fr(c.name for c in to_restore),
                            encore_archive=join_names_fr(c.name for c in still_archived) or None, **extra))

@app.route('/admin/annonces/<uuid>/supprimer', methods=['POST'])
@admin_required
def admin_delete_listing(uuid):
    """
    Supprime définitivement une annonce (publiée ou archivée) : fiches de tous ses chats et fichiers photo
    (sauf ceux encore utilisés par une autre fiche). Les liens vers ces chats sont retirés des autres fiches.
    """
    cat = AdoptionCat.query.filter(AdoptionCat.uuid == uuid,
                                   AdoptionCat.status.in_(['ACCEPTED', 'ARCHIVED'])).first_or_404()
    status = cat.status
    group = find_group(status, uuid)
    names = group.names_display
    deleted_uuids = {c.uuid for c in group.cats}
    photos = review_form.all_photos_of(group.cats)

    for c in group.cats:
        db.session.delete(c)
    for other in AdoptionCat.query.filter(AdoptionCat.linked_cats.isnot(None)).all():
        if isinstance(other.linked_cats, list) and deleted_uuids & set(other.linked_cats):
            other.linked_cats = [u for u in other.linked_cats if u not in deleted_uuids] or None
    db.session.commit()

    failed = review_form.delete_photo_files(photos, app.config['UPLOAD_FOLDER'], app.logger)
    extra = {'photos_erreur': len(failed)} if failed else {}
    if status == 'ARCHIVED':
        extra['statut'] = 'archivees'
    return redirect(url_for('admin_listings', supprimee=names, **extra))

def valid_post_id(post_id):
    """Identifiant d'un post de la page configurée ('<page>_<post>') : jamais un autre objet Facebook."""
    page_id = app.config.get('FB_PAGE_ID') or ''
    return bool(page_id) and re.fullmatch(rf"{re.escape(page_id)}_\d+", post_id or '') is not None

@app.route('/admin/facebook', methods=['GET', 'POST'])
@admin_required
def admin_facebook():
    """
    Test de la publication Facebook : état du jeton, publication d'un texte libre, suppression du post publié.
    La page visée dépend de la configuration (page de test en développement).
    """
    error, message = None, ''
    action = request.form.get('action') if request.method == 'POST' else None
    try:
        if action == 'delete':
            post_id = request.form.get('post_id', '')
            if not valid_post_id(post_id):
                abort(400)
            facebook.delete_post(post_id)
            return redirect(url_for('admin_facebook', supprime=1))
        if action == 'publish':
            message = request.form.get('message', '').strip()
            if not message:
                error = "Le texte est vide."
            else:
                post_id = facebook.publish_text(message)
                return redirect(url_for('admin_facebook', post=post_id))
    except facebook.FacebookError as e:
        error = str(e)

    # État du lien (page et jeton) : vérifié seulement à la demande, pour ne pas consommer d'appels à l'affichage
    checked = action == 'check'
    page, token, status_error = None, None, None
    if checked and facebook.is_configured():
        try:
            page = facebook.page_info()
            token = facebook.token_info()
        except facebook.FacebookError as e:
            status_error = str(e)

    # Post qui vient d'être publié (identifiant passé dans l'URL, sans écrire dans la session partagée avec eraFA)
    post_id = request.args.get('post', '')
    post, post_error = None, None
    if valid_post_id(post_id):
        try:
            post = {'id': post_id, 'link': facebook.post_link(post_id)}
        except facebook.FacebookError as e:
            post, post_error = {'id': post_id, 'link': None}, str(e)

    return render_template(
        'admin_facebook.html',
        configured=facebook.is_configured(),
        enabled=facebook.is_enabled(),
        checked=checked,
        page=page,
        token=token,
        token_expires=(datetime.fromtimestamp(token['expires_at']).strftime('%d/%m/%Y')
                       if token and token.get('expires_at') else None),
        data_access_expires=(datetime.fromtimestamp(token['data_access_expires_at']).strftime('%d/%m/%Y')
                             if token and token.get('data_access_expires_at') else None),
        status_error=status_error,
        post=post,
        post_error=post_error,
        deleted=request.args.get('supprime') == '1',
        error=error,
        message=message,
    )

@app.route('/test-db')
@dev_only
def test_db():
    """Vérifie la connexion MySQL et retourne le contenu de la table adoption_cats."""
    try:
        cats = AdoptionCat.query.order_by(AdoptionCat.id.desc()).all()
        return jsonify({
            "status": "success",
            "message": "Connexion à MySQL réussie !",
            "total_cats": len(cats),
            "cats": [cat.to_dict() for cat in cats]
        }), 200
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Erreur de connexion à la base de données : {str(e)}"
        }), 500

def _write_test_png(path, rgb, width=400, height=300):
    """Écrit une image PNG unie (photos de test, sans dépendance externe)."""
    import struct
    import zlib

    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)

    row = b'\x00' + bytes(rgb) * width
    png = (b'\x89PNG\r\n\x1a\n'
           + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
           + chunk(b'IDAT', zlib.compress(row * height, 9))
           + chunk(b'IEND', b''))
    with open(path, 'wb') as f:
        f.write(png)

@app.route('/seed-test')
@dev_only
@admin_required
def seed_test():
    """
    Rétablit le jeu de données de test (app/seed_data.py) : fiches recréées ou remises à l'identique (retrouvées
    par uuid), Grisou et Titi / Toto / Tutu en attente de validation, toutes les autres annonces publiées.
    Photos : celles de couleur unie sont régénérées ; les autres, si elles ont disparu, sont recopiées depuis le
    dossier de sauvegarde uploads/eraAdopt-seed (sinon remplacées par une image grise).
    """
    try:
        folder = app.config['UPLOAD_FOLDER']
        backup = os.path.join(os.path.dirname(folder), 'eraAdopt-seed')
        os.makedirs(folder, exist_ok=True)

        recreated, reset = [], []
        for data in SEED_CATS:
            cat = AdoptionCat.query.filter_by(uuid=data['uuid']).first()
            if cat is None:
                cat = AdoptionCat(uuid=data['uuid'])
                db.session.add(cat)
                recreated.append(data['name'])
            else:
                reset.append(data['name'])
            for field, value in data.items():
                setattr(cat, field, list(value) if isinstance(value, list) else value)
            cat.adoption_mode = data.get('adoption_mode', 'TOGETHER')

        # Suivi Facebook des fiches de test remis à zéro : le seed ne publie jamais rien (les posts restent sur la page)
        AdoptionCatPost.query.filter(AdoptionCatPost.cat_uuid.in_([d['uuid'] for d in SEED_CATS])).delete(
            synchronize_session=False)

        # Les annonces créées en dehors du jeu de test (ex. par les testeurs) sont publiées
        seed_uuids = [d['uuid'] for d in SEED_CATS]
        published = AdoptionCat.query.filter(AdoptionCat.uuid.notin_(seed_uuids), AdoptionCat.status != 'ACCEPTED').all()
        for cat in published:
            cat.status = 'ACCEPTED'
        db.session.commit()

        # Photos
        for filename, rgb in COLOR_PHOTOS.items():
            _write_test_png(os.path.join(folder, filename), rgb)
        restored, placeholders = [], []
        real_photos = {p for d in SEED_CATS for p in (d['photos'] or []) if p not in COLOR_PHOTOS}
        for filename in sorted(real_photos):
            path = os.path.join(folder, filename)
            if os.path.exists(path):
                continue
            if os.path.exists(os.path.join(backup, filename)):
                shutil.copy2(os.path.join(backup, filename), path)
                restored.append(filename)
            else:
                _write_test_png(path, (160, 160, 160))
                placeholders.append(filename)

        return jsonify({
            "status": "success",
            "message": "Jeu de test rétabli : Grisou et Titi / Toto / Tutu en attente de validation, le reste publié.",
            "fiches_recreees": recreated,
            "fiches_remises_a_zero": reset,
            "autres_annonces_publiees": [c.name for c in published],
            "photos_restaurees_depuis_la_sauvegarde": restored,
            "photos_remplacees_par_une_image_grise": placeholders,
            "dossier_de_sauvegarde": backup if os.path.isdir(backup) else "absent : " + backup,
        }), 200
    except Exception as e:
        db.session.rollback()
        app.logger.exception("Erreur lors du seed de test")
        return jsonify({
            "status": "error",
            "message": f"Erreur lors de l'insertion : {str(e)}"
        }), 500

@app.route('/health')
def health():
    try:
        db.session.execute(db.text('SELECT 1'))
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"

    return jsonify({
        "service": "eraAdopt-devel",
        "database": db_status
    })
