import os
import shutil
from functools import wraps
from urllib.parse import quote
from flask import render_template, jsonify, request, abort, redirect, url_for
from flask_login import current_user
from sqlalchemy import func
from sqlalchemy.orm import aliased
from app import app, db, login_manager
from app.models import AdoptionCat, User, build_groups, build_review_groups, photo_public_url
from app import review_form
from app.seed_data import SEED_CATS, COLOR_PHOTOS
from app.helpers import slugify_name, build_contact_mailto

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
    """Réserve une route aux admins des adoptions (connexion via eraFA)."""
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

        # 1. Filtre entente chats (si coché: le foyer a des chats, donc le chat doit être sociable chats)
        if good_with_cats == '1':
            query = query.filter(AdoptionCat.good_with_cats.is_(True))

        # 2. Filtre entente enfants (si coché: le foyer a des enfants, donc le chat doit être ok enfants)
        if good_with_children == '1':
            query = query.filter(AdoptionCat.good_with_children.is_(True))

        # 3. Filtre accès extérieur (si coché: pas d'extérieur au foyer, donc on cache les chats qui en ont besoin)
        if no_outdoor == '1':
            query = query.filter(AdoptionCat.outdoor_access.isnot(True))

        # 4. Filtre adoption multiple (1 = à plusieurs, 0 = seul uniquement)
        # Même règle que le badge (is_multiple_adoption) : au moins un chat lié ACCEPTED.
        # JSON_CONTAINS gère aussi bien le NULL SQL que la valeur JSON 'null'.
        if multiple_adoption in ('1', '0'):
            linked = aliased(AdoptionCat)
            has_accepted_linked = db.select(linked.id).where(
                linked.status == 'ACCEPTED',
                func.json_contains(AdoptionCat.linked_cats, func.json_quote(linked.uuid)) == 1
            ).exists()
            query = query.filter(has_accepted_linked if multiple_adoption == '1' else ~has_accepted_linked)

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

    active_filters = {
        'good_with_cats': good_with_cats,
        'good_with_children': good_with_children,
        'no_outdoor': no_outdoor,
        'multiple_adoption': multiple_adoption,
    }

    # Critères effectivement appliqués (repris dans les liens de pagination)
    applied = {k: v for k, v in active_filters.items() if v in FILTER_VALUES[k]}

    # ?partial=1 : uniquement la liste des annonces (mise à jour sans rechargement par les filtres)
    template = '_results.html' if request.args.get('partial') == '1' else 'index.html'
    return render_template(
        template,
        cats=cats,
        pagination=pagination,
        filters=active_filters,
        applied_filters=applied,
    )

@app.route('/chat/<uuid>')
def cat_detail(uuid):
    """
    Affiche l'annonce d'un chat, ou des chats à adopter ensemble, à partir de l'UUID de l'un d'eux.
    L'URL de n'importe quel chat de l'annonce fonctionne et redirige vers celle du chat de référence (le plus ancien).
    """
    cat = AdoptionCat.query.filter_by(uuid=uuid, status='ACCEPTED').first_or_404()
    reference = cat.adoption_group[0]
    if reference.uuid != cat.uuid:
        return redirect(url_for('cat_detail', uuid=reference.uuid))
    return render_template(
        'cat_detail.html',
        cat=cat,
        contact_mailto=build_contact_mailto(cat, ADOPTION_MAILADDR)
    )

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
                           photo_errors=request.args.get('photos_erreur', 0, type=int))

@app.route('/admin/annonces')
@admin_required
def admin_listings():
    """Toutes les annonces publiées (ou archivées avec ?statut=archivees), regroupées par adoption."""
    archived = request.args.get('statut') == 'archivees'
    published_groups = build_groups('ACCEPTED')
    archived_groups = build_groups('ARCHIVED')
    groups = archived_groups if archived else published_groups
    groups.sort(key=lambda g: g.created_at, reverse=True)  # plus récentes d'abord
    return render_template(
        'admin_listings.html',
        groups=groups,
        archived=archived,
        archived_notice=request.args.get('archivee'),
        restored_notice=request.args.get('remise'),
        deleted_notice=request.args.get('supprimee'),
        photo_errors=request.args.get('photos_erreur', 0, type=int),
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
        common, own, errors = review_form.parse_form(request.form, group)
        if not errors:
            review_form.apply_values(group, common, own)
            publish = mode == 'review' and request.form.get('action') == 'publish'
            if publish:
                for cat in review_form.editable_cats(group):
                    cat.status = 'ACCEPTED'
            db.session.commit()

            # Fichiers des photos retirées : supprimés du disque une fois la base à jour
            failed = review_form.delete_photo_files(common['photos_delete'], app.config['UPLOAD_FOLDER'], app.logger)
            extra = {'photos_erreur': len(failed)} if failed else {}
            if publish:
                return redirect(url_for('admin_review_list', publie=group.main_cat.uuid, **extra))
            endpoint = 'admin_review_group' if mode == 'review' else 'admin_edit_listing'
            return redirect(url_for(endpoint, uuid=group.main_cat.uuid, enregistre=1, **extra))
    else:
        common, own, _ = review_form.initial_values(group)

    _, _, differences = review_form.initial_values(group)
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
        form=review_form,
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

@app.route('/admin/annonces/<uuid>/archiver', methods=['POST'])
@admin_required
def admin_archive_listing(uuid):
    """Archive une annonce publiée (tous ses chats) : elle n'est plus visible du public."""
    group = find_group('ACCEPTED', uuid)
    for cat in group.cats:
        cat.status = 'ARCHIVED'
    db.session.commit()
    return redirect(url_for('admin_listings', archivee=group.names_display))

@app.route('/admin/annonces/<uuid>/remettre-en-ligne', methods=['POST'])
@admin_required
def admin_restore_listing(uuid):
    """Remet en ligne une annonce archivée (tous ses chats repassent ACCEPTED, photos intactes)."""
    group = find_group('ARCHIVED', uuid)
    for cat in group.cats:
        cat.status = 'ACCEPTED'
    db.session.commit()
    return redirect(url_for('admin_listings', statut='archivees', remise=group.names_display))

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
