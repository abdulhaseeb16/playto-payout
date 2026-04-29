class InvalidTransitionError(Exception):
    pass


LEGAL_TRANSITIONS = {
    'pending': ['processing'],
    'processing': ['completed', 'failed'],
    'completed': [],
    'failed': [],
}


def validate_transition(current_status, new_status):
    allowed = LEGAL_TRANSITIONS.get(current_status, [])
    if new_status not in allowed:
        raise InvalidTransitionError(
            f'Cannot transition payout from {current_status} to {new_status}.'
        )
