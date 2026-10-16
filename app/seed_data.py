"""
Jeu de données de test (site de développement uniquement), rétabli par /seed-test.

Chaque fiche est retrouvée par son uuid : elle est recréée si elle a été supprimée, et toutes ses valeurs
sont rétablies si elle a été modifiée. Les photos « réelles » sont recopiées depuis le dossier de sauvegarde
(SEED_PHOTO_BACKUP) si elles ont disparu ; les photos de couleur unie des fiches en attente sont régénérées.
"""
from datetime import date, datetime

FELIX_MINOUCHE_DESC = (
    "Félix et Minouche sont inséparables ! Lui est un jeune chat très affectueux et joueur, propre et sociable, "
    "qui adore les siestes sur les genoux. Elle est une petite minette pleine de douceur, très complice avec lui. "
    "Ils cherchent une famille qui les accueillera tous les deux."
)
FELIX_MINOUCHE_PHOTOS = ["Felix_39a0959b_1.png", "Felix_39a0959b_2.png", "Felix_39a0959b_3.png", "Minouche_bb126b0b_1.png"]
DATHEA_HECTOR_DESC = "Deux petits chats adorables qu'on ne veut pas mettre en adoption, mais pour le site de test c'est OK..."
DATHEA_HECTOR_PHOTOS = ["DATHEA_3b914adc_1.jpg", "DATHEA_3b914adc_2.jpg", "DATHEA_3b914adc_3.jpg"]
KYPROSA_BURRATA_DESC = (
    "Kyprosa (tigrée écaille) et Burrata (blanc) sont deux jeunes très joueurs et très copains.  Ils sont donc à "
    "l'adoption ensemble, sans sortie possible, comme Burrata, étant sourd, serait immédiatement en danger à "
    "l'extérieur.\r\n\r\n"
    "Kyprosa est une jeune maman de deux ans, qui a gardé un caractère de chaton et qui est curieuse et active comme "
    "si elle avait encore 6 mois.  Câline mais avec un caractère indépendant, elle sera toujours au rendez-vous des "
    "que vous ouvrez un paquet de friandises!\r\n"
    "Burrata est un jeune actif et joueur et qui a effectivement 6 mois, il apprécie la compagnie de Kyprosa avec qui "
    "il enchaîne des séances de jeu de folie.  Burrata a tout de même un caractère plus pot-de-colle et il a tendance "
    "à être toujours proche des humains en recherche de câlins qu'il échange contre des ronronnements non-stop.\r\n\r\n"
    "Ce couple d'exception cherche une famille pour la vie, prête a s'occuper d'eux en acceptant Kyprosa qui ne peut "
    "pas s'empêcher de mettre son nez partout (surtout les assiettes pleines), Burrata qui vient se coller la nuit pour "
    "dormir et les deux ensembles qui se coursent partout lors de leurs séances de jeu."
)
KYPROSA_BURRATA_PHOTOS = [f"KYPROSA_36e050aa_{i}.jpg" for i in range(1, 7)]
TRIO_PHOTOS = ["Titi_Toto_Tutu_bec30e09_1.png", "Titi_Toto_Tutu_bec30e09_2.png", "Titi_Toto_Tutu_bec30e09_3.png"]
TRIO_UUIDS = ["bec30e09-342e-4618-9384-c5590b0e9348", "85552ce0-829d-4839-a875-0b7cd1be4dbb",
              "e912a0a8-a794-441f-8915-db4d1196ab0a"]

ENTENTE_OK = dict(good_with_cats=True, good_with_children=True, outdoor_access='INDOOR', fiv=False, felv=False)
# Fiches en attente : entente à renseigner lors de la validation (FIV / FeLV obligatoires, négatifs par défaut)
A_RENSEIGNER = dict(good_with_cats=None, good_with_children=None, outdoor_access=None, fiv=False, felv=False)

# Fiches de test sans chat eraFA : cat_id négatif (= -id en base), qui ne peut correspondre à aucun vrai chat
# (eraFA s'en sert pour bloquer les doublons). Créateur : compte de test existant.
TEST_CREATOR = 125

SEED_CATS = [
    # --- Annonces publiées
    dict(uuid="39a0959b-e698-4fdf-9a13-1629ddd260c5", cat_id=-1, status="ACCEPTED", name="Félix", sex="MALE",
         birthdate=date(2023, 4, 15), breed="Européen", **ENTENTE_OK, description=FELIX_MINOUCHE_DESC,
         photos=FELIX_MINOUCHE_PHOTOS, linked_cats=["bb126b0b-adb0-45d3-95a3-8fe6e178ddfa"],
         created_by=TEST_CREATOR, created_at=datetime(2026, 9, 20, 18, 39, 26)),
    dict(uuid="bb126b0b-adb0-45d3-95a3-8fe6e178ddfa", cat_id=-2, status="ACCEPTED", name="Minouche", sex="FEMALE",
         birthdate=date(2023, 5, 1), breed="Européen tigré", **ENTENTE_OK, description=FELIX_MINOUCHE_DESC,
         photos=FELIX_MINOUCHE_PHOTOS, linked_cats=["39a0959b-e698-4fdf-9a13-1629ddd260c5"],
         created_by=TEST_CREATOR, created_at=datetime(2026, 9, 21, 1, 38, 47)),
    dict(uuid="9d367269-07ea-4ad4-9f5b-ddae14a420d3", cat_id=-3, status="ACCEPTED", name="Simba", sex="MALE",
         birthdate=date(2022, 6, 10), breed="Croisé roux",
         good_with_cats=True, good_with_children=False, outdoor_access='REQUIRED', fiv=False, felv=False,
         description="Grand explorateur calme et indépendant. Un jardin sera nécessaire pour son épanouissement.",
         photos=["Simba_9d367269_1.png"], linked_cats=None, created_by=TEST_CREATOR, created_at=datetime(2026, 9, 21, 1, 38, 47)),
    dict(uuid="3b914adc-1fd0-409a-a2da-c8183dcdb428", cat_id=6743, status="ACCEPTED", name="DATHEA", sex="FEMALE",
         birthdate=date(2022, 4, 1), breed="Européen", **ENTENTE_OK, description=DATHEA_HECTOR_DESC,
         photos=DATHEA_HECTOR_PHOTOS, linked_cats=["99205800-d497-4323-8b89-c7b4f70a9b66"],
         created_by=125, created_at=datetime(2026, 10, 4, 23, 8, 38)),
    dict(uuid="99205800-d497-4323-8b89-c7b4f70a9b66", cat_id=6585, status="ACCEPTED", name="HECTOR", sex="MALE",
         birthdate=date(2025, 4, 15), breed="Européen", **ENTENTE_OK, description=DATHEA_HECTOR_DESC,
         photos=DATHEA_HECTOR_PHOTOS, linked_cats=["3b914adc-1fd0-409a-a2da-c8183dcdb428"],
         created_by=125, created_at=datetime(2026, 10, 4, 23, 8, 38)),
    dict(uuid="4eeb31b9-1a6e-46f9-812a-a5e07cba6e9a", cat_id=6741, status="ACCEPTED", name="CHAT TEST 1", sex="MALE",
         birthdate=date(2020, 12, 21), breed="Européen",
         good_with_cats=False, good_with_children=False, outdoor_access='REQUIRED', fiv=False, felv=False,
         description="Un chat pas commode...", photos=["CHAT_TEST_1_4eeb31b9_1.jpg"], linked_cats=None,
         created_by=125, created_at=datetime(2026, 10, 4, 23, 27, 47)),
    dict(uuid="36e050aa-1f66-4196-9b0f-35741c066185", cat_id=7342, status="ACCEPTED", name="KYPROSA", sex="FEMALE",
         birthdate=date(2024, 7, 1), breed="Européen", **ENTENTE_OK, description=KYPROSA_BURRATA_DESC,
         adoption_mode="SEPARATE", photos=KYPROSA_BURRATA_PHOTOS, linked_cats=["87c7de19-b443-4449-b885-f4db21140a48"],
         created_by=1, created_at=datetime(2026, 10, 10, 21, 21, 13)),
    dict(uuid="87c7de19-b443-4449-b885-f4db21140a48", cat_id=7376, status="ACCEPTED", name="BURRATA", sex="MALE",
         birthdate=date(2026, 4, 5), breed="Européen", **ENTENTE_OK, description=KYPROSA_BURRATA_DESC,
         adoption_mode="SEPARATE", photos=KYPROSA_BURRATA_PHOTOS, linked_cats=["36e050aa-1f66-4196-9b0f-35741c066185"],
         created_by=1, created_at=datetime(2026, 10, 10, 21, 21, 13)),

    # --- Annonces en attente de validation (photos de couleur unie, régénérées)
    dict(uuid="2065b553-df89-4372-a43b-123066ec308b", cat_id=-9, status="UNDER_REVIEW", name="Grisou", sex="MALE",
         birthdate=date(2021, 3, 2), breed="Européen", **A_RENSEIGNER,
         description="Fiche de test en attente de validation (Grisou).",
         photos=["Grisou_2065b553_1.png", "Grisou_2065b553_2.png"], linked_cats=None,
         created_by=TEST_CREATOR, created_at=datetime(2026, 10, 4, 17, 24, 9)),
    dict(uuid=TRIO_UUIDS[0], cat_id=-13, status="UNDER_REVIEW", name="Titi", sex="MALE",
         birthdate=date(2024, 2, 10), breed="Européen", **A_RENSEIGNER,
         description="Fiche de test en attente de validation (Titi, Toto et Tutu, adoptables séparément).",
         adoption_mode="SEPARATE", photos=TRIO_PHOTOS, linked_cats=[TRIO_UUIDS[1], TRIO_UUIDS[2]],
         created_by=TEST_CREATOR, created_at=datetime(2026, 10, 4, 17, 57, 32)),
    dict(uuid=TRIO_UUIDS[1], cat_id=-14, status="UNDER_REVIEW", name="Toto", sex="MALE",
         birthdate=date(2022, 9, 15), breed="Européen", **A_RENSEIGNER,
         description="Fiche de test en attente de validation (Titi, Toto et Tutu, adoptables séparément).",
         adoption_mode="SEPARATE", photos=TRIO_PHOTOS, linked_cats=[TRIO_UUIDS[0], TRIO_UUIDS[2]],
         created_by=TEST_CREATOR, created_at=datetime(2026, 10, 4, 17, 57, 32)),
    dict(uuid=TRIO_UUIDS[2], cat_id=-15, status="UNDER_REVIEW", name="Tutu", sex="FEMALE",
         birthdate=date(2024, 2, 10), breed="Européen", **A_RENSEIGNER,
         description="Fiche de test en attente de validation (Titi, Toto et Tutu, adoptables séparément).",
         adoption_mode="SEPARATE", photos=TRIO_PHOTOS, linked_cats=[TRIO_UUIDS[0], TRIO_UUIDS[1]],
         created_by=TEST_CREATOR, created_at=datetime(2026, 10, 4, 17, 57, 32)),
]

# Photos de couleur unie (fiches en attente), régénérées à chaque appel : fichier -> couleur RGB
COLOR_PHOTOS = {
    "Grisou_2065b553_1.png": (224, 122, 95),
    "Grisou_2065b553_2.png": (43, 122, 120),
    "Titi_Toto_Tutu_bec30e09_1.png": (242, 204, 143),
    "Titi_Toto_Tutu_bec30e09_2.png": (224, 122, 95),
    "Titi_Toto_Tutu_bec30e09_3.png": (43, 122, 120),
}
