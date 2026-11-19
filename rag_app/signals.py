"""Keep files on disk in sync with Document rows.

Django never deletes uploaded files by itself, so without this every deleted or
replaced document would leave an orphan file in MEDIA_ROOT.
Signals (rather than overriding `delete()`) also cover bulk deletes from the admin.
"""

from django.db import transaction
from django.db.models.signals import post_delete, pre_save
from django.dispatch import receiver

from .models import Document


def _delete_file_after_commit(field_file) -> None:
    storage, name = field_file.storage, field_file.name
    if name:
        # Only touch the disk once the DB change is definitely committed.
        transaction.on_commit(lambda: storage.delete(name))


@receiver(post_delete, sender=Document)
def delete_file_with_document(sender, instance: Document, **kwargs) -> None:
    _delete_file_after_commit(instance.file)


@receiver(pre_save, sender=Document)
def delete_replaced_file(sender, instance: Document, **kwargs) -> None:
    if not instance.pk:
        return
    old = Document.objects.filter(pk=instance.pk).only("file").first()
    if old and old.file and old.file.name != instance.file.name:
        _delete_file_after_commit(old.file)
