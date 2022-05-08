


from tconnectsync.api import TConnectApi
from tconnectsync.secret import TIMEZONE_NAME

import matplotlib.pyplot as plt
import numpy as np
import arrow
import typing

from . import download_data

def minutes(timedelta_val):
    return divmod(timedelta_val.seconds, 60)[0]


def add_ranges_for_datetimes(datetime_list : typing.List[arrow.Arrow], full_data, should_test_gaps):
    current_cgm_ranges = sorted(list(full_data.keys()), key=lambda range_tup: range_tup[0])

    sorted_list = sorted(datetime_list)

    for current_reading_time in sorted_list:

        cgm_range = next((cgm_range for cgm_range in current_cgm_ranges if current_reading_time.is_between(*cgm_range, bounds="[]")), None)

        if cgm_range is not None:
            # If a range already exists, don't add range
            current_cgm_ranges.remove(cgm_range)
            continue

        # Range does not exist, add

        if current_reading_time < current_cgm_ranges[0][0]:
            # Is before start of data
            diff = current_cgm_ranges[0][0] - current_reading_time
            if minutes(diff) > 5:
                # Greater than a 5 minute increment, just create a five minute increment
                # Note: Can create gaps, make sure gap filling code is sound
                range_end = current_reading_time.shift(minutes=5)
            else:
                range_end = current_cgm_ranges[0][0]

            full_data[(current_reading_time, range_end)] = {}
            
            # Update current cgm ranges
            current_cgm_ranges = sorted(list(full_data.keys()), key=lambda range_tup: range_tup[0])
            continue

        if current_reading_time > current_cgm_ranges[-1][1]:
            # Is after end of data

            # Range should be 5 minutes in length, after measurment
            # Note: Can create gaps, make sure gap filling code is sound
            range_end = current_reading_time.shift(minutes=5)

            full_data[(current_reading_time, range_end)] = {}

            # Update current cgm ranges
            current_cgm_ranges = sorted(list(full_data.keys()), key=lambda range_tup: range_tup[0])
            continue

        if not should_test_gaps:
            continue
        
        print("Testing for gaps")
        for range_idx in range(len(current_cgm_ranges)-1):
            current_range = current_cgm_ranges[range_idx]
            next_range = current_cgm_ranges[range_idx+1]
            if current_reading_time.is_between(current_range[1], next_range[0]):
                # There is a gap between the end of the current cgm data and start of the next, create

                diff = next_range[0] - current_range[1]
                if minutes(diff) <= 5:
                    range_start = current_range[1]
                    range_end = next_range[0]

                    full_data[(range_start, range_end)] = {}
                    # Update current cgm ranges
                    print("Creating gap")
                    current_cgm_ranges = sorted(list(full_data.keys()), key=lambda range_tup: range_tup[0])
                    continue
                
                #Create subrange
                start_diff = current_reading_time - current_range[1]
                end_diff = next_range[0] - current_reading_time

                diff_list = [5 - minutes(start_diff), 5 - minutes(end_diff)]
                diff_list = [i for i in diff_list if i >= 0]
                
                try:
                    min_value = min(diff_list)
                    if min_value == minutes(start_diff):
                        # First interval is valid
                        range_start = current_range[1]
                        range_end = current_reading_time
                    else:
                        # Second interval is valid
                        range_start = current_reading_time
                        range_end = next_range[0]

                    full_data[(range_start, range_end)] = {}
                    print("Creating gap from difference in ranges")
                    # Update current cgm ranges
                    current_cgm_ranges = sorted(list(full_data.keys()), key=lambda range_tup: range_tup[0])
                    continue

                except ValueError:
                    # No interval on either side exists which is less than or equal to 5 minutes 
                    pass

                # Create 5 minute interval manually
                range_end = current_reading_time.shift(minutes=5)
                print("Creating manual gap")

                full_data[(current_reading_time, range_end)] = {}
                # Update current cgm ranges
                current_cgm_ranges = sorted(list(full_data.keys()), key=lambda range_tup: range_tup[0])
                continue

    return full_data

def parse_tandem_cgm_data(tandem_events, full_data):
    current_cgm_ranges = sorted(list(full_data.keys()), key=lambda range_tup: range_tup[0])

    cgm_data = tandem_events[download_data.DataType.CGM]
    for cgm_dict_idx in range(len(cgm_data)):
        cgm_dict = cgm_data[cgm_dict_idx]
        current_reading_time = arrow.get(cgm_dict["time"], tzinfo=TIMEZONE_NAME)

        cgm_range = next((cgm_range for cgm_range in current_cgm_ranges if current_reading_time.is_between(*cgm_range, bounds="[]")), None)

        if cgm_range is None:
            # If a range does not exist, ignore
            print("Ignoring CGM Range!!!!!!")
            current_cgm_ranges.remove(cgm_range)
            continue
        
        if full_data[cgm_range].get("bg") is not None:
            # Already filled with Dexcom data, ignore
            current_cgm_ranges.remove(cgm_range)
            continue

        # Add with tandem BG data
        full_data[cgm_range]["bg"] = int(cgm_dict["bg"])

    return full_data


def handle_data(tandem_events, dexcom_events):

    full_data = {}

    dex_keys = sorted(list(dexcom_events.keys()))
    for dex_key_idx in range(len(dex_keys)):
        event_datetime = dex_keys[dex_key_idx]

        data_dict = dexcom_events[event_datetime]

        if dex_key_idx < len(dex_keys)-1:
            next_datetime = dex_keys[dex_key_idx+1]
            range_end = arrow.get(next_datetime, tzinfo=TIMEZONE_NAME)
        else:
            # If last, just advance five minutes
            range_end = event_datetime.shift(minutes=5)


        full_data[(event_datetime, range_end)] = {
            "bg" : data_dict[download_data.DataType.CGM],
            "trend" : data_dict[download_data.DataType.TREND],
            "trend_rate" : data_dict[download_data.DataType.TREND_RATE]
        }

    # Add all ranges to data
    cgm_data = tandem_events[download_data.DataType.CGM]
    tandem_cgm_times = []
    for cgm_dict in cgm_data:
        current_reading_time = arrow.get(cgm_dict["time"], tzinfo=TIMEZONE_NAME)
        tandem_cgm_times.append(current_reading_time)
    
    tandem_bolus_times = []
    for bolus_dict in tandem_events[download_data.DataType.BOLUS]:
        comp_time = bolus_dict["completion_time"]
        tandem_bolus_times.append(comp_time)

    tandem_iob_times = []
    for iob_dict in tandem_events[download_data.DataType.IOB]:
        data_time = arrow.get(iob_dict["EventDateTime"], tzinfo=TIMEZONE_NAME)
        tandem_iob_times.append(data_time)

    # First pass, add ranges to beginning or end
    full_data = add_ranges_for_datetimes(tandem_cgm_times, full_data, False)
    full_data = add_ranges_for_datetimes(tandem_bolus_times, full_data, False)
    full_data = add_ranges_for_datetimes(tandem_iob_times, full_data, False)

    # Second pass, add ranges to gaps
    full_data = add_ranges_for_datetimes(tandem_cgm_times, full_data, True)
    full_data = add_ranges_for_datetimes(tandem_bolus_times, full_data, True)
    full_data = add_ranges_for_datetimes(tandem_iob_times, full_data, True)

    # Parse CGM data (First pass)
    full_data = parse_tandem_cgm_data(tandem_events, full_data)

    # Parse Bolus Data
    bolus_ranges = list(full_data.keys())
    for bolus_dict in tandem_events[download_data.DataType.BOLUS]:
        iob = bolus_dict["iob"]
        insulin = float(bolus_dict["insulin"])
        comp_time = bolus_dict["completion_time"]
        target_bg = float(bolus_dict["target_bg"])

        cgm_range = next((cgm_range for cgm_range in bolus_ranges if comp_time.is_between(*cgm_range, bounds="[]")), None)
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
    for iob_dict in tandem_events[download_data.DataType.IOB]:
        iob = float(iob_dict["IOB"])
        data_time = arrow.get(iob_dict["EventDateTime"], tzinfo=TIMEZONE_NAME)

        cgm_range = next((cgm_range for cgm_range in iob_ranges if data_time.is_between(*cgm_range, bounds="[]")), None)
        if cgm_range is None:
            print("No corresponding BG found (Current IOB: {}): {}, {}".format(iob, len(iob_ranges), data_time))
            continue

        if iob == 0:
            full_data[cgm_range]["iob"] = full_data[cgm_range].get("iob", []) + [iob]
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
