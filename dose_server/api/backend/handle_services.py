


from tconnectsync.api import TConnectApi
from tconnectsync.secret import TIMEZONE_NAME

import matplotlib.pyplot as plt
import numpy as np
import arrow
import typing
import bisect
import numpy as np

from api import utility

from . import download_data

def minutes(timedelta_val):
    return divmod(timedelta_val.seconds, 60)[0]

def chunks(lst, n):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

def range_containing_datetime(range_list : typing.List[typing.Tuple[arrow.Arrow]], test_datetime : arrow.Arrow, sort : bool = True) -> typing.Optional[typing.Tuple[arrow.Arrow]]:



    # Sorted from oldest to newest
    sorted_list = range_list
    if sort:
        sorted_list = sorted(range_list, key=lambda range_tup: range_tup[0])

    low_idx = 0
    high_idx = len(sorted_list)-1


    while low_idx <= high_idx:

        mid = low_idx + (high_idx - low_idx)//2

        if test_datetime.is_between(*sorted_list[mid], bounds="[]"):
            return (*sorted_list[mid],)

        elif test_datetime > sorted_list[mid][0]:
            low_idx = mid + 1

        else:
            high_idx = mid - 1

    return None

def add_ranges_for_datetimes(datetime_list : typing.List[arrow.Arrow], full_data, should_test_gaps):
    current_cgm_ranges = sorted(list(full_data.keys()), key=lambda range_tup: range_tup[0])

    sorted_list = sorted(datetime_list)
    skipped_datetimes = []

    if len(current_cgm_ranges) == 0:
        return full_data, skipped_datetimes



    for current_reading_time in sorted_list:

        cgm_range = range_containing_datetime(current_cgm_ranges, current_reading_time)

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
            current_cgm_ranges = list(full_data.keys())
            continue

        if current_reading_time > current_cgm_ranges[-1][1]:
            # Is after end of data

            # Range should be 5 minutes in length, after measurment
            # Note: Can create gaps, make sure gap filling code is sound
            range_end = current_reading_time.shift(minutes=5)

            full_data[(current_reading_time, range_end)] = {}

            # Update current cgm ranges
            current_cgm_ranges = list(full_data.keys())
            continue

        if not should_test_gaps:
            skipped_datetimes.append(current_reading_time)
            continue

        current_cgm_ranges = sorted(list(full_data.keys()), key=lambda range_tup: range_tup[0])
        
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
                    # Update current cgm ranges
                    current_cgm_ranges = sorted(list(full_data.keys()), key=lambda range_tup: range_tup[0])
                    continue

                except ValueError:
                    # No interval on either side exists which is less than or equal to 5 minutes 
                    pass

                # Create 5 minute interval manually
                range_end = current_reading_time.shift(minutes=5)

                full_data[(current_reading_time, range_end)] = {}
                # Update current cgm ranges
                current_cgm_ranges = sorted(list(full_data.keys()), key=lambda range_tup: range_tup[0])
                continue

    return full_data,skipped_datetimes

def parse_tandem_cgm_data(tandem_events, full_data):
    current_cgm_ranges = sorted(list(full_data.keys()), key=lambda range_tup: range_tup[0])

    cgm_data = tandem_events[download_data.DataType.CGM]
    for cgm_dict_idx in range(len(cgm_data)):
        cgm_dict = cgm_data[cgm_dict_idx]
        current_reading_time = arrow.get(cgm_dict["time"], tzinfo=TIMEZONE_NAME)

        cgm_range = range_containing_datetime(current_cgm_ranges, current_reading_time)

        if cgm_range is None:
            # If a range does not exist, ignore
            print("Ignoring CGM Range!!!!!!")
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
    print("Starting to Handle Data")
    if len(dexcom_events) > 0:
        print("Dexcom Events Exist, using them to fill")
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
    else:
        print("No dexcom events exist, using tandem data to fill")
        cgm_data = tandem_events[download_data.DataType.CGM]
        for cgm_dict_idx in range(len(cgm_data)):
            cgm_dict = cgm_data[cgm_dict_idx]
            current_reading_time = arrow.get(cgm_dict["time"], tzinfo=TIMEZONE_NAME)
            
            if cgm_dict_idx < len(cgm_data)-1:
                next_datetime = cgm_data[cgm_dict_idx+1]["time"]
                range_end = arrow.get(next_datetime, tzinfo=TIMEZONE_NAME)
            else:
                # If last, just advance five minutes
                range_end = current_reading_time.shift(minutes=5)

            # Add with tandem BG data
            full_data[(current_reading_time, range_end)] = {"bg" : int(cgm_dict["bg"])}


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

    print("Starting to add Ranges: ({}): {}".format(len(full_data),utility.utc_datetime().isoformat(timespec="seconds")))
    # First pass, add ranges to beginning or end
    full_data, skipped_cgm_times = add_ranges_for_datetimes(tandem_cgm_times, full_data, False)
    full_data, skipped_bolus_times = add_ranges_for_datetimes(tandem_bolus_times, full_data, False)
    full_data, skipped_iob_times = add_ranges_for_datetimes(tandem_iob_times, full_data, False)
    print("Finished first pass ranges: {}".format(utility.utc_datetime().isoformat(timespec="seconds")))
    # Second pass, add ranges to gaps
    full_data, _ = add_ranges_for_datetimes(skipped_cgm_times, full_data, True)
    full_data, _ = add_ranges_for_datetimes(skipped_bolus_times, full_data, True)
    full_data, _ = add_ranges_for_datetimes(skipped_iob_times, full_data, True)

    print("Ended adding Ranges: ({}): {}".format(len(full_data), utility.utc_datetime().isoformat(timespec="seconds")))
    # Parse CGM data (First pass)
    full_data = parse_tandem_cgm_data(tandem_events, full_data)
    print("Finished parsing CGM data: {}".format(utility.utc_datetime().isoformat(timespec="seconds")))
    # Parse Bolus Data
    bolus_ranges = list(full_data.keys())
    for bolus_dict in tandem_events[download_data.DataType.BOLUS]:
        iob = bolus_dict["iob"]
        insulin = float(bolus_dict["insulin"])
        comp_time = bolus_dict["completion_time"]
        target_bg = float(bolus_dict["target_bg"])

        cgm_range = range_containing_datetime(bolus_ranges, comp_time)
        if cgm_range is None:
            print("No corresponding BG found")
            continue

        bolus_ranges.remove(cgm_range)

        if iob is not None:
            full_data[cgm_range]["iob"] = [float(iob)]
        full_data[cgm_range]["insulin"] = insulin
        full_data[cgm_range]["completion_time"] = comp_time
        full_data[cgm_range]["target_bg"] = target_bg

    print("Finsihed parsing BOLUS data: {}".format(utility.utc_datetime().isoformat(timespec="seconds")))
    # Parse Insulin-on-Board
    iob_ranges = list(full_data.keys())
    iob_ranges = sorted(iob_ranges, key=lambda range_tup: range_tup[0])
    for iob_dict in tandem_events[download_data.DataType.IOB]:
        iob = float(iob_dict["IOB"])
        data_time = arrow.get(iob_dict["EventDateTime"], tzinfo=TIMEZONE_NAME)

        cgm_range = range_containing_datetime(iob_ranges, data_time, sort=False)
        if cgm_range is None:
            print("No corresponding BG found (Current IOB: {}): {}, {}".format(iob, len(iob_ranges), data_time))
            continue

        if iob == 0:
            full_data[cgm_range]["iob"] = full_data[cgm_range].get("iob", []) + [iob]
            continue

        full_data[cgm_range]["iob"] = full_data[cgm_range].get("iob", []) + [iob]
    print("Finished parsing IOB data: {}".format(utility.utc_datetime().isoformat(timespec="seconds")))
    #Simplify Insulin on board data
    # for cgm_range, data_dict in full_data.items():

    #     updated_dict = data_dict
    #     current_iob = updated_dict.get("iob")
    #     if current_iob is not None and type(current_iob) is not float:
    #         updated_dict["iob"] = min(updated_dict.get("iob", []))

    #     full_data[cgm_range] = updated_dict

    full_data = {key:value for (key,value) in full_data.items() if value != {} }
    return full_data
