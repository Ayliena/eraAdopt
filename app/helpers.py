import unicodedata
import re
from urllib.parse import urlencode, quote

def slugify_name(name: str) -> str:
    """
    Transforme un nom (avec accents, espaces ou caractères spéciaux) en ASCII simple.
    Exemple: 'Félix' -> 'Felix', 'Câline' -> 'Caline', 'Chloé & Minou' -> 'Chloe_Minou'
    """
    if not name:
        return "chat"
    # Décomposition des accents puis suppression des caractères non-ASCII
    text = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('utf-8')
    # Remplacer les espaces par des underscores
    text = re.sub(r'\s+', '_', text.strip())
    # Ne garder que lettres, chiffres, underscores et tirets
    text = re.sub(r'[^a-zA-Z0-9_-]', '', text)
    return text or "chat"

def build_contact_mailto(cat, address: str) -> str:
    """
    Construit le lien mailto pré-rempli pour une demande d'adoption.
    Sujet et corps sont entièrement encodés : un nom contenant '&', '#' ou '?' ne coupe plus le mail.
    """
    if cat.is_multiple_adoption:
        subject = f"Demande d'adoption conjointe pour {cat.adoption_names_display}"
        intro = f"Je vous contacte concernant l'adoption conjointe de {cat.adoption_refs_display}."
    else:
        subject = f"Demande d'adoption pour {cat.name} (Ref: {(cat.uuid or '')[:8]})"
        intro = f"Je vous contacte concernant l'adoption de {cat.adoption_refs_display}."

    body = "\r\n".join([
        "Bonjour l'association ERA,",
        "",
        intro,
        "",
        "Voici quelques informations sur mon foyer et mon projet d'adoption :",
        "- Ville et type de logement (appartement / maison, avec ou sans extérieur) : ",
        "- Composition du foyer (adultes, enfants) : ",
        "- Présence d'autres animaux : ",
        "",
        "Merci d'avance pour votre retour,",
        "",
    ])
    # quote (et non quote_plus) : les espaces deviennent %20, les clients mail n'interprètent pas '+'
    return f"mailto:{address}?" + urlencode({'subject': subject, 'body': body}, quote_via=quote)
