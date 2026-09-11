-- Methodology is separate from source_files/claim evidence.
CREATE TABLE knowledge_contexts (
    session_id bigint PRIMARY KEY REFERENCES model_sessions,
    unit_id bigint NOT NULL REFERENCES units,
    manifest jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (session_id, unit_id)
);
CREATE TABLE knowledge_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id bigint NOT NULL,
    unit_id bigint NOT NULL,
    kind text NOT NULL CHECK (kind IN ('offered','queried','applied','reviewed','legacy_read','candidate_written')),
    detail jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (session_id, unit_id) REFERENCES knowledge_contexts(session_id, unit_id)
);
CREATE INDEX knowledge_events_unit ON knowledge_events(unit_id, session_id);
