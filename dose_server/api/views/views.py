import uuid
import pytz

from django.db import models as dj_models

from django.http.response import JsonResponse
from django.http import HttpResponse
import rest_framework as rest

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny

from api import models

from api import utility
from api.backend import download_data
from api.backend import handle_services

import datetime
import arrow

from tconnectsync.api import TConnectApi

import logging
logger = logging.getLogger('dose-logger')


@api_view(['POST'])
def update_credentials(request : rest.request.Request):
    request_dict = rest.parsers.JSONParser().parse(request)

    user : models.User = request.user.user 

    dexcom_refresh_token = request_dict.get("dexcom_refresh_token")
    tconnect_email = request_dict.get("tconnect_email")
    tconnect_password = request_dict.get("tconnect_password")

    if dexcom_refresh_token is not None:
        user.dexcom_refresh_token = dexcom_refresh_token

    if tconnect_email is not None:
        user.tconnect_email = tconnect_email

    if tconnect_password is not None:
        user.tconnect_password = tconnect_password

    user.save()

    return JsonResponse(utility.format_response_dict())


# MSS = minutes since start of day
# Comp_MSS = MSS of completed bolus
@api_view(['POST'])
def calculate_insulin(request : rest.request.Request):

        user : models.User = request.user.user 
        request_dict = rest.parsers.JSONParser().parse(request)

        if not user.is_valid_user():
                logger.warning("calculate-insulin | \"Some TConnect and Dexcom credentials missing\"")
                return JsonResponse(utility.format_response_dict(error=(utility.DoseError.RequiredDataMissing), error_message='Some TConnect and Dexcom credentials missing'))

        # Get better adjustment later
        comp_mss_delta = 2

        now = utility.utc_datetime()
        mss : int = int((now.hour * 60) + now.minute)
        comp_mss : int = mss + comp_mss_delta

        target_bg = request_dict.get("target_bg")
        target_bg_duration = request_dict.get("target_duration_minutes")

        if target_bg is not None:
            user.current_target_bg = target_bg

        if target_bg_duration is not None and isinstance(target_bg_duration, int):
            user.target_bg_duration = datetime.timedelta(minutes=target_bg_duration)

        user.save()

        # Start Data Downloads

        # TConnect
        tconnect = TConnectApi(user.tconnect_email, user.tconnect_password)    

        utc_time_start = arrow.get(now - datetime.timedelta(days=1))
        utc_time_end = arrow.get(now)

        

        tandem_events = download_data.download_tconnect_data(tconnect, utc_time_start, utc_time_end)
        dexcom_data = download_data.download_dexcom_data(user, utc_time_start, utc_time_end)

        full_data = handle_services.handle_data(tandem_events, dexcom_data)

        last_range = sorted(list(full_data.keys()), key=lambda range_tup: range_tup[1], reverse=True)[0]

        entry_raw = full_data[last_range]

        return JsonResponse(utility.format_response_dict(entry_raw))
        





        