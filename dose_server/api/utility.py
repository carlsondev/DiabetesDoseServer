import datetime
from multiprocessing import Event
from posixpath import basename
from time import timezone, time
from django.contrib.auth.base_user import AbstractBaseUser
import pytz
import enum
import typing
from rest_framework import serializers as rest_serializers

from django.core import serializers
from django.db.models import Lookup,Field
from rest_framework_simplejwt.serializers import PasswordField, TokenObtainPairSerializer, api_settings
from rest_framework_simplejwt.views import TokenObtainPairView

import importlib

rule_package, user_eligible_for_login = "rest_framework_simplejwt.authentication.default_user_authentication_rule".rsplit('.', 1)
login_rule = importlib.import_module(rule_package)

from rest_framework import exceptions

from api import models

from django.contrib.auth.backends import BaseBackend
from django.core.exceptions import NON_FIELD_ERRORS, ImproperlyConfigured, PermissionDenied
from django.contrib.auth import get_user_model, authenticate

import smtplib
import ssl

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication

UserModel = get_user_model()

import logging
logger = logging.getLogger('dose-logger')


temp_datas_for_invites : typing.Dict[str, typing.Dict[str, typing.Any]] = {}

class DoseBackend(BaseBackend):

        def authenticate(self, request, username=None, password=None, **kwargs):

                phone_number_opt = kwargs.get('phone_number')

                if phone_number_opt is None and username is None: #You need at least one
                        return
                
                if password is None:
                        return

                #Checks for admin page
                if username is not None and username.isdigit():
                        phone_number_opt = username

                try:
                        if phone_number_opt is not None:
                                get_user_model().USERNAME_FIELD = "phone_number"
                                login_data = models.LoginData.objects.filter(phone_number=phone_number_opt, password=password)[0]
                        else:
                                raise models.LoginData.DoesNotExist

                except models.LoginData.DoesNotExist:
                        raise exceptions.AuthenticationFailed()
                except IndexError:
                        raise exceptions.AuthenticationFailed()
                else:
                        if login_data.check_password(password):
                                return login_data


        def get_user(self, user_id: int) -> typing.Optional[AbstractBaseUser]:
                try:
                        return models.LoginData.objects.get(pk=user_id)
                except models.LoginData.DoesNotExist:
                        return None

serializers.BUILTIN_SERIALIZERS['json'] = 'api.utility'


class NotEqual(Lookup):
    lookup_name = 'ne'

    def as_sql(self, compiler, connection):
        lhs, lhs_params = self.process_lhs(compiler, connection)
        rhs, rhs_params = self.process_rhs(compiler, connection)
        params = lhs_params + rhs_params
        return '%s <> %s' % (lhs, rhs), params

Field.register_lookup(NotEqual)

class LoginTokenObtainPairSerializer(TokenObtainPairSerializer):


        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

            self.fields["phone_number"] = rest_serializers.CharField()
            self.fields["password"] = PasswordField()
            
            self.fields["phone_number"].required = True
            self.fields["password"].required = True

        def validate(self, attrs):

                phone_number_op = attrs.get("phone_number")
                
                given_password = attrs.get('password')
                if given_password is None:
                        #Password is not given for non token login
                        raise exceptions.AuthenticationFailed()

                authenticate_kwargs = {
                        'phone_number': phone_number_op,
                        'password': given_password
                }

                try:
                        authenticate_kwargs['request'] = self.context['request']
                except KeyError:
                        pass

                self.user = authenticate(**authenticate_kwargs)

                if not getattr(login_rule, user_eligible_for_login)(self.user):
                        raise exceptions.AuthenticationFailed(
                                self.error_messages['no_active_account'],
                                'no_active_account',
                        )

                refresh = self.get_token(self.user)
                data = {'refresh' : str(refresh), 'access' : str(refresh.access_token)}
                return data

        @classmethod
        def get_token(cls, login_data):
                token = super().get_token(login_data)

                token['uuid'] = str(login_data.user.uuid)

                return token

class LoginTokenObtainPairView(TokenObtainPairView):
    serializer_class = LoginTokenObtainPairSerializer

        
def strip_phone_number(phone_num_str : typing.Optional[str]) -> typing.Optional[str]:
        if phone_num_str is None:
                return None

        temp_number = phone_num_str

        try: #In order to handle string indices being out of range
                if temp_number[0] == "+":
                        temp_number = temp_number[2:] #Remove first two chars, Only support for one digit contry codes for the moment
                                                      # Look into better libraries for phone number parsing
        except:
                return phone_num_str

        num_filter = filter(str.isdigit, temp_number) #Remove all non numeric chars
        return "".join(num_filter)

#Needed to enable JSON serializer
class Serializer(serializers.json.Serializer):
    def get_dump_object(self, obj):
        return self._current


class DoseError(enum.Enum):
        JSONEncodedError = 1
        NoBodyData = 2
        RequestDataFormatInvalid = 3
        RequiredDataMissing = 4
        InternalRequestError = 5
        DatabaseRequestFailed = 6
        NoOperationNeeded = 7
        UserError = 8

def format_response_dict(inputDict = {}, error : typing.Optional[DoseError] = None, error_message = ""):
        response = inputDict
        response["error"] = None

        if error is not None:
                response["error"] = {"error_code" : error.value, "message" : error_message}
        
        return response

def utc_datetime() -> datetime.datetime:
        now = datetime.datetime.now()
        timezone = pytz.timezone("UTC")
        with_timezone = timezone.localize(now)
        return with_timezone

def convert_string_datetime(date_time_str : str) -> datetime.datetime:
        timezone = pytz.timezone("UTC")
        with_timezone = timezone.localize(datetime.datetime.strptime(date_time_str, '%Y-%m-%d %H:%M:%S'))
        return with_timezone

def convert_from_iso(date_time_str : str) -> datetime.datetime:
        timezone = pytz.timezone("UTC")
        with_timezone = timezone.localize(datetime.datetime.strptime(date_time_str, "%Y-%m-%dT%H:%M:%SZ"))
        return with_timezone
        