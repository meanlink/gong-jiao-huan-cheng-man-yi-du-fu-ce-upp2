CREATE TABLE IF NOT EXISTS staff_account (
    email text PRIMARY KEY,
    display_name text NOT NULL,
    role text NOT NULL CHECK (role IN ('collector','analyst','director')),
    password_hash text NOT NULL
);

CREATE TABLE IF NOT EXISTS route_plan (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code text UNIQUE NOT NULL,
    hub text NOT NULL,
    feeder text NOT NULL,
    connection text NOT NULL,
    baseline_path text NOT NULL,
    trial_path text NOT NULL CHECK (trial_path <> baseline_path),
    baseline_from date NOT NULL,
    baseline_to date NOT NULL,
    trial_from date NOT NULL,
    trial_to date NOT NULL,
    stage text NOT NULL DEFAULT 'draft' CHECK (stage IN ('draft','surveying','sealed','decided')),
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (baseline_from <= baseline_to AND baseline_to < trial_from AND trial_from <= trial_to)
);
CREATE UNIQUE INDEX IF NOT EXISTS one_live_trial_per_hub ON route_plan(lower(hub),lower(feeder),lower(connection))
    WHERE stage IN ('surveying','sealed');

CREATE TABLE IF NOT EXISTS survey_sample (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sample_ref text UNIQUE NOT NULL,
    plan_id bigint NOT NULL REFERENCES route_plan (id),
    passenger_hash text NOT NULL,
    cohort text NOT NULL CHECK (cohort IN ('baseline','trial')),
    trip_day date NOT NULL,
    time_band text CHECK (time_band IN ('peak','offpeak')),
    rating smallint NOT NULL CHECK (rating BETWEEN 1 AND 5),
    disposition text NOT NULL CHECK (disposition IN ('eligible','queue','excluded')),
    duplicate_of bigint REFERENCES survey_sample (id),
    cleanup_note text,
    collected_by text NOT NULL REFERENCES staff_account (email),
    collected_at timestamptz NOT NULL DEFAULT now(),
    CHECK (disposition <> 'eligible' OR (time_band IS NOT NULL AND duplicate_of IS NULL)),
    CHECK (disposition <> 'excluded' OR cleanup_note IS NOT NULL),
    CHECK (disposition <> 'queue' OR time_band IS NULL OR duplicate_of IS NOT NULL)
);
CREATE UNIQUE INDEX IF NOT EXISTS canonical_passenger_per_plan ON survey_sample (plan_id, passenger_hash)
    WHERE duplicate_of IS NULL;
CREATE INDEX IF NOT EXISTS plan_sample_bucket ON survey_sample (plan_id, disposition, time_band, cohort);

CREATE TABLE IF NOT EXISTS retest_conclusion (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    plan_id bigint NOT NULL UNIQUE REFERENCES route_plan (id),
    status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','ready','signed')),
    snapshot_hash text NOT NULL,
    requested_at timestamptz NOT NULL DEFAULT now(),
    calculated_at timestamptz,
    combined_p double precision CHECK (combined_p BETWEEN 0 AND 1),
    stratified_effect double precision CHECK (stratified_effect BETWEEN -1 AND 1),
    band_results jsonb,
    adopt_allowed boolean,
    decision text CHECK (decision IN ('adopt','retain','extend')),
    decision_note text,
    signed_by text REFERENCES staff_account (email),
    signed_at timestamptz,
    CHECK (status = 'queued' OR (calculated_at IS NOT NULL AND band_results IS NOT NULL AND adopt_allowed IS NOT NULL
        AND combined_p IS NOT NULL AND stratified_effect IS NOT NULL)),
    CHECK (status <> 'signed' OR (decision IS NOT NULL AND decision_note IS NOT NULL AND signed_at IS NOT NULL AND signed_by IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS transfer_audit (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    plan_id bigint NOT NULL REFERENCES route_plan (id),
    actor text NOT NULL,
    event text NOT NULL,
    details jsonb NOT NULL DEFAULT '{}',
    happened_at timestamptz NOT NULL DEFAULT now()
);
