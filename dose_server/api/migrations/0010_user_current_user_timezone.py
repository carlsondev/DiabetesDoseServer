# Generated by Django 4.0.4 on 2022-05-30 19:40

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0009_alter_diabetesentry_blood_glucose'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='current_user_timezone',
            field=models.TextField(default='America/Los_Angeles'),
            preserve_default=False,
        ),
    ]