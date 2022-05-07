
import datetime
import arrow
import logging
import enum
import json
import http.client
import typing
import arrow

from api.models import User

from tconnectsync.parser.tconnect import TConnectEntry
from tconnectsync.secret import TIMEZONE_NAME

from tconnectsync.util import timeago
from tconnectsync.api.common import ApiException
from tconnectsync.features import *
from tconnectsync.sync.basal import (
    process_ciq_basal_events,
    add_csv_basal_events
)
from tconnectsync.sync.bolus import (
    process_bolus_events
)
from tconnectsync.sync.iob import (
    process_iob_events
)
from tconnectsync.sync.cgm import (
    process_cgm_events
)
from tconnectsync.sync.pump_events import (
    process_ciq_activity_events,
    process_basalsuspension_events
)

logger = logging.getLogger(__name__)

dex_client_id = "1bgV6dunaufYB8YwVxtJqVqC5a7ThmYI"
dex_client_secret = "VRY8PtUOI4fjQaMp"

class DataType(enum.Enum):
        BOLUS = 1
        BASEL = 2
        IOB = 3
        CGM = 4
        TREND = 5
        TREND_RATE = 6


def custom_bolus_parse(bolus_data):

    final_return_data = []

    for bolus_dict in bolus_data:
        final_dict = {}

        bg = bolus_dict.get("BG")
        iob = bolus_dict.get("IOB")
        
        insulin = bolus_dict.get("InsulinDelivered")
        req_time = bolus_dict.get("RequestDateTime")
        comp_time = bolus_dict.get("CompletionDateTime")
        target_bg = bolus_dict.get("TargetBG")

        final_dict["bg"] = bg if bg != '' else None
        final_dict["iob"] = iob if iob != '' else None
        final_dict["insulin"] = insulin if insulin != '' else None
        final_dict["request_time"] = arrow.get(req_time, tzinfo=TIMEZONE_NAME) if req_time != '' else None
        final_dict["completion_time"] = arrow.get(comp_time, tzinfo=TIMEZONE_NAME) if comp_time != '' else None
        final_dict["target_bg"] = target_bg if target_bg != '' else None

        final_return_data.append(final_dict)

    return final_return_data

def download_tconnect_data(tconnect, time_start, time_end, features=DEFAULT_FEATURES):
    print("Downloading t:connect ControlIQ data")
    try:
        ciqTherapyTimelineData = tconnect.controliq.therapy_timeline(time_start, time_end)
    except ApiException as e:
        # The ControlIQ API returns a 404 if the user did not have a ControlIQ enabled
        # device in the time range which is queried. Since it launched in early 2020,
        # ignore 404's before February.
        if e.status_code == 404 and time_start.date() < datetime.date(2020, 2, 1):
            logger.warning("Ignoring HTTP 404 for ControlIQ API request before Feb 2020")
            ciqTherapyTimelineData = None
        else:
            raise e

    print("Downloading t:connect CSV data")
    csvdata = tconnect.ws2.therapy_timeline_csv(time_start, time_end)

    readingData = csvdata["readingData"]
    iobData = csvdata["iobData"]
    csvBasalData = csvdata["basalData"]
    bolusData = csvdata["bolusData"]

    if readingData and len(readingData) > 0:
        lastReading = readingData[-1]['EventDateTime'] if 'EventDateTime' in readingData[-1] else 0
        lastReading = TConnectEntry._datetime_parse(lastReading)

        print("Last CGM reading from t:connect: %s (%s)" % (lastReading, timeago(lastReading)))
    else:
        logger.warning("No last CGM reading is able to be determined")

    added = 0

    cgmData = process_cgm_events(readingData)

    if BASAL in features:
        basalEvents = process_ciq_basal_events(ciqTherapyTimelineData)
        if csvBasalData:
            logger.debug("CSV basal data found: processing it")
            add_csv_basal_events(basalEvents, csvBasalData)
        else:
            logger.debug("No CSV basal data found")

    
    if PUMP_EVENTS in features:
        pumpEvents = process_ciq_activity_events(ciqTherapyTimelineData)
        logger.debug("CIQ activity events: %s" % pumpEvents)

        ws2BasalSuspension = tconnect.ws2.basalsuspension(time_start, time_end)

        bsPumpEvents = process_basalsuspension_events(ws2BasalSuspension)
        logger.debug("basalsuspension events: %s" % bsPumpEvents)

        pumpEvents += bsPumpEvents


    if BOLUS in features:
        bolusEvents = process_bolus_events(bolusData)

    if len(iobData) > 0:
        iobEvents = process_iob_events(iobData)


    return {DataType.CGM : cgmData, DataType.BOLUS : custom_bolus_parse(bolusData), DataType.BASEL : basalEvents, DataType.IOB : iobData}


# Currently assuming this works 100% of the time
def refresh_dex_access_code(user : User) -> typing.Optional[str]:

    conn = http.client.HTTPSConnection("api.dexcom.com")

    payload = "client_secret={}&client_id={}&refresh_token={}&grant_type=refresh_token&redirect_uri={}".format(dex_client_secret, dex_client_id, user.dexcom_refresh_token, "diabetes-dose://oauth-callback/dexcom")

    headers = {
        'content-type': "application/x-www-form-urlencoded",
        'cache-control': "no-cache"
    }

    conn.request("POST", "/v2/oauth2/token", payload, headers)

    res = conn.getresponse()

    if res.status == 400:
        # Refresh code is no longer valid
        return None

    data = res.read()

    response_str = data.decode("utf-8")
    response_dict = json.loads(response_str)

    access_token = response_dict.get("access_token", user.dexcom_access_token)
    user.dexcom_access_token = access_token
    user.save()

    return access_token

def download_dexcom_data(user : User, time_start : arrow.Arrow, time_end: arrow.Arrow) -> typing.Optional[typing.Dict[arrow.Arrow, typing.Dict[DataType, typing.Any]]]:

    access_token = user.dexcom_access_token
    if user.dexcom_access_token is None:
        access_token = refresh_dex_access_code(user)

    conn = http.client.HTTPSConnection("api.dexcom.com")

    headers = {
        'authorization': "Bearer {}".format(access_token)
    }

    start_date_str = time_start.isoformat(timespec='seconds').replace('+00:00', '')
    end_date_str = time_end.isoformat(timespec='seconds').replace('+00:00', '')

    print(time_start.isoformat())

    url_path = "/v2/users/self/egvs?startDate={}&endDate={}".format(start_date_str, end_date_str)

    conn.request("GET", url_path, headers=headers)
    res = conn.getresponse()

    if res.status == 401:
        # 401, access token expired
        access_token = refresh_dex_access_code(user)
        headers = {
            'authorization': "Bearer {}".format(access_token)
        }
        conn = http.client.HTTPSConnection("api.dexcom.com")
        conn.request("GET", url_path, headers=headers)
        res = conn.getresponse()

        if res.status == 401:
            # Failed a second time
            return None

    data = res.read()

    response_str = data.decode("utf-8")
    response_dict = json.loads(response_str)

    evgs = response_dict.get("egvs", [])

    return_dict : typing.Dict[arrow.Arrow, typing.Dict[DataType, typing.Any]] = {}

    for data_dict in evgs:
        system_time = data_dict.get("systemTime")
        if system_time is None:
            continue
        
        time = arrow.get(system_time)

        bg = data_dict.get("value")
        trend_rate = data_dict.get("trendRate")
        trend = data_dict.get("trend")

        type_dict = {DataType.CGM : bg, DataType.TREND : trend, DataType.TREND_RATE : trend_rate}
        return_dict[time] = type_dict

    return return_dict
