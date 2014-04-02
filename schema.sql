CREATE TABLE `reddit_submissions_processed` (
	`submission_id` VARCHAR(255) NOT NULL PRIMARY KEY,
	`url` TEXT
);

CREATE TABLE `config_variables` (
	`name` VARCHAR(255) NOT NULL,
	`value` TEXT
);