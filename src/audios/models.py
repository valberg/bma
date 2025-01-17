"""The Audio model."""
from django.db import models
from files.models import BaseFile
from taggit.managers import TaggableManager
from utils.models import UUIDTaggedItem
from utils.upload import get_upload_path


class Audio(BaseFile):  # type: ignore[django-manager-missing]
    """The Audio model."""

    original = models.FileField(
        upload_to=get_upload_path,
        max_length=255,
        help_text="The original uploaded file.",
    )

    tags = TaggableManager(
        through=UUIDTaggedItem,
        help_text="The tags for this audio file",
    )
