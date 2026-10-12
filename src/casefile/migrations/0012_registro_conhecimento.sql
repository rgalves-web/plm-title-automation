CREATE TABLE knowledge_registry_versions (
  version char(64) PRIMARY KEY,
  registry_key text NOT NULL,
  kind text NOT NULL,
  source_sha256 char(64) NOT NULL,
  original_path text NOT NULL,
  preserved_path text NOT NULL,
  scope jsonb NOT NULL,
  content jsonb NOT NULL,
  binding jsonb NOT NULL,
  registered_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX knowledge_registry_key ON knowledge_registry_versions(registry_key,registered_at);
