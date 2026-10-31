"""Synthetic quotes ONLY for isolated local acceptance; never shipped in the image.

Injected at the provider boundary. Real parsing, raw storage, SQL, locking and
scheduled entry remain unchanged. No API key or network request is used.
"""
from datetime import date, datetime
import os
import time

import httpx

from market_data.calendar import EASTERN, sessions
from market_data.provider import MassiveDailyProvider
from market_data.scheduled import main


def response(request):
    time.sleep(float(os.getenv('FIXTURE_DELAY_SECONDS', '0')))
    parts = request.url.path.split('/')
    symbol = parts[4]
    start, end = date.fromisoformat(parts[-2]), date.fromisoformat(parts[-1])
    bars = [{'o':100, 'h':110, 'l':90, 'c':105, 'v':1000,
             't':int(datetime.combine(day,datetime.min.time(),EASTERN).timestamp()*1000)}
            for day in sessions(start,end)]
    if os.getenv('FIXTURE_QUALITY_FAILURE') == 'true' and bars:
        bars.append({**bars[0], 'c':-1})
    return httpx.Response(200,json={'ticker':symbol,'status':'OK','adjusted':True,
                                  'resultsCount':len(bars),'results':bars})


if __name__ == '__main__':
    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        raise SystemExit(main(provider_factory=lambda unused: MassiveDailyProvider('synthetic-only',client)))
