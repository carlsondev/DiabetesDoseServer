import uuid

from django.db import models as dj_models

from django.http.response import JsonResponse
from django.http import HttpResponse
import rest_framework as rest

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny

from api import models

from api import utility

import logging
logger = logging.getLogger('dose-logger')


@api_view(['POST'])
@permission_classes([AllowAny])
def register_user(request : rest.request.Request):

        request_dict = rest.parsers.JSONParser().parse(request)

        required_keys = ["first_name", "last_name", "phone_number"]
        if not set(required_keys).issubset(request_dict):
                logger.warning("register-user | \"Did not supply all data\"")
                return JsonResponse(utility.format_response_dict(error=utility.DoseError.RequiredDataMissing, error_message="Did not supply all data"))

        first_name = request_dict["first_name"]
        last_name = request_dict["last_name"]
        phone_num = utility.strip_phone_number(request_dict["phone_number"])

        try:
                existing_users = models.LoginData.objects.filter(dj_models.Q(phone_number=phone_num))
                if len(existing_users) <= 0:
                        raise models.LoginData.DoesNotExist
                logger.warning("register-user | \"User for phone number already exists\"")
                return JsonResponse(utility.format_response_dict(error=utility.DoseError.InternalRequestError, error_message="User for email or phone number already exists"))
        except models.LoginData.DoesNotExist:
                #A user does not exist for this data, continue
                pass

        user_uuid = uuid.uuid4()

        new_user = models.User(uuid=user_uuid, first_name=first_name, last_name=last_name, last_login=utility.utc_datetime())
        new_user_login = models.LoginData(user=new_user, phone_number=phone_num, password=request_dict.get("password"))

        new_user.save()
        new_user_login.save()

        response = HttpResponse(str(new_user.uuid), content_type="text/plain")
        return response
