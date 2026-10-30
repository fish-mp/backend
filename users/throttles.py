from rest_framework.throttling import AnonRateThrottle


class AuthRateThrottle(AnonRateThrottle):
    scope = 'auth'


class EmailRateThrottle(AnonRateThrottle):
    scope = 'email'
