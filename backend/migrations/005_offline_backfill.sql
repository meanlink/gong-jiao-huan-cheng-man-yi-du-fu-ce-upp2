CREATE TABLE IF NOT EXISTS backfill_batch (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    plan_id bigint NOT NULL REFERENCES route_plan(id),
    batch_ref text NOT NULL CHECK (char_length(batch_ref) BETWEEN 3 AND 60),
    status text NOT NULL DEFAULT 'staging' CHECK (status IN ('staging','merged','cancelled')),
    expected_items integer CHECK (expected_items > 0),
    received_items integer NOT NULL DEFAULT 0 CHECK (received_items >= 0),
    created_by text NOT NULL REFERENCES staff_account(email),
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_by text REFERENCES staff_account(email),
    completed_at timestamptz,
    closing_note text CHECK (closing_note IS NULL OR char_length(closing_note) BETWEEN 4 AND 250),
    UNIQUE (plan_id, batch_ref),
    UNIQUE (plan_id, id),
    CHECK ((status <> 'staging') = (completed_at IS NOT NULL)),
    CHECK ((completed_by IS NULL) = (completed_at IS NULL)),
    CHECK (status <> 'cancelled' OR received_items = 0)
);

CREATE INDEX IF NOT EXISTS backfill_batch_staging ON backfill_batch (plan_id) WHERE status = 'staging';

CREATE TABLE IF NOT EXISTS backfill_item (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    plan_id bigint NOT NULL REFERENCES route_plan(id),
    batch_id bigint NOT NULL,
    offline_ref text NOT NULL CHECK (char_length(offline_ref) BETWEEN 1 AND 40),
    passenger_hash text NOT NULL,
    cohort text NOT NULL CHECK (cohort IN ('baseline','trial')),
    trip_day date NOT NULL,
    filled_at timestamptz NOT NULL,
    time_band text CHECK (time_band IN ('peak','offpeak')),
    rating smallint NOT NULL CHECK (rating BETWEEN 1 AND 5),
    received_by text NOT NULL REFERENCES staff_account(email),
    received_at timestamptz NOT NULL DEFAULT now(),
    sample_id bigint REFERENCES survey_sample(id),
    outcome text CHECK (outcome IN ('first','superseded','duplicate')),
    basis text,
    merged_by text REFERENCES staff_account(email),
    merged_at timestamptz,
    UNIQUE (plan_id, offline_ref),
    FOREIGN KEY (plan_id, batch_id) REFERENCES backfill_batch(plan_id, id),
    CHECK ((sample_id IS NULL) = (merged_at IS NULL)),
    CHECK ((merged_at IS NULL) = (merged_by IS NULL))
);

CREATE INDEX IF NOT EXISTS backfill_item_batch ON backfill_item (plan_id, batch_id, id);
CREATE INDEX IF NOT EXISTS backfill_item_pending ON backfill_item (plan_id, batch_id) WHERE sample_id IS NULL;

ALTER TABLE survey_sample ADD COLUMN IF NOT EXISTS filled_at timestamptz;
ALTER TABLE survey_sample ADD COLUMN IF NOT EXISTS source text NOT NULL DEFAULT 'online';
ALTER TABLE survey_sample ADD COLUMN IF NOT EXISTS offline_ref text;
ALTER TABLE survey_sample ADD COLUMN IF NOT EXISTS merge_note text;

DO $$ BEGIN
    ALTER TABLE survey_sample ADD CONSTRAINT survey_sample_source_check
        CHECK (source IN ('online','backfill'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    ALTER TABLE survey_sample ADD CONSTRAINT survey_sample_backfill_fields
        CHECK (source <> 'backfill' OR (filled_at IS NOT NULL AND offline_ref IS NOT NULL));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    ALTER TABLE survey_sample ADD CONSTRAINT survey_sample_online_fields
        CHECK (source <> 'online' OR (filled_at IS NULL AND offline_ref IS NULL));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE UNIQUE INDEX IF NOT EXISTS one_offline_ref_per_plan
    ON survey_sample (plan_id, offline_ref) WHERE offline_ref IS NOT NULL;
