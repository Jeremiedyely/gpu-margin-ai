-- V16__expand_self_transition_guard.sql
-- Expands CHK_history_no_self_transition to allow SESSION_CLOSED
-- alongside SYSTEM_RECOVERY for self-transitions (APPROVED→APPROVED).
-- SESSION_CLOSED is the terminal lifecycle event — auditable in state_history.

ALTER TABLE dbo.state_history
    DROP CONSTRAINT CHK_history_no_self_transition;

ALTER TABLE dbo.state_history
    ADD CONSTRAINT CHK_history_no_self_transition
        CHECK (
            from_state <> to_state
            OR transition_trigger IN ('SYSTEM_RECOVERY', 'SESSION_CLOSED')
        );
