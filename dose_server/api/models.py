from django.db import models
from django.contrib.postgres.fields import ArrayField
import uuid
from django.contrib.auth.models import BaseUserManager
import datetime
import pytz
import typing
import datetime

def utc_datetime() -> datetime.datetime:
        now = datetime.datetime.now()
        timezone = pytz.timezone("UTC")
        with_timezone = timezone.localize(now)
        return with_timezone

# Create your models here.

class LoginManager(BaseUserManager):
    '''
    creating a manager for a custom user model
    https://docs.djangoproject.com/en/3.0/topics/auth/customizing/#writing-a-manager-for-a-custom-user-model
    https://docs.djangoproject.com/en/3.0/topics/auth/customizing/#a-full-example
    '''
    def create_user_login(self, first_name, last_name, phone_number, password):
        """
        Create and return a `LoginData` with an email, username and password.
        """
        if not first_name or not last_name or not phone_number or not password:
            raise ValueError('Missing info')

        new_user_uuid = uuid.uuid4()

        new_user = User(uuid=new_user_uuid)
        new_user = User(uuid=new_user_uuid, first_name=first_name, last_name=last_name, last_login=utc_datetime())

        new_user_login = self.model(user=new_user, phone_number=phone_number, password=password)

        new_user.save(using=self._db)
        new_user_login.save(using=self._db)
        return new_user_login

    def create_superuser(self, full_name, phone_number, password):
        """
        Create and return a `LoginData` with superuser (admin) permissions.
        """

        names = full_name.split(" ")
        if len(names) < 2:
                return
        first_name = names[0]
        last_name = names[1]

        login_data = self.create_user_login(first_name, last_name, phone_number, password)
        login_data.is_superuser = True
        login_data.is_staff = True
        login_data.save(using=self._db)

        return login_data

class LoginData(models.Model):

        user = models.ForeignKey(
                'User',
                on_delete=models.CASCADE,
                related_name="login_data"
        )
        phone_number =  models.TextField(max_length=15, unique=True)
        password = models.TextField(null=True, blank=True)

        USERNAME_FIELD = "phone_number"
        REQUIRED_FIELDS = []
        is_anonymous = False
        is_authenticated = True
        is_active = models.BooleanField(default=True)
        is_staff = models.BooleanField(default=False)
        is_superuser = models.BooleanField(default=False)

        objects = LoginManager()

        def __str__(self):
                return "Login Data ({})".format(self.user.uuid)

        def check_password(self, password):
                return password == self.password

        def has_perm(self, perm, obj=None):
                return self.is_superuser

        def has_module_perms(self, app_label):
                return self.is_superuser

        def has_usable_password(self):
                return True
        class Meta:
                db_table = 'user_login_data'


class DiabetesEntry(models.Model):

    owner = models.ForeignKey(
        'User',
        on_delete=models.CASCADE,
        related_name='diabetes_entry'
    )

    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField()

    # Dexcom
    blood_glucose = models.FloatField(default=0, null=True)
    trend_rate = models.FloatField(default=0, null=True)
    trend = models.TextField(default="none",null=True)

    insulin_on_board = ArrayField(base_field=models.FloatField(default=0), default=list)

    # Bolus
    dosed_insulin = models.FloatField(default=0, null=True)
    dose_completion_time = models.DateTimeField(null=True)
    dose_target_bg = models.FloatField(default=0, null=True)
    is_manual_bolus = models.BooleanField(default=True, null=True)

    # Basel
    basel_time = models.DateTimeField(null=True)
    basel_delivery_type = models.TextField(null=True)
    basel_duration = models.FloatField(default=0, null=True)
    basel_rate = models.FloatField(default=0, null=True)


# Create your models here.
class User(models.Model):

        uuid = models.UUIDField(primary_key=True)
        first_name = models.TextField()
        last_name = models.TextField()

        # Saved data
        current_target_bg = models.FloatField(default=140)
        target_bg_duration = models.DurationField(default=datetime.timedelta(minutes=15))
        
        last_login = models.DateTimeField()

        # The last time the data was fetched
        last_fetched_datetime = models.DateTimeField(auto_now_add=True)

        current_user_timezone = models.TextField()

        # Api Data
        dexcom_refresh_token = models.TextField(null=True)
        dexcom_access_token = models.TextField(null=True)
        tconnect_email = models.TextField(null=True)
        tconnect_password = models.TextField(null=True)


        def __str__(self):
                return "User ({})".format(self.uuid)

        def save(self, *args, **kwargs):
                super(User, self).save(*args, **kwargs)  

        def delete(self, using: typing.Any = None, keep_parents: bool = False) -> typing.Tuple[int, typing.Dict[str, int]]:

                return super().delete(using=using, keep_parents=keep_parents)     

        def is_valid_user(self) -> bool:
            if self.dexcom_refresh_token is None:
                return False

            if self.tconnect_email is None:
                return False

            if self.tconnect_password is None:
                return False

            return True

        class Meta:
                db_table = 'users'

