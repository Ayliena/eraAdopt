-- ==============================================================================
-- Schema SQL pour eraAdopt - Table des chats à l'adoption
-- Compatible MySQL / MariaDB (InnoDB, utf8mb4)
-- ==============================================================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

DROP TABLE IF EXISTS `adoption_cats`;

CREATE TABLE `adoption_cats` (
  -- Identifiants
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `uuid` VARCHAR(36) NOT NULL DEFAULT (UUID()),
  `cat_id` INT(11) NOT NULL COMMENT 'ID du chat dans eraFA (càd: cats.id) ; négatif pour les fiches de test',

  -- Statut de la fiche
  `status` ENUM('UNDER_REVIEW', 'ACCEPTED', 'ARCHIVED') NOT NULL DEFAULT 'UNDER_REVIEW',

  -- Informations générales
  `name` VARCHAR(100) NOT NULL,
  `sex` ENUM('MALE', 'FEMALE') NOT NULL,
  `birthdate` DATE NOT NULL COMMENT 'Date de naissance (estimée ou réelle) pour calculer l\'âge',
  `breed` VARCHAR(100) NOT NULL DEFAULT 'Européen' COMMENT 'Race du chat',
  `color` VARCHAR(64) NOT NULL COMMENT 'Couleur et type de poil (texte issu d\'eraFA à la création, ex. « Tigré, poil long »)',

  -- Entente et environnement (booléens: 1 = oui, 0 = non, NULL = inconnu)
  `good_with_cats` ENUM('NONE', 'OK', 'REQUIRED') DEFAULT NULL COMMENT 'Vie avec d\'autres chats : sans autres chats (NONE), autres chats OK (OK), autres chats nécessaires (REQUIRED) ; NULL = inconnu',
  `good_with_children` TINYINT(1) DEFAULT NULL COMMENT 'Vie avec des enfants',
  `outdoor_access` ENUM('INDOOR', 'OPTIONAL', 'REQUIRED') DEFAULT NULL COMMENT 'Accès extérieur : intérieur uniquement (INDOOR), sortie possible (OPTIONAL), sortie nécessaire (REQUIRED) ; NULL = inconnu',

  -- Santé (booléens: 1 = positif, 0 = négatif ; le test est toujours fait avant la mise à l'adoption)
  `fiv` TINYINT(1) NOT NULL COMMENT 'Test FIV (1=positif, 0=négatif)',
  `felv` TINYINT(1) NOT NULL COMMENT 'Test FeLV (1=positif, 0=négatif)',

  -- Description libre
  `description` TEXT NOT NULL COMMENT 'Historique, caractère, comportement, etc.',

  -- Photos (tableau JSON des noms de fichiers, de 1 à 8 photos ; la première est la photo principale)
  `photos` JSON NOT NULL COMMENT 'Tableau JSON des noms de fichiers des photos, 1 à 8',

  -- Chats liés (liste d'UUIDs au format JSON, ex: ["uuid-1", "uuid-2"] ; NULL = chat seul)
  `linked_cats` JSON DEFAULT NULL COMMENT 'Liste des UUIDs des chats à adopter ensemble',

  -- Mode d'adoption d'une annonce de plusieurs chats (ignoré pour un chat seul)
  `adoption_mode` ENUM('TOGETHER', 'SEPARATE') NOT NULL DEFAULT 'TOGETHER' COMMENT 'Annonce de plusieurs chats : à adopter ensemble (TOGETHER) ou séparément (SEPARATE)',

  -- Créateur de la fiche (compte eraFA)
  `created_by` INT(11) NOT NULL COMMENT 'Créateur de la fiche (càd: users.id)',

  -- Horodatages
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  PRIMARY KEY (`id`),
  UNIQUE KEY `idx_adoption_cats_uuid` (`uuid`),
  KEY `idx_adoption_cats_cat_id` (`cat_id`),
  KEY `idx_adoption_cats_status` (`status`),
  KEY `idx_adoption_cats_name` (`name`),
  KEY `idx_adoption_cats_created_by` (`created_by`),
  CONSTRAINT `chk_photos_limit` CHECK (JSON_LENGTH(`photos`) BETWEEN 1 AND 8)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Publications des annonces sur les réseaux sociaux (Facebook, plus tard Instagram) : une ligne par chat et par
-- réseau ; les chats d'une même annonce pointent vers le même post. post_id NULL + last_error : la première
-- publication a échoué (elle peut être retentée). Supprimer une annonce ne supprime pas le post sur le réseau.
CREATE TABLE IF NOT EXISTS `adoption_cat_posts` (
  `id` INT(11) NOT NULL AUTO_INCREMENT,
  `cat_uuid` VARCHAR(36) NOT NULL COMMENT 'Chat de l''annonce (adoption_cats.uuid)',
  `network` ENUM('FACEBOOK', 'INSTAGRAM') NOT NULL COMMENT 'Réseau social',
  `post_id` VARCHAR(64) DEFAULT NULL COMMENT 'Identifiant du post sur le réseau (NULL si la publication a échoué)',
  `post_url` VARCHAR(255) DEFAULT NULL COMMENT 'Lien public du post',
  `last_error` VARCHAR(500) DEFAULT NULL COMMENT 'Dernière erreur du réseau (publication ou mise à jour)',
  `scheduled_at` DATETIME DEFAULT NULL COMMENT 'Mise en ligne programmée du post (heure de Paris) ; NULL : publié immédiatement',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  PRIMARY KEY (`id`),
  UNIQUE KEY `idx_adoption_cat_posts_cat_network` (`cat_uuid`, `network`),
  KEY `idx_adoption_cat_posts_post_id` (`post_id`),
  CONSTRAINT `fk_adoption_cat_posts_cat` FOREIGN KEY (`cat_uuid`) REFERENCES `adoption_cats` (`uuid`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET FOREIGN_KEY_CHECKS = 1;
