# -*- coding: utf-8 -*-
# Generated by Django 1.11.28 on 2020-04-14 20:39


from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('uchileedxlogin', '0003_auto_20200120_2024'),
    ]

    operations = [
        migrations.AlterField(
            model_name='edxloginuser',
            name='user',
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                to=settings.AUTH_USER_MODEL),
        ),
    ]
