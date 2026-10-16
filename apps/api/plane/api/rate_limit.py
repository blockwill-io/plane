# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Python imports
import hashlib

# Django imports
from django.conf import settings

# Third party imports
from rest_framework.throttling import SimpleRateThrottle


class ApiKeyRateThrottle(SimpleRateThrottle):
    scope = "api_key"
    rate = settings.API_KEY_RATE_LIMIT

    def get_cache_key(self, request, view):
        # Retrieve the API key from the request header
        api_key = request.headers.get("X-Api-Key")
        if not api_key:
            # BlockWill fork: OAuth bearer tokens share the API key budget.
            authorization = request.headers.get("Authorization", "")
            if authorization.lower().startswith("bearer "):
                api_key = hashlib.sha256(authorization[7:].strip().encode()).hexdigest()
        if not api_key:
            return None  # Allow the request if there's no API key

        # Use the API key as part of the cache key
        return f"{self.scope}:{api_key}"

    def allow_request(self, request, view):
        allowed = super().allow_request(request, view)

        if allowed:
            now = self.timer()
            # Calculate the remaining limit and reset time
            history = self.cache.get(self.key, [])

            # Remove old histories
            while history and history[-1] <= now - self.duration:
                history.pop()

            # Calculate the requests
            num_requests = len(history)

            # Check available requests
            available = self.num_requests - num_requests

            # Unix timestamp for when the rate limit will reset
            reset_time = int(now + self.duration)

            # Add headers
            request.META["X-RateLimit-Remaining"] = max(0, available)
            request.META["X-RateLimit-Reset"] = reset_time

        return allowed
