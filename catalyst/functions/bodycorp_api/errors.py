"""
One error type for every refusal. `main` turns it into {"ok": false, "error": ...}
with its HTTP status, so a module only says what went wrong and how badly.
"""


class ApiError(Exception):
    def __init__(self, message, status=400):
        Exception.__init__(self, message)
        self.message = message
        self.status = status


def bad(message):
    return ApiError(message, 400)


def not_found(message="That wasn't found."):
    return ApiError(message, 404)


def forbidden(message="You can't do that."):
    return ApiError(message, 403)
