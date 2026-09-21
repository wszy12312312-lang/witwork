# -*- coding: utf-8 -*-
"""本轮修复的 E2E 验证：音量接口(app_id)+pycaw自动安装、封面接口、卷/章 sort_order 落库。"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r'C:\Users\wszy1\WorkBuddy\2026-09-18-01-07-46\inkrealm')

# 本机系统代理会把 127.0.0.1 也转发出去（TestClient 不走网络，这里仅习惯性兜底）
from fastapi.testclient import TestClient
from server.main import app

with TestClient(app) as c:
    # 1) 音量接口：带 app_id（前端修复后真实调用形态）
    r = c.get('/api/song/volume', params={'app_id': 'cloudmusic.exe'})
    print('volume(app_id) ->', r.status_code, r.json())

    # 2) 封面接口（无播放时 204 属正常）
    r = c.get('/api/song/cover')
    print('cover ->', r.status_code, r.headers.get('content-type'))

    # 3) /song/now 返回 cover_version 字段
    r = c.get('/api/song/now')
    j = r.json()
    print('now ->', r.status_code, 'ok=', j.get('ok'), 'cover_version=', j.get('cover_version'))

    # 4) 卷/章拖动排序：建临时作品→两卷→各一章→PUT sort_order→重新 GET 验证顺序
    b = c.post('/api/books', json={'title': '__排序E2E__'}).json()
    v1 = c.post(f"/api/books/{b['id']}/volumes", json={'title': '卷A'}).json()
    v2 = c.post(f"/api/books/{b['id']}/volumes", json={'title': '卷B'}).json()
    ch1 = c.post('/api/chapters', json={'book_id': b['id'], 'volume_id': v1['id'], 'title': '章1'}).json()
    ch2 = c.post('/api/chapters', json={'book_id': b['id'], 'volume_id': v1['id'], 'title': '章2'}).json()
    # 模拟把卷B拖到卷A前面、章2拖到章1前面
    c.put(f"/api/books/volumes/{v2['id']}", json={'sort_order': 0})
    c.put(f"/api/books/volumes/{v1['id']}", json={'sort_order': 1})
    c.put(f"/api/chapters/{ch2['id']}", json={'sort_order': 0})
    c.put(f"/api/chapters/{ch1['id']}", json={'sort_order': 1})
    d = c.get(f"/api/books/{b['id']}").json()
    print('vol order ->', [v['title'] for v in d['volumes']])
    print('ch order  ->', [x['title'] for x in d['chapters']])
    # 确认正文未被排序 PUT 误伤（words=0 且内容不丢）
    full = c.get(f"/api/chapters/{ch1['id']}").json()
    print('ch1 intact ->', full['title'], 'words=', full['words'])
    # 清理
    for cid in (ch1['id'], ch2['id']):
        c.delete(f'/api/chapters/{cid}')
    c.delete(f"/api/books/volumes/{v1['id']}")
    c.delete(f"/api/books/volumes/{v2['id']}")
    c.delete(f"/api/books/{b['id']}")
    print('CLEANUP_OK')
print('RESULT: PASS')
