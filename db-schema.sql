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

  -- Entente et environnement (booléens: 1 = oui, 0 = non, NULL = inconnu)
  `good_with_cats` TINYINT(1) DEFAULT NULL COMMENT 'Vie avec d\'autres chats',
  `good_with_children` TINYINT(1) DEFAULT NULL COMMENT 'Vie avec des enfants',
  `outdoor_access` TINYINT(1) DEFAULT NULL COMMENT 'Accès à un extérieur nécessaire/souhaité',

  -- Santé (booléens: 1 = positif, 0 = négatif ; le test est toujours fait avant la mise à l'adoption)
  `fiv` TINYINT(1) NOT NULL COMMENT 'Test FIV (1=positif, 0=négatif)',
  `felv` TINYINT(1) NOT NULL COMMENT 'Test FeLV (1=positif, 0=négatif)',

  -- Description libre
  `description` TEXT NOT NULL COMMENT 'Historique, caractère, comportement, etc.',

  -- Photos (tableau JSON des noms de fichiers, de 1 à 6 photos ; la première est la photo principale)
  `photos` JSON NOT NULL COMMENT 'Tableau JSON des noms de fichiers des photos, 1 à 6',

  -- Chats liés (liste d'UUIDs au format JSON, ex: ["uuid-1", "uuid-2"] ; NULL = chat seul)
  `linked_cats` JSON DEFAULT NULL COMMENT 'Liste des UUIDs des chats à adopter ensemble',

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
  CONSTRAINT `chk_photos_limit` CHECK (JSON_LENGTH(`photos`) BETWEEN 1 AND 6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET FOREIGN_KEY_CHECKS = 1;
