import uuid

from django.db import models


class Customer(models.Model):
    """Lightweight customer identity.

    The MVP does not require login: a Customer can be created just to anchor
    an anonymous conversation/session, and enriched later.
    """

    external_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    name = models.CharField(max_length=200, blank=True)
    email = models.EmailField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name or str(self.external_id)
