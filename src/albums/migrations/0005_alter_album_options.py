# Generated by Django 5.0.3 on 2024-04-14 06:06

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('albums', '0004_initial'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='album',
            options={'ordering': ('created',)},
        ),
    ]
