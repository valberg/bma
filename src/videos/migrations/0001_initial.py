# Generated by Django 5.0.6 on 2024-05-22 06:06

import django.db.models.deletion
import taggit.managers
import utils.upload
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('files', '0002_initial'),
        ('taggit', '0006_rename_taggeditem_content_type_object_id_taggit_tagg_content_8fc721_idx'),
        ('utils', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Video',
            fields=[
                ('basefile_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='files.basefile')),
                ('original', models.FileField(help_text='The original uploaded video file.', max_length=255, upload_to=utils.upload.get_upload_path)),
                ('tags', taggit.managers.TaggableManager(help_text='The tags for this video file', through='utils.UUIDTaggedItem', to='taggit.Tag', verbose_name='Tags')),
            ],
            options={
                'abstract': False,
                'base_manager_name': 'objects',
            },
            bases=('files.basefile',),
        ),
    ]
