import sys, os
sys.path.insert(0, r'C:/Users/wszy1/WorkBuddy/2026-09-18-01-07-46/inkrealm')
from fastapi.testclient import TestClient

import server.main as m

with TestClient(m.app) as c:
    for p in ['/', '/index.html', '/_astro/App.Cksk48gD.js', '/favicon.svg']:
        r = c.get(p)
        print(p, r.status_code, '| Cache-Control:', r.headers.get('cache-control'), '| pragma:', r.headers.get('pragma'))
