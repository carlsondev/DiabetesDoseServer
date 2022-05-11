import uuid
import pytz

from django.db import models as dj_models

from django.http.response import JsonResponse
from django.http import HttpResponse
import rest_framework as rest

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny

from api import models, model_serializers

from api import utility
from api.backend import download_data
from api.backend import handle_services

import datetime
import arrow
import typing

from tconnectsync.secret import TIMEZONE_NAME

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


def fetch_all_data(user : models.User, utc_time_start : arrow.Arrow, utc_time_end : arrow.Arrow) -> typing.Dict[typing.Tuple[arrow.Arrow], typing.Dict[str, typing.Any]]:
        # Start Data Downloads

        # TConnect
        tconnect = TConnectApi(user.tconnect_email, user.tconnect_password)    

        tandem_events = download_data.download_tconnect_data(tconnect, utc_time_start, utc_time_end)
        dexcom_data = download_data.download_dexcom_data(user, utc_time_start, utc_time_end)

        full_data = handle_services.handle_data(tandem_events, dexcom_data)

        return full_data

def save_data_to_database(user : models.User, full_data : typing.Dict[typing.Tuple[arrow.Arrow], typing.Dict[str, typing.Any]]):

    for (range_tup, entry_dict) in full_data.items():

        entry = models.DiabetesEntry()
        entry.owner = user

        entry.start_datetime = range_tup[0].datetime
        entry.end_datetime = range_tup[1].datetime

        entry.blood_glucose = entry_dict.get("bg")
        entry.trend_rate = entry_dict.get("trend_rate")
        entry.trend = entry_dict.get("trend")

        entry.insulin_on_board = entry_dict.get("iob", [])

        entry.dosed_insulin = entry_dict.get("insulin")
        entry.dose_target_bg = entry_dict.get("target_bg")

        comp_time : arrow.Arrow = entry_dict.get("completion_time")
        if comp_time is not None:
            entry.dose_completion_time = comp_time.datetime

        # If this entry already exists, don't add it
        try:
            test_entry = models.DiabetesEntry.objects.get(start_datetime=entry.start_datetime, end_datetime=entry.end_datetime, owner=user)
            continue
        except:
            pass
        print("Saved: ({})".format(range_tup))
        entry.save()

@api_view(['POST'])
def get_all_data(request : rest.request.Request):

    user : models.User = request.user.user 
    request_dict = rest.parsers.JSONParser().parse(request)

    if not user.is_valid_user():
            logger.warning("get-all-data | \"Some TConnect and Dexcom credentials missing\"")
            return JsonResponse(utility.format_response_dict(error=(utility.DoseError.RequiredDataMissing), error_message='Some TConnect and Dexcom credentials missing'))

    now = utility.utc_datetime()

    utc_time_end = arrow.get(now)


    full_data = fetch_all_data(user, arrow.get(user.last_fetched_datetime), utc_time_end)
    print("Fetched data has {} ranges".format(len(full_data.keys())))
    if full_data != {} and full_data is not None:
        
        user.last_fetched_datetime = utc_time_end.datetime
        user.save()

    save_data_to_database(user, full_data)

    all_entries = models.DiabetesEntry.objects.filter(owner=user)

    last_fetched_datetime_str = request_dict.get("last_fetched_datetime")
    if last_fetched_datetime_str is not None:
        last_fetched_datetime = arrow.get(last_fetched_datetime_str).datetime
        all_entries = all_entries.filter(start_datetime__gte=last_fetched_datetime)

    entries_json_list = model_serializers.EntrySerializer(all_entries, many=True).data

    return JsonResponse(utility.format_response_dict({"data" : entries_json_list}))
    

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

        utc_time_end = arrow.get(now)

        full_data = fetch_all_data(user, user.last_fetched_datetime, utc_time_end)
        if full_data != {} and full_data is not None:
            user.last_fetched_datetime = utc_time_end.datetime
            user.save()

        save_data_to_database(user, full_data)


        return JsonResponse(utility.format_response_dict({}))
        





        