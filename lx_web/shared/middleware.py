"""
CORS 中间件。
"""

from flask import request, make_response


def _add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response


def _handle_options():
    if request.method == "OPTIONS":
        return make_response("", 200)
