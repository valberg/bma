# Generated by Django 5.0.3 on 2024-04-14 13:03

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0002_user_is_bma_creator_user_is_bma_curator_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='user',
            name='is_bma_creator',
        ),
        migrations.RemoveField(
            model_name='user',
            name='is_bma_curator',
        ),
        migrations.RemoveField(
            model_name='user',
            name='is_bma_moderator',
        ),
    ]