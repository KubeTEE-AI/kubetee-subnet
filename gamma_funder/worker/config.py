"""Fail-closed production transports shared by measured Gamma candidates.

A Redis Sentinel daemon is NOT the data server: redis-py must discover the
named Redis master separately. The gateway has a same-package copy of this
URL adapter so it need not import the independent worker release.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, unquote, urlsplit


def redis_production_settings(url: str) -> dict:
    """Parse one audited transport URI, with explicit Sentinel discovery."""
    from redis.connection import parse_url

    address = urlsplit(url)
    try:
        if address.scheme not in {
            "redis",
            "rediss",
            "redis+sentinel",
            "rediss+sentinel",
        }:
            raise ValueError("unsupported production Redis URI scheme")
        if address.scheme.endswith("+sentinel"):
            if (
                not address.hostname
                or address.username is None
                or address.password is None
                or address.fragment
                or address.path not in {"", "/"}
            ):
                raise ValueError(
                    "Sentinel URI needs exactly host and percent-encoded credentials"
                )
            parameters = parse_qs(address.query, strict_parsing=True)
            allowed = {
                "service_name",
                "db",
                "sentinel_username",
                "sentinel_password",
            }
            if set(parameters) - allowed or "service_name" not in parameters:
                raise ValueError(
                    "Sentinel URI requires service_name and only supported options"
                )
            if any(
                name not in allowed or len(values) != 1
                for name, values in parameters.items()
            ):
                raise ValueError("unsupported Sentinel URI option")
            service = parameters["service_name"][0]
            if not re.fullmatch(r"[A-Za-z0-9_.-]+", service):
                raise ValueError("invalid Sentinel service name")
            options = {
                "socket_connect_timeout": 5.0,
                "socket_timeout": 5.0,
                "decode_responses": True,
                "db": 0,
                "username": unquote(address.username),
                "password": unquote(address.password),
            }
            if "db" in parameters:
                options["db"] = int(parameters["db"][0])
            if options["db"] < 0 or options["db"] > 15:
                raise ValueError("unsupported Redis database")
            sentinel_credentials = {
                "username": options["username"],
                "password": options["password"],
            }
            if address.scheme.startswith("rediss"):
                options["ssl"] = True
                sentinel_credentials["ssl"] = True
            for name in ("username", "password"):
                option = "sentinel_" + name
                if option in parameters:
                    sentinel_credentials[name] = parameters[option][0]
            if not all(sentinel_credentials.values()):
                raise ValueError("Sentinel credentials must not be empty")

            return {
                "sentinel_nodes": [[address.hostname, address.port or 26379]],
                "service_name": service,
                "sentinel_kwargs": sentinel_credentials,
                "socket_timeout": 5.0,
                "socket_connect_timeout": 5.0,
                **options,
            }
        if (
            not address.hostname
            or address.fragment
            or (address.path and not address.path[1:].isdigit())
        ):
            raise ValueError(
                "direct Redis URI must specify only a numeric DB path"
            )
        return {
            **parse_url(url),
            "decode_responses": True,
            "socket_connect_timeout": 5.0,
        }
    except (TypeError, ValueError) as error:
        raise ValueError(
            "invalid production Redis URI configuration"
        ) from error
