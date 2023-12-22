import math

from lxml import etree
from datetime import datetime, timedelta, time, timezone
import json
import requests_cache
import pytz
import re
import unicodedata
from pathlib import Path

bt_dt_format = '%Y-%m-%dT%H:%M:%SZ'
tz = pytz.timezone('Europe/London')


# From https://stackoverflow.com/questions/4324790/removing-control-characters-from-a-string-in-python
def remove_control_characters(s):
    return "".join(ch for ch in s if unicodedata.category(ch)[0]!="C")

# From spatialtime/iso8601_duration.py
def parse_duration(iso_duration):
    """Parses an ISO 8601 duration string into a datetime.timedelta instance.
    Args:
        iso_duration: an ISO 8601 duration string.
    Returns:
        a datetime.timedelta instance
    """
    m = re.match(r'^P(?:(\d+)Y)?(?:(\d+)M)?(?:(\d+)D)?T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:.\d+)?)S)?$',
                 iso_duration)
    if m is None:
        raise ValueError("invalid ISO 8601 duration string")

    days = 0
    hours = 0
    minutes = 0
    seconds = 0.0

    # Years and months are not being utilized here, as there is not enough
    # information provided to determine which year and which month.
    # Python's time_delta class stores durations as days, seconds and
    # microseconds internally, and therefore we'd have to
    # convert parsed years and months to specific number of days.

    if m[3]:
        days = int(m[3])
    if m[4]:
        hours = int(m[4])
    if m[5]:
        minutes = int(m[5])
    if m[6]:
        seconds = float(m[6])

    return timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)

def get_days(src: str, numdays:int = 3) -> list:
    """
Generate epoch times for now, midnight tomorrow, and midnight the next day
    :return: List of times, either in epoch (for Sky) or str (for BT)
    """

    if src == "sky":
        return list(int(datetime.timestamp(datetime.combine(datetime.now(), time(0, 0)) + timedelta(x))) for x in range(numdays))

    elif src == "bt":
        return list((datetime.combine(datetime.now()+time(0,0)) + timedelta(x)) for x in range(numdays))

    elif src == "freeview":
        return list((math.trunc((datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(x)).timestamp())) for x in range(numdays))
    else:
        return list((datetime.combine(datetime.now(), time(0, 0)) + timedelta(x)) for x in range(numdays))


def get_channels_config() -> list:
    """
Load XML file of channel information
    :return: XML elements as a set, then all sets as a list
    """
    with Path(__file__).parent.joinpath('channels.json').open(encoding='utf-8') as channel_file:
        data = json.load(channel_file)['channels']

    return data


def build_xmltv(channels: list, programmes: list) -> bytes:
    """
Make the channels and programmes into something readable by XMLTV
    :param channels: The list of channels to be generated
    :param programmes: The list of programmes to be generated
    :return: A sequence of bytes for XML
    """
    # Timezones since UK has daylight savings
    dt_format = '%Y%m%d%H%M%S %z'

    data = etree.Element("tv")
    data.set("generator-info-name", "freeview-epg")
    data.set("generator-info-url", "https://github.com/dp247/Freeview-EPG")
    for ch in channels:
        channel = etree.SubElement(data, "channel")
        channel.set("id", ch.get("xmltv_id"))
        name = etree.SubElement(channel, "display-name")
        name.set("lang", ch.get("lang"))
        name.text = ch.get("name")
        if ch.get("icon_url") is not None:
            icon_src = etree.SubElement(channel, "icon")
            icon_src.set("src", ch.get("icon_url"))
            icon_src.text = ''

    for pr in programmes:
        programme = etree.SubElement(data, 'programme')
        start_time = datetime.fromtimestamp(pr.get('start'), tz).strftime(dt_format)
        end_time = datetime.fromtimestamp(pr.get('stop'), tz).strftime(dt_format)

        programme.set("channel", pr.get('channel'))
        programme.set("start", start_time)
        programme.set("stop", end_time)

        title = etree.SubElement(programme, "title")
        title.set('lang', 'en')
        title.text = pr.get("title")

        if pr.get('description') is not None:
            description = etree.SubElement(programme, "desc")
            description.set('lang', 'en')
            description.text = remove_control_characters(pr.get("description"))

        if pr.get('icon') is not None:
            icon = etree.SubElement(programme, "icon")
            icon.set('src', pr.get("icon"))

    return etree.tostring(data, pretty_print=True, encoding='utf-8')

rsess = requests_cache.CachedSession(cache_name = Path(__file__).parent.joinpath("epgcache"), expire_after=timedelta(days=3))

# Load the channels data
channels_data = get_channels_config()

programme_data = []
for channel in channels_data:
    print(channel.get('name'))
    # If EPG is to be sourced from Sky:
    if channel.get('src') == "sky":
        # Get some epoch times - right now, 12am tomorrow and 12am the day after tomorrow (so 48h)
        epoch_times = get_days("sky")
        firstdate = True
        for epoch in epoch_times:
            url = f"https://epgservices.sky.com/5.2.2/api/2.0/channel/json/{channel.get('provider_id')}/{epoch}/86400/4"
            # don't get today's result from cache, because there may be late schedule changes
            if firstdate: rsess.delete(url)
            req = rsess.get(url)
            if req.status_code != 200:
                continue
            result = json.loads(req.text)
            epg_data = result['listings'][f"{channel.get('provider_id')}"]
            for item in epg_data:
                title = item['t']
                desc = item['d'] if 'd' in item else None
                start = int(item['s'])
                end = int(item['s']) + int(item['m'][1])
                icon = f"http://epgstatic.sky.com/epgdata/1.0/paimage/46/1/{item['img']}" if 'img' in item else None
                ch_name = channel.get('xmltv_id')

                programme_data.append({
                    "title": title,
                    "description": desc,
                    "start": start,
                    "stop": end,
                    "icon": icon,
                    "channel": ch_name
                })
            firstdate = False
    if channel.get('src') == "freeview":
        epoch_times = get_days("freeview")
        firstdate = True
        for epoch in epoch_times:
            # Get programme data for Freeview multiplex
            url = f"https://www.freeview.co.uk/api/tv-guide?nid={channel['region_id']}&start={str(epoch)}"
            # don't get today's result from cache, because there may be late schedule changes
            if firstdate: rsess.delete(url)
            req = rsess.get(url)
            if req.status_code != 200:
                continue
            result = json.loads(req.text)
            epg_data = result['data']['programs']

            ch_match = filter(lambda ch: ch['service_id'] == channel.get('provider_id'), epg_data)

            # For each channel in result, get UID from JSON
            for item in ch_match:
                service_id = item.get('service_id')

                # Freeview API returns basic info with EPG API call
                for listing in item.get('events'):

                    ch_name = channel.get('xmltv_id')
                    title = listing.get("main_title")
                    desc = listing.get("secondary_title") if "secondary_title" in listing else \
                        "No further information..."
                    temp_start = datetime.strptime(listing.get('start_time'), "%Y-%m-%dT%H:%M:%S%z")
                    duration = parse_duration(listing.get('duration'))
                    end = (temp_start + duration).timestamp()
                    start = temp_start.timestamp()

                    # There's another URL for more in-depth programme information
                    data_url = f"https://www.freeview.co.uk/api/program?sid={service_id}&nid={channel.get('region_id')}" \
                               f"&pid={listing.get('program_id')}&start_time={listing.get('start_time')}&duration={listing.get('duration')}"
                    info_req = rsess.get(data_url)

                    try:
                        res = json.loads(info_req.text)
                    except Exception as ex:
                        continue

                    # Should only return one programme, so just get the first if one exists
                    if 'programs' in res['data']:
                        if len(res['data']['programs']) > 0:
                            info = res['data']['programs'][0]
                        else:
                            info = None

                    if info is not None:
                        # Update the description with Freeview Play's medium option if available
                        if len(info.get('synopsis')) > 0:
                            desc = info.get('synopsis').get('medium') if 'synopsis' in info else ''

                        # Get Freeview Play's image, or use the fallback
                        if 'image_url' in info:
                            icon = info.get('image_url') + '?w=800'
                        elif 'fallback_image_url' in listing:
                            icon = listing.get('fallback_image_url') + '?w=800'
                        else:
                            icon = None
                    else:
                        desc = ''
                        icon = None

                    programme_data.append({
                        "title":       title,
                        "description": desc,
                        "start":       start,
                        "stop":        end,
                        "icon":        icon,
                        "channel":     ch_name
                    })

channel_xml = build_xmltv(channels_data, programme_data)

# Write some XML
with Path(__file__).parent.joinpath('epg.xml').open('wb') as f:
    f.write(channel_xml)
    f.close()
