# just a helper script to get all the available channels and IDs in the sky EPG
import requests
import json
from pathlib import Path
from datetime import datetime, timedelta

s=requests.Session()

with Path(__file__).parent.joinpath('AllSkyChannels.txt').open('w') as f:

	for ch in range(999):

		url=f"https://epgservices.sky.com/tvlistings-proxy/TVListingsProxy/tvlistings.json?channels={1000+ch*10},{1000+ch*10+1},{1000+ch*10+2},{1000+ch*10+3},{1000+ch*10+4},{1000+ch*10+5},{1000+ch*10+6},{1000+ch*10+7},{1000+ch*10+8},{1000+ch*10+9}&dur=0&detail=7&time={datetime.now():%Y%m%d}0000"
		grab=s.get(url)
		try:
			res=json.loads(grab.text)
		except Exception as ex:
			print(f"failed: {grab}")
			continue
		# res looks like {"channels":[{"title":"PBC","channeltype":"1","channelid":"1011","genre":null,"program":[{"eventid":"308","channelid":"1011","date":"21\/12\/23","start":"1703116800000","dur":"21600","title":"Amritvela","genre":"5","subgenre":"10","edschoice":"false","parentalrating":{"k":"0","v":"--"},"sound":{"k":"0","v":"Monaural"},"remoteRecordable":"false","record":"1","scheduleStatus":"FINISHED","blackout":"false","movielocator":"null"}]},{"title":"Zee TV HD","channeltype":"25","channelid":"1016","genre":null,"program":[{"eventid":

		if "channels" in res:
			for chx in res["channels"]:
				print(f"{chx['channelid']}: {chx['title']}", file = f)
	f.close()
