CREATE TABLE agent_skill_releases (
    release_id uuid PRIMARY KEY,
    feature_key text NOT NULL,
    skill_key text NOT NULL,
    version text NOT NULL,
    executor_id text NOT NULL,
    runtime_contract_version integer NOT NULL CHECK (runtime_contract_version = 1),
    manifest_jsonb jsonb NOT NULL,
    artifacts_jsonb jsonb NOT NULL,
    content_digest text NOT NULL CHECK (content_digest ~ '^[0-9a-f]{64}$'),
    source_ref text NOT NULL,
    validation_jsonb jsonb,
    status text NOT NULL CHECK (status IN ('draft', 'validated', 'published', 'retired')),
    created_at timestamptz NOT NULL DEFAULT now(),
    validated_at timestamptz,
    published_at timestamptz,
    UNIQUE (feature_key, skill_key, version),
    UNIQUE (release_id, feature_key, skill_key)
);
CREATE TABLE agent_skill_slots (
    feature_key text NOT NULL,
    site_key text NOT NULL,
    skill_key text NOT NULL,
    active_release_id uuid,
    previous_release_id uuid,
    revision bigint NOT NULL DEFAULT 0 CHECK (revision >= 0),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (feature_key, site_key, skill_key),
    FOREIGN KEY (active_release_id, feature_key, skill_key)
        REFERENCES agent_skill_releases (release_id, feature_key, skill_key),
    FOREIGN KEY (previous_release_id, feature_key, skill_key)
        REFERENCES agent_skill_releases (release_id, feature_key, skill_key)
);
CREATE FUNCTION agent_skill_release_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.status <> OLD.status AND (OLD.status, NEW.status) NOT IN
       (('draft', 'validated'), ('validated', 'published'), ('published', 'retired')) THEN
        RAISE EXCEPTION 'invalid skill release state transition';
    END IF;
    IF OLD.status IN ('published', 'retired') AND
       (NEW.manifest_jsonb, NEW.artifacts_jsonb, NEW.content_digest,
        NEW.feature_key, NEW.skill_key, NEW.version, NEW.executor_id,
        NEW.runtime_contract_version, NEW.source_ref, NEW.validation_jsonb)
       IS DISTINCT FROM
       (OLD.manifest_jsonb, OLD.artifacts_jsonb, OLD.content_digest,
        OLD.feature_key, OLD.skill_key, OLD.version, OLD.executor_id,
        OLD.runtime_contract_version, OLD.source_ref, OLD.validation_jsonb) THEN
        RAISE EXCEPTION 'published skill release is immutable';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER agent_skill_release_immutable_before_update
    BEFORE UPDATE ON agent_skill_releases
    FOR EACH ROW EXECUTE FUNCTION agent_skill_release_immutable();
CREATE FUNCTION agent_skill_release_no_delete() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'skill releases cannot be deleted';
END $$;
CREATE TRIGGER agent_skill_release_no_delete_before_delete
    BEFORE DELETE ON agent_skill_releases
    FOR EACH ROW EXECUTE FUNCTION agent_skill_release_no_delete();
