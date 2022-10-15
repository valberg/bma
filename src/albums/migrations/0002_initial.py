# Generated by Django 4.1.1 on 2022-10-09 18:45

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("albums", "0001_initial"),
        ("files", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="albummember",
            name="basefile",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, to="files.basefile"
            ),
        ),
        migrations.AddField(
            model_name="album",
            name="files",
            field=models.ManyToManyField(
                related_name="albums", through="albums.AlbumMember", to="files.basefile"
            ),
        ),
    ]