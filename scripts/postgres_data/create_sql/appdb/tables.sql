-- AUTO-GENERATED FILE. DO NOT EDIT MANUALLY.
-- Generated from https://github.com/EOSC-Data-Commons/data-commons-search/blob/main/src/data_commons_search/db.py
CREATE TABLE users (
	sub VARCHAR(255) NOT NULL,
	email VARCHAR(320),
	name VARCHAR(255),
	username VARCHAR(255),
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (sub)
);

CREATE TABLE conversations (
	user_id VARCHAR(255) NOT NULL,
	thread_id VARCHAR(255) NOT NULL,
	label VARCHAR(255) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (user_id, thread_id),
	FOREIGN KEY(user_id) REFERENCES users (sub) ON DELETE CASCADE
);

CREATE TABLE messages (
	id SERIAL NOT NULL,
	user_id VARCHAR(255) NOT NULL,
	thread_id VARCHAR(255) NOT NULL,
	type VARCHAR(64) NOT NULL,
	content JSONB NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(user_id, thread_id) REFERENCES conversations (user_id, thread_id) ON DELETE CASCADE
);
