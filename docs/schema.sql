-- Esquema de referencia sin datos ni credenciales.
-- Para actualizar usar python -m bd.preparar.

CREATE TABLE `users` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `username` varchar(24) NOT NULL,
  `password_hash` varchar(255) NOT NULL,
  `created_at` datetime NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_users_username` (`username`)
) ENGINE=InnoDB AUTO_INCREMENT=261 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `participants` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `nick` varchar(24) NOT NULL,
  `is_active` tinyint(1) NOT NULL DEFAULT 1,
  `created_at` datetime NOT NULL DEFAULT current_timestamp(),
  `updated_at` datetime NOT NULL DEFAULT current_timestamp(),
  `version` int(11) NOT NULL DEFAULT 1,
  `owner_id` int(11) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_participants_owner_nick` (`owner_id`,`nick`),
  KEY `ix_participants_is_active` (`is_active`),
  KEY `ix_participants_owner_id` (`owner_id`),
  CONSTRAINT `fk_participants_owner` FOREIGN KEY (`owner_id`) REFERENCES `users` (`id`),
  CONSTRAINT `ck_participants_nick_length` CHECK (char_length(`nick`) between 2 and 24),
  CONSTRAINT `ck_participants_version` CHECK (`version` >= 1),
  CONSTRAINT `ck_participants_is_active` CHECK (`is_active` in (0,1))
) ENGINE=InnoDB AUTO_INCREMENT=652 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `tournaments` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `owner_id` int(11) NOT NULL,
  `name` varchar(80) NOT NULL,
  `format` varchar(24) NOT NULL,
  `min_participants` int(11) NOT NULL,
  `max_participants` int(11) NOT NULL,
  `request_key` varchar(36) NOT NULL,
  `created_at` datetime NOT NULL DEFAULT current_timestamp(),
  `version` int(11) NOT NULL DEFAULT 1,
  `finished_at` datetime DEFAULT NULL,
  `pair_mode` varchar(12) NOT NULL DEFAULT 'individual',
  `league_rounds` int(11) NOT NULL DEFAULT 1,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_tournament_request` (`owner_id`,`request_key`),
  KEY `ix_tournaments_owner_id` (`owner_id`),
  CONSTRAINT `tournaments_ibfk_1` FOREIGN KEY (`owner_id`) REFERENCES `users` (`id`),
  CONSTRAINT `ck_tournament_limits` CHECK (`min_participants` >= 2 and `max_participants` >= `min_participants` and `max_participants` <= 128),
  CONSTRAINT `ck_tournament_format` CHECK (`format` in ('single_elimination','double_elimination','groups_knockout','league'))
) ENGINE=InnoDB AUTO_INCREMENT=102 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `user_sessions` (
  `token_hash` varchar(64) NOT NULL,
  `user_id` int(11) NOT NULL,
  `expires_at` datetime NOT NULL,
  PRIMARY KEY (`token_hash`),
  KEY `ix_user_sessions_user_id` (`user_id`),
  KEY `ix_user_sessions_expires_at` (`expires_at`),
  CONSTRAINT `fk_sessions_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `participant_logos` (
  `participant_id` int(11) NOT NULL,
  `content` mediumblob NOT NULL,
  PRIMARY KEY (`participant_id`),
  CONSTRAINT `fk_logos_participant` FOREIGN KEY (`participant_id`) REFERENCES `participants` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `tournament_entries` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `tournament_id` int(11) NOT NULL,
  `participant_id` int(11) NOT NULL,
  `draw_position` int(11) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_tournament_participant` (`tournament_id`,`participant_id`),
  UNIQUE KEY `uq_tournament_seed` (`tournament_id`,`draw_position`),
  KEY `ix_tournament_entries_participant_id` (`participant_id`),
  KEY `ix_tournament_entries_tournament_id` (`tournament_id`),
  CONSTRAINT `tournament_entries_ibfk_1` FOREIGN KEY (`tournament_id`) REFERENCES `tournaments` (`id`) ON DELETE CASCADE,
  CONSTRAINT `tournament_entries_ibfk_2` FOREIGN KEY (`participant_id`) REFERENCES `participants` (`id`),
  CONSTRAINT `ck_entry_position` CHECK (`draw_position` >= 1)
) ENGINE=InnoDB AUTO_INCREMENT=428 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `tournament_stages` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `tournament_id` int(11) NOT NULL,
  `kind` varchar(16) NOT NULL,
  `name` varchar(60) NOT NULL,
  `position` int(11) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_tournament_stage_position` (`tournament_id`,`position`),
  KEY `ix_tournament_stages_tournament_id` (`tournament_id`),
  CONSTRAINT `tournament_stages_ibfk_1` FOREIGN KEY (`tournament_id`) REFERENCES `tournaments` (`id`) ON DELETE CASCADE,
  CONSTRAINT `ck_stage_kind` CHECK (`kind` in ('knockout','upper','lower','final','group','league'))
) ENGINE=InnoDB AUTO_INCREMENT=178 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `group_draws` (
  `stage_id` int(11) NOT NULL,
  `entry_id` int(11) NOT NULL,
  `draw_order` int(11) NOT NULL,
  PRIMARY KEY (`stage_id`,`entry_id`),
  UNIQUE KEY `uq_group_draw_order` (`stage_id`,`draw_order`),
  KEY `entry_id` (`entry_id`),
  CONSTRAINT `group_draws_ibfk_1` FOREIGN KEY (`stage_id`) REFERENCES `tournament_stages` (`id`) ON DELETE CASCADE,
  CONSTRAINT `group_draws_ibfk_2` FOREIGN KEY (`entry_id`) REFERENCES `tournament_entries` (`id`) ON DELETE CASCADE,
  CONSTRAINT `ck_group_draw_order` CHECK (`draw_order` >= 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `tournament_group_members` (
  `stage_id` int(11) NOT NULL,
  `entry_id` int(11) NOT NULL,
  PRIMARY KEY (`stage_id`,`entry_id`),
  UNIQUE KEY `uq_group_member_entry` (`entry_id`),
  CONSTRAINT `tournament_group_members_ibfk_1` FOREIGN KEY (`stage_id`) REFERENCES `tournament_stages` (`id`) ON DELETE CASCADE,
  CONSTRAINT `tournament_group_members_ibfk_2` FOREIGN KEY (`entry_id`) REFERENCES `tournament_entries` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `tournament_partners` (
  `entry_id` int(11) NOT NULL,
  `participant_id` int(11) NOT NULL,
  PRIMARY KEY (`entry_id`),
  KEY `ix_tournament_partners_participant_id` (`participant_id`),
  CONSTRAINT `tournament_partners_ibfk_1` FOREIGN KEY (`entry_id`) REFERENCES `tournament_entries` (`id`) ON DELETE CASCADE,
  CONSTRAINT `tournament_partners_ibfk_2` FOREIGN KEY (`participant_id`) REFERENCES `participants` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `tournament_rounds` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `stage_id` int(11) NOT NULL,
  `number` int(11) NOT NULL,
  `name` varchar(60) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_stage_round` (`stage_id`,`number`),
  KEY `ix_tournament_rounds_stage_id` (`stage_id`),
  CONSTRAINT `tournament_rounds_ibfk_1` FOREIGN KEY (`stage_id`) REFERENCES `tournament_stages` (`id`) ON DELETE CASCADE,
  CONSTRAINT `ck_round_number` CHECK (`number` >= 1)
) ENGINE=InnoDB AUTO_INCREMENT=415 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `tournament_matches` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `round_id` int(11) NOT NULL,
  `position` int(11) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_round_match` (`round_id`,`position`),
  KEY `ix_tournament_matches_round_id` (`round_id`),
  CONSTRAINT `tournament_matches_ibfk_1` FOREIGN KEY (`round_id`) REFERENCES `tournament_rounds` (`id`) ON DELETE CASCADE,
  CONSTRAINT `ck_match_position` CHECK (`position` >= 1)
) ENGINE=InnoDB AUTO_INCREMENT=681 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `match_results` (
  `match_id` int(11) NOT NULL,
  `home_score` int(11) NOT NULL,
  `away_score` int(11) NOT NULL,
  `winner_entry_id` int(11) DEFAULT NULL,
  `recorded_at` datetime NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`match_id`),
  KEY `ix_match_results_winner_entry_id` (`winner_entry_id`),
  CONSTRAINT `match_results_ibfk_1` FOREIGN KEY (`match_id`) REFERENCES `tournament_matches` (`id`) ON DELETE CASCADE,
  CONSTRAINT `match_results_ibfk_2` FOREIGN KEY (`winner_entry_id`) REFERENCES `tournament_entries` (`id`),
  CONSTRAINT `ck_result_scores` CHECK (`home_score` between 0 and 99 and `away_score` between 0 and 99)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `tournament_slots` (
  `match_id` int(11) NOT NULL,
  `slot_number` int(11) NOT NULL,
  `entry_id` int(11) DEFAULT NULL,
  `source_match_id` int(11) DEFAULT NULL,
  `source_outcome` varchar(6) DEFAULT NULL,
  `source_group_id` int(11) DEFAULT NULL,
  `group_rank` int(11) DEFAULT NULL,
  PRIMARY KEY (`match_id`,`slot_number`),
  KEY `ix_tournament_slots_entry_id` (`entry_id`),
  KEY `ix_tournament_slots_source_group_id` (`source_group_id`),
  KEY `ix_tournament_slots_source_match_id` (`source_match_id`),
  CONSTRAINT `tournament_slots_ibfk_1` FOREIGN KEY (`match_id`) REFERENCES `tournament_matches` (`id`) ON DELETE CASCADE,
  CONSTRAINT `tournament_slots_ibfk_2` FOREIGN KEY (`entry_id`) REFERENCES `tournament_entries` (`id`),
  CONSTRAINT `tournament_slots_ibfk_3` FOREIGN KEY (`source_match_id`) REFERENCES `tournament_matches` (`id`),
  CONSTRAINT `tournament_slots_ibfk_4` FOREIGN KEY (`source_group_id`) REFERENCES `tournament_stages` (`id`),
  CONSTRAINT `ck_slot_number` CHECK (`slot_number` in (1,2)),
  CONSTRAINT `ck_slot_source` CHECK (`entry_id` is not null and `source_match_id` is null and `source_outcome` is null and `source_group_id` is null and `group_rank` is null or `entry_id` is null and `source_match_id` is not null and `source_outcome` is not null and `source_outcome` in ('winner','loser') and `source_group_id` is null and `group_rank` is null or `entry_id` is null and `source_match_id` is null and `source_outcome` is null and `source_group_id` is not null and `group_rank` is not null and `group_rank` in (1,2) or `entry_id` is null and `source_match_id` is null and `source_outcome` is null and `source_group_id` is null and `group_rank` is null)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

