import time
from math import radians, cos, sin, asin, sqrt

import pymysql
import requests

AMAP_KEY = 'a52350cc75166276ad2ba5cfc1402e1e'

DB_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': 'Qq735228(',
    'database': 'chengdu_house',
    'charset': 'utf8mb4'
}


def get_db():
    return pymysql.connect(**DB_CONFIG)

def geocode(address):
    url = 'https://restapi.amap.com/v3/geocode/geo'
    params = {'key': AMAP_KEY, 'address': f'成都市{address}', 'city': '成都'}
    try:
        r = requests.get(url, params=params, timeout=10).json()
        if r.get('status') == '1' and r.get('geocodes'):
            loc = r['geocodes'][0]['location']
            lng, lat = map(float, loc.split(','))
            return lng, lat
    except Exception:
        pass
    return None, None


def count_poi(lng, lat, keyword, radius):
    url = 'https://restapi.amap.com/v3/place/around'
    params = {
        'key': AMAP_KEY,
        'location': f'{lng},{lat}',
        'keywords': keyword,
        'radius': radius,
        'offset': 25,
        'page': 1,
    }
    try:
        r = requests.get(url, params=params, timeout=10).json()
        if r.get('status') == '1':
            return len(r.get('pois', []))
    except Exception:
        pass
    return 0


def haversine(lng1, lat1, lng2, lat2):
    lng1, lat1, lng2, lat2 = map(radians, [lng1, lat1, lng2, lat2])
    a = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lng2 - lng1) / 2) ** 2
    return 2 * 6371000 * asin(sqrt(a))


def nearest_subway(lng, lat):
    url = 'https://restapi.amap.com/v3/place/around'
    params = {
        'key': AMAP_KEY,
        'location': f'{lng},{lat}',
        'keywords': '地铁站',
        'radius': 5000,
        'offset': 1,
        'page': 1,
    }
    try:
        r = requests.get(url, params=params, timeout=10).json()
        if r.get('status') == '1' and r.get('pois'):
            loc = r['pois'][0].get('location', '')
            if loc:
                plng, plat = map(float, loc.split(','))
                return int(haversine(lng, lat, plng, plat))
    except Exception:
        pass
    return -1

def enrich_all():
    print("=" * 60)
    print("高德POI API特征补充")
    print("=" * 60)

    conn = get_db()
    with conn.cursor() as cur:
        cur.execute('''
            SELECT DISTINCT h.community, h.street
            FROM house_listings h
            LEFT JOIN house_poi p
                ON h.street = p.street AND h.community = p.community
            WHERE p.id IS NULL AND h.street != ''
            LIMIT 5000
        ''')
        addresses = cur.fetchall()
    conn.close()

    total = len(addresses)
    print(f"\n待处理地址数: {total}")
    print(f"每条地址调用3次POI API（地理编码+地铁距离+地铁数+学校数）\n")

    if not addresses:
        print("所有房源已补充POI，无需处理")
        return

    ok = 0
    ng = 0

    for idx, (community, street) in enumerate(addresses, 1):
        q = street if street else community
        lng, lat = geocode(q)
        time.sleep(0.05)

        if lng is None:
            ng += 1
            continue

        subway_dist = nearest_subway(lng, lat)
        time.sleep(0.05)
        subway_cnt = count_poi(lng, lat, '地铁站', 1500)
        time.sleep(0.05)
        school_cnt = count_poi(lng, lat, '学校', 2000)
        time.sleep(0.1)

        conn = get_db()
        with conn.cursor() as cur:
            cur.execute('''
                INSERT INTO house_poi
                (community, street, lng, lat,
                 nearest_subway_dist, subway_count, school_count)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    lng = VALUES(lng), lat = VALUES(lat),
                    nearest_subway_dist = VALUES(nearest_subway_dist),
                    subway_count = VALUES(subway_count),
                    school_count = VALUES(school_count)
            ''', (community, street, lng, lat, subway_dist, subway_cnt, school_cnt))
        conn.commit()
        conn.close()

        ok += 1
        if idx % 100 == 0:
            print(f"  [{idx}/{total}] 成功{ok} | 失败{ng}")

    print(f"\n{'=' * 60}")
    print(f"完成: 成功{ok} | 失败{ng}")
    print(f"日均API调用量: {total * 4}次")
    print("=" * 60)


if __name__ == '__main__':
    enrich_all()