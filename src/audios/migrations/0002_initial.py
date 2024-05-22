# Generated by Django 5.0.6 on 2024-05-22 06:06

import taggit.managers
from django.db import migrations


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('audios', '0001_initial'),
        ('taggit', '0006_rename_taggeditem_content_type_object_id_taggit_tagg_content_8fc721_idx'),
        ('utils', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='audio',
            name='tags',
            field=taggit.managers.TaggableManager(help_text='The tags for this audio file', through='utils.UUIDTaggedItem', to='taggit.Tag', verbose_name='Tags'),
        ),
    ]
