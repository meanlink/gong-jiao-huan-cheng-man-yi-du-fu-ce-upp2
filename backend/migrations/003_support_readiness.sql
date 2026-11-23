CREATE TABLE IF NOT EXISTS support_desk (
    plan_id bigint NOT NULL REFERENCES route_handover(plan_id),
    desk text NOT NULL CHECK (desk IN ('access', 'station', 'dispatch')),
    location text NOT NULL CHECK (char_length(location) BETWEEN 2 AND 100),
    capacity smallint NOT NULL CHECK (capacity BETWEEN 1 AND 30),
    available boolean NOT NULL,
    updated_by text NOT NULL REFERENCES staff_account(email),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (plan_id, desk)
);

CREATE TABLE IF NOT EXISTS support_notice (
    plan_id bigint NOT NULL REFERENCES route_handover(plan_id),
    edition integer NOT NULL CHECK (edition > 0),
    meeting_point text NOT NULL CHECK (char_length(meeting_point) BETWEEN 2 AND 100),
    directions text NOT NULL CHECK (char_length(directions) BETWEEN 8 AND 280),
    published_by text NOT NULL REFERENCES staff_account(email),
    published_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (plan_id, edition)
);
