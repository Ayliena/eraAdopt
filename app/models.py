import uuid
from datetime import datetime, date
from flask_login import UserMixin
from app import db

# Droits eraFA (cf. eraFA app/permissions.py) : position dans User.PrivStr
PRIV_ANNAD = 34   # "Rédaction d'annonces d'adoption" (création, sur eraFA)
PRIV_ANNVAL = 35  # "Publication d'annonces d'adoption" (validation et gestion, sur ce site)

def join_names_fr(names):
    """'Titi' / 'Titi et Toto' / 'Titi, Toto et Tutu'."""
    names = list(names)
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " et " + names[-1]


def photo_public_url(path):
    """URL publique d'une photo stockée (nom de fichier dans le dossier d'upload, ou chemin/URL complet)."""
    if path.startswith('/') or path.startswith('http'):
        return path
    return f"/uploads/{path}"


class AdoptionCat(db.Model):
    __tablename__ = 'adoption_cats'

    # Identifiants
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    uuid = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    cat_id = db.Column(db.Integer, nullable=False, index=True)  # cats.id (négatif pour les fiches de test)

    # Statut
    status = db.Column(
        db.Enum('UNDER_REVIEW', 'ACCEPTED', 'ARCHIVED', name='cat_status_enum'),
        default='UNDER_REVIEW',
        nullable=False,
        index=True
    )

    # Informations générales
    name = db.Column(db.String(100), nullable=False, index=True)
    sex = db.Column(db.Enum('MALE', 'FEMALE', name='cat_sex_enum'), nullable=False)
    birthdate = db.Column(db.Date, nullable=False)
    breed = db.Column(db.String(100), default='Européen', nullable=False)
    # Couleur et type de poil, texte repris d'eraFA à la création (ex. 'Tigré, poil long'), modifiable par les admins
    color = db.Column(db.String(64), nullable=False)

    # Entente et environnement
    # Sans autres chats / autres chats OK / autres chats nécessaires ; NULL = inconnu
    good_with_cats = db.Column(db.Enum('NONE', 'OK', 'REQUIRED', name='good_with_cats_enum'), nullable=True)
    good_with_children = db.Column(db.Boolean, nullable=True)
    # Intérieur uniquement / sortie possible / sortie nécessaire ; NULL = inconnu
    outdoor_access = db.Column(db.Enum('INDOOR', 'OPTIONAL', 'REQUIRED', name='outdoor_access_enum'), nullable=True)

    # Santé
    fiv = db.Column(db.Boolean, nullable=False)
    felv = db.Column(db.Boolean, nullable=False)

    # Description libre
    description = db.Column(db.Text, nullable=False)

    # Photos et relations (JSON)
    # none_as_null : None est stocké en NULL SQL et non en valeur JSON 'null'
    photos = db.Column(db.JSON(none_as_null=True), nullable=False)  # 1 à 8 photos
    linked_cats = db.Column(db.JSON(none_as_null=True), nullable=True)
    # Annonce de plusieurs chats : à adopter ensemble (TOGETHER) ou séparément (SEPARATE) ; ignoré pour un chat seul
    adoption_mode = db.Column(db.Enum('TOGETHER', 'SEPARATE', name='adoption_mode_enum'), default='TOGETHER', nullable=False)

    # Créateur de la fiche (users.id dans eraFA), renseigné par la page de création
    created_by = db.Column(db.Integer, nullable=False, index=True)

    # Horodatages
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    @property
    def photo_urls(self):
        """Retourne la liste ordonnée des URLs publiques des photos du chat."""
        if not self.photos or not isinstance(self.photos, list):
            return []
        return [photo_public_url(p) for p in self.photos if p]

    @property
    def primary_photo_url(self):
        """Retourne l'URL publique de la première photo ou None."""
        urls = self.photo_urls
        return urls[0] if urls else None

    @property
    def get_linked_cats(self):
        """Récupère la liste des objets AdoptionCat liés ayant le statut ACCEPTED."""
        if not self.linked_cats or not isinstance(self.linked_cats, list):
            return []
        return AdoptionCat.query.filter(
            AdoptionCat.uuid.in_(self.linked_cats),
            AdoptionCat.status == 'ACCEPTED'
        ).all()

    @property
    def is_multiple_adoption(self):
        """Indique si le chat fait l'objet d'une adoption conjointe avec au moins un chat ACCEPTED."""
        return len(self.get_linked_cats) > 0

    @property
    def adoption_group_size(self):
        """Nombre total de chats à adopter ensemble (le chat lui-même + ses chats liés ACCEPTED)."""
        return 1 + len(self.get_linked_cats)

    @property
    def adoption_group(self):
        """
        Chats de l'annonce : le chat lui-même et ses chats liés ACCEPTED, du plus ancien au plus récent.
        Le premier est le chat de référence de l'annonce (carte de l'accueil, URL canonique).
        """
        return sorted([self] + self.get_linked_cats, key=lambda c: c.id)

    @property
    def is_separate_adoption(self):
        """Annonce de plusieurs chats adoptables séparément (le mode est porté par le chat de référence)."""
        group = self.adoption_group
        return len(group) > 1 and group[0].adoption_mode == 'SEPARATE'

    @property
    def adoption_names_display(self):
        """Retourne par exemple 'Félix et Minouche' ou simplement 'Félix'."""
        return join_names_fr(c.name for c in self.adoption_group)

    @property
    def adoption_refs_display(self):
        """Retourne par exemple 'Félix (Réf: 39a0959b), Minouche (Réf: bb126b0b)'."""
        return ", ".join(f"{c.name} (Réf: {(c.uuid or '')[:8]})" for c in self.adoption_group)

    @property
    def adoption_sex_counts(self):
        """Nombre de mâles et de femelles de l'annonce : [(2, 'MALE'), (1, 'FEMALE')] (sexes absents omis)."""
        group = self.adoption_group
        counts = [(sum(1 for c in group if c.sex == sex), sex) for sex in ('MALE', 'FEMALE')]
        return [(n, sex) for n, sex in counts if n]

    @property
    def sex_label(self):
        return "Mâle" if self.sex == "MALE" else "Femelle"

    @property
    def age_years_months(self):
        """Calcule l'âge en années et mois à partir de la date de naissance."""
        if not self.birthdate:
            return "Âge non renseigné"
        today = date.today()
        years = today.year - self.birthdate.year
        months = today.month - self.birthdate.month
        if today.day < self.birthdate.day:
            months -= 1
        if months < 0:
            years -= 1
            months += 12

        parts = []
        if years > 0:
            parts.append(f"{years} an{'s' if years > 1 else ''}")
        if months > 0:
            parts.append(f"{months} mois")
        return " et ".join(parts) if parts else "Moins d'un mois"

    def to_dict(self):
        return {
            'id': self.id,
            'uuid': self.uuid,
            'cat_id': self.cat_id,
            'name': self.name,
            'sex': self.sex,
            'birthdate': self.birthdate.isoformat() if self.birthdate else None,
            'age': self.age_years_months,
            'breed': self.breed,
            'color': self.color,
            'status': self.status,
            'good_with_cats': self.good_with_cats,
            'good_with_children': self.good_with_children,
            'outdoor_access': self.outdoor_access,
            'fiv': self.fiv,
            'felv': self.felv,
            'description': self.description,
            'photos': self.photos,
            'linked_cats': self.linked_cats,
            'created_by': self.created_by,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f"<AdoptionCat {self.name} ({self.uuid})>"


class AdoptionCatPost(db.Model):
    """
    Publication d'une annonce sur un réseau social (Facebook, plus tard Instagram) : une ligne par chat et par
    réseau. Les chats d'une même annonce pointent vers le même post (post_id identique).
    post_id NULL avec last_error : la première publication a échoué (elle peut être retentée).
    """
    __tablename__ = 'adoption_cat_posts'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    cat_uuid = db.Column(db.String(36), db.ForeignKey('adoption_cats.uuid', ondelete='CASCADE'), nullable=False)
    network = db.Column(db.Enum('FACEBOOK', 'INSTAGRAM', name='social_network_enum'), nullable=False)
    post_id = db.Column(db.String(64), nullable=True, index=True)
    post_url = db.Column(db.String(255), nullable=True)
    last_error = db.Column(db.String(500), nullable=True)
    scheduled_at = db.Column(db.DateTime, nullable=True)  # mise en ligne programmée (heure locale), sinon NULL
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (db.UniqueConstraint('cat_uuid', 'network', name='idx_adoption_cat_posts_cat_network'),)


class User(UserMixin, db.Model):
    """
    Utilisateur eraFA (table 'users', partagée), en lecture seule.
    Seules les colonnes utiles à eraAdopt sont déclarées ; les comptes sont gérés exclusivement par eraFA.
    """
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(128), unique=True, nullable=False)
    usertype = db.Column(db.Integer)
    PrivStr = db.Column(db.String(64))
    FAname = db.Column(db.String(128), nullable=False)

    def get_id(self):
        # Même identifiant de session que eraFA (Flask-Login y stocke le username)
        return self.username

    def has_privilege(self, pn):
        """Même logique que User.hasPrivilege dans eraFA."""
        return bool(self.PrivStr) and pn < len(self.PrivStr) and self.PrivStr[pn] == '1'

    @property
    def is_adoption_admin(self):
        """Peut valider, publier et gérer les annonces (droit eraFA PRIV_ANNVAL)."""
        return self.has_privilege(PRIV_ANNVAL)

    @property
    def can_write_listings(self):
        """Peut créer des annonces depuis eraFA (droit eraFA PRIV_ANNAD)."""
        return self.has_privilege(PRIV_ANNAD)

    @property
    def display_name(self):
        return self.FAname or self.username

    def __repr__(self):
        return f"<User {self.username}>"


class AdoptionGroup:
    """Chats d'une même annonce (un chat seul, ou des chats liés entre eux), pour les listes d'administration."""

    def __init__(self, cats, creators_by_id, main_status):
        # Chats du statut listé d'abord, puis par ancienneté
        self.main_status = main_status
        self.cats = sorted(cats, key=lambda c: (c.status != main_status, c.id))
        self.creators_by_id = creators_by_id

    @property
    def main_cat(self):
        """Chat de référence du groupe (le plus ancien du statut listé) : sert d'identifiant dans les URLs."""
        return self.cats[0]

    @property
    def size(self):
        return len(self.cats)

    @property
    def names_display(self):
        return join_names_fr(c.name for c in self.cats)

    @property
    def creators_display(self):
        """Noms des créateurs distincts, ou None si aucun n'est connu."""
        names = []
        for c in self.cats:
            creator = self.creators_by_id.get(c.created_by)
            if creator and creator.display_name not in names:
                names.append(creator.display_name)
        return ", ".join(names) or None

    @property
    def photo_url(self):
        return next((c.primary_photo_url for c in self.cats if c.primary_photo_url), None)

    @property
    def created_at(self):
        return min(c.created_at for c in self.cats if c.status == self.main_status)

    @property
    def updated_at(self):
        return max(c.updated_at for c in self.cats if c.status == self.main_status)


def build_groups(main_status, linked_statuses=()):
    """
    Regroupe les fiches main_status avec leurs chats liés (composantes connexes du graphe linked_cats).
    Les liens sont suivis dans les deux sens (un lien saisi d'un seul côté suffit). Les chats liés ayant
    un statut de linked_statuses font aussi partie du groupe.
    Retourne une liste d'AdoptionGroup, du plus ancien au plus récent.
    """
    cats = AdoptionCat.query.filter(
        AdoptionCat.status.in_([main_status, *linked_statuses])
    ).order_by(AdoptionCat.id).all()
    by_uuid = {c.uuid: c for c in cats}

    neighbours = {c.uuid: set() for c in cats}
    for c in cats:
        for other in (c.linked_cats if isinstance(c.linked_cats, list) else []):
            if other in by_uuid and other != c.uuid:
                neighbours[c.uuid].add(other)
                neighbours[other].add(c.uuid)

    seen = set()
    components = []
    for c in cats:
        if c.status != main_status or c.uuid in seen:
            continue
        component, stack = [], [c.uuid]
        seen.add(c.uuid)
        while stack:
            current = stack.pop()
            component.append(by_uuid[current])
            for n in neighbours[current] - seen:
                seen.add(n)
                stack.append(n)
        components.append(component)

    # Créateurs chargés en une seule requête
    creator_ids = {c.created_by for comp in components for c in comp if c.created_by}
    creators_by_id = {u.id: u for u in User.query.filter(User.id.in_(creator_ids)).all()} if creator_ids else {}

    groups = [AdoptionGroup(comp, creators_by_id, main_status) for comp in components]
    groups.sort(key=lambda g: g.created_at)
    return groups


def build_review_groups():
    """
    Annonces à valider : fiches UNDER_REVIEW regroupées avec leurs chats liés. Les chats déjà ACCEPTED
    liés à une fiche en attente font partie du groupe (ils seront adoptés ensemble).
    """
    return build_groups('UNDER_REVIEW', ('ACCEPTED',))
