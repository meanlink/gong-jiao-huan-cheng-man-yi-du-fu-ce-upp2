CREATE TABLE IF NOT EXISTS route_walk_check (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    plan_id bigint NOT NULL REFERENCES route_plan(id),
    cohort text NOT NULL CHECK (cohort IN ('baseline', 'trial')),
    walk_day date NOT NULL,
    time_band text NOT NULL CHECK (time_band IN ('peak', 'offpeak')),
    outcome text NOT NULL CHECK (outcome IN ('clear', 'detour', 'blocked')),
    walk_minutes integer CHECK (walk_minutes BETWEEN 1 AND 90),
    source_ref text NOT NULL,
    note text NOT NULL,
    recorded_by text NOT NULL REFERENCES staff_account(email),
    recorded_at timestamptz NOT NULL DEFAULT now(),
    cleared_by_walk_id bigint,
    clearance_note text,
    cleared_by text REFERENCES staff_account(email),
    cleared_at timestamptz,
    UNIQUE (plan_id, id),
    UNIQUE (plan_id, cohort, walk_day, time_band, source_ref),
    FOREIGN KEY (plan_id, cleared_by_walk_id) REFERENCES route_walk_check(plan_id, id),
    CHECK ((outcome = 'blocked') = (walk_minutes IS NULL)),
    CHECK (cleared_by_walk_id IS NULL OR (outcome <> 'clear' AND cleared_by_walk_id > id)),
    CHECK ((cleared_by_walk_id IS NULL) = (cleared_by IS NULL) AND
           (cleared_by IS NULL) = (clearance_note IS NULL) AND (cleared_by IS NULL) = (cleared_at IS NULL))
);

CREATE INDEX IF NOT EXISTS unresolved_trial_walk
    ON route_walk_check(plan_id) WHERE cohort = 'trial' AND outcome <> 'clear' AND cleared_by_walk_id IS NULL;

CREATE TABLE IF NOT EXISTS route_handover (
    plan_id bigint PRIMARY KEY REFERENCES retest_conclusion(plan_id),
    effective_on date NOT NULL,
    created_by text NOT NULL REFERENCES staff_account(email),
    created_at timestamptz NOT NULL DEFAULT now(),
    released_by text REFERENCES staff_account(email),
    released_at timestamptz,
    release_note text,
    CHECK ((released_by IS NULL) = (released_at IS NULL) AND (released_by IS NULL) = (release_note IS NULL))
);

CREATE TABLE IF NOT EXISTS handover_task (
    plan_id bigint NOT NULL REFERENCES route_handover(plan_id),
    kind text NOT NULL CHECK (kind IN ('stop_signage', 'dispatch_briefing', 'accessibility_notice')),
    evidence text,
    completed_by text REFERENCES staff_account(email),
    completed_at timestamptz,
    PRIMARY KEY (plan_id, kind),
    CHECK ((completed_by IS NULL) = (completed_at IS NULL) AND (completed_by IS NULL) = (evidence IS NULL))
);
