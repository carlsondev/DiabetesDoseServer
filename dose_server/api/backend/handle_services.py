

from tconnectsync.api import TConnectApi
from tconnectsync.secret import TIMEZONE_NAME

import matplotlib.pyplot as plt
import numpy as np
import arrow

from . import download_data

def handle_data(downloaded_events):

    full_data = {}

    # Parse CGM data
    cgm_data = downloaded_events[download_data.DataType.CGM]
    for cgm_dict_idx in range(len(cgm_data)):
        cgm_dict = cgm_data[cgm_dict_idx]
        current_reading_time = arrow.get(cgm_dict["time"], tzinfo=TIMEZONE_NAME)
        if cgm_dict_idx < len(cgm_data)-1:
            range_end = arrow.get(cgm_data[cgm_dict_idx+1]["time"], tzinfo=TIMEZONE_NAME)
        else:
            # If last, just advance five minutes
            range_end = current_reading_time.shift(minutes=5)
        full_data[(current_reading_time, range_end)] = {"bg" : int(cgm_dict["bg"])}

    # Parse Bolus Data
    bolus_ranges = list(full_data.keys())
    for bolus_dict in downloaded_events[download_data.DataType.BOLUS]:
        iob = bolus_dict["iob"]
        insulin = float(bolus_dict["insulin"])
        comp_time = bolus_dict["completion_time"]
        target_bg = float(bolus_dict["target_bg"])

        cgm_range = next((cgm_range for cgm_range in bolus_ranges if comp_time.is_between(*cgm_range)), None)
        if cgm_range is None:
            print("No corresponding BG found")
            continue

        bolus_ranges.remove(cgm_range)

        if iob is not None:
            full_data[cgm_range]["iob"] = [float(iob)]
        full_data[cgm_range]["insulin"] = insulin
        full_data[cgm_range]["completion_time"] = comp_time
        full_data[cgm_range]["target_bg"] = target_bg


    # Parse Insulin-on-Board
    iob_ranges = list(full_data.keys())
    for iob_dict in downloaded_events[download_data.DataType.IOB]:
        iob = float(iob_dict["IOB"])
        data_time = arrow.get(iob_dict["EventDateTime"], tzinfo=TIMEZONE_NAME)

        if iob == 0:
            full_data[cgm_range]["iob"] = full_data[cgm_range].get("iob", []) + [iob]
            continue

        cgm_range = next((cgm_range for cgm_range in iob_ranges if data_time.is_between(*cgm_range)), None)
        if cgm_range is None:
            print("No corresponding BG found (Current IOB: {}): {}, {}".format(iob, len(iob_ranges), data_time))
            continue
        
        full_data[cgm_range]["iob"] = full_data[cgm_range].get("iob", []) + [iob]

    #Simplify Insulin on board data
    for cgm_range, data_dict in full_data.items():

        updated_dict = data_dict
        current_iob = updated_dict.get("iob")
        if current_iob is not None and type(current_iob) is not float:
            updated_dict["iob"] = min(updated_dict.get("iob", []))

        full_data[cgm_range] = updated_dict


    return full_data
