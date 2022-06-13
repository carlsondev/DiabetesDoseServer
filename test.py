from api import models
import arrow
import datetime
from api import utility

user = models.User.objects.all()[0]

now = utility.utc_datetime() - datetime.timedelta(hours=10)

user.last_fetched_datetime = arrow.get(now - datetime.timedelta(days=45)).datetime

user.save()

models.DiabetesEntry.objects.all().delete()