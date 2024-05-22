# Generated by Django 5.0.6 on 2024-05-22 06:06

import django.db.models.deletion
import utils.upload
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('files', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Audio',
            fields=[
                ('basefile_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='files.basefile')),
                ('original', models.FileField(help_text='The original uploaded file.', max_length=255, upload_to=utils.upload.get_upload_path)),
            ],
            options={
                'abstract': False,
                'base_manager_name': 'objects',
            },
            bases=('files.basefile',),
        ),
    ]
