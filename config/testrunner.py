"""Test runner that guarantees the suite never calls a real external API,
no matter what's in the developer's .env (ARCHITECTURE.md §47: "the main
suite must not depend on external APIs").

Without this, a developer with a real TYPESAFE_API_KEY/OPENAI_API_KEY
configured for local development would have `manage.py test` silently make
real, billed calls to Jev/OpenAI — exactly the failure mode this guards
against. Individual tests can still opt into a fake-but-present key via
`self.settings(...)`/`override_settings(...)`, which composes fine on top
of this.
"""

from django.test.runner import DiscoverRunner


class NoExternalCredentialsTestRunner(DiscoverRunner):
    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)

        from django.conf import settings

        settings.TYPESAFE_API_KEY = ""
        settings.OPENAI_API_KEY = ""
