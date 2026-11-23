CREATE TABLE IF NOT EXISTS support_case (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    plan_id bigint NOT NULL REFERENCES route_handover(plan_id),
    notice_edition integer NOT NULL,
    category text NOT NULL CHECK (category IN ('step_free', 'wayfinding', 'missed_connection')),
    landmark text NOT NULL CHECK (char_length(landmark) BETWEEN 2 AND 100),
    description text NOT NULL CHECK (char_length(description) BETWEEN 4 AND 240),
    desk text,
    route_reason text NOT NULL CHECK (route_reason IN ('primary', 'fallback', 'waiting')),
    opened_by text NOT NULL REFERENCES staff_account(email),
    opened_at timestamptz NOT NULL DEFAULT now(),
    resolved_by text REFERENCES staff_account(email),
    resolved_at timestamptz,
    resolution text CHECK (char_length(resolution) BETWEEN 8 AND 240),
    UNIQUE (plan_id, id),
    FOREIGN KEY (plan_id, notice_edition) REFERENCES support_notice(plan_id, edition),
    FOREIGN KEY (plan_id, desk) REFERENCES support_desk(plan_id, desk),
    CHECK ((desk IS NULL) = (route_reason = 'waiting')),
    CHECK ((resolved_at IS NULL) = (resolved_by IS NULL) AND (resolved_at IS NULL) = (resolution IS NULL)),
    CHECK (resolved_at IS NULL OR desk IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS support_open_load ON support_case (plan_id, desk) WHERE resolved_at IS NULL;

CREATE TABLE IF NOT EXISTS support_case_event (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    plan_id bigint NOT NULL,
    case_id bigint NOT NULL,
    action text NOT NULL CHECK (action IN ('opened', 'redispatched', 'resolved')),
    desk text,
    route_reason text NOT NULL CHECK (route_reason IN ('primary', 'fallback', 'waiting')),
    actor text NOT NULL REFERENCES staff_account(email),
    happened_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (plan_id, case_id) REFERENCES support_case(plan_id, id),
    FOREIGN KEY (plan_id, desk) REFERENCES support_desk(plan_id, desk),
    CHECK ((desk IS NULL) = (route_reason = 'waiting'))
);

CREATE INDEX IF NOT EXISTS support_case_history ON support_case_event (plan_id, case_id, id);
