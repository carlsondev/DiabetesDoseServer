# Generated by Django 4.0.4 on 2022-05-06 04:24

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='dexcom_refresh_token',
            field=models.TextField(null=True),
        ),
        migrations.AddField(
            model_name='user',
            name='tconnect_email',
            field=models.TextField(null=True),
        ),
        migrations.AddField(
            model_name='user',
            name='tconnect_password',
            field=models.TextField(null=True),
        ),
    ]
