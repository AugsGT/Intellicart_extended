from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models


class IntellicartUserManager(UserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        # A superuser created from the command line is an ADMIN in our role system.
        extra_fields.setdefault("role", "ADMIN")
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    """Custom user from day one (changing AUTH_USER_MODEL later is painful).

    API permissions are decided by `role`, not by Django's is_staff flag.
    """

    class Role(models.TextChoices):
        CUSTOMER = "CUSTOMER", "Customer"
        OPERATIONS = "OPERATIONS", "Operations"
        ADMIN = "ADMIN", "Administrator"

    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CUSTOMER)

    objects = IntellicartUserManager()

    def save(self, *args, **kwargs):
        # Emails are compared case-insensitively, so store them lowercase.
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.email
