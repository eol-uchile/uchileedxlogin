# -*- coding: utf-8 -*-
# Generated by Django 1.11.21 on 2020-01-20 20:24


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('uchileedxlogin', '0002_edxloginusercourseregistration'),
    ]

    operations = [
        migrations.AlterField(
            model_name='edxloginusercourseregistration',
            name='run',
            field=models.CharField(db_index=True, max_length=18),
        ),
    ]
