import time
import random
import pymysql
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

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


class ChengduAnjukeSpider:
    def __init__(self, headless=True):
        self.headless = headless
        self.driver = None
        self.areas = [
            'wuhou', 'gaoxin', 'chenghua', 'jinniu', 'jinjiang',
            'qingyang', 'shuangliu', 'longquanyi', 'wenjiang', 'piduqu',
            'xindu', 'tianfuxinqu', 'qingbaijiangqu', 'dujiangyan',
            'chongzhoushi', 'jianyang',
        ]

    def _create_driver(self):
        options = webdriver.ChromeOptions()
        if self.headless:
            options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option('excludeSwitches', ['enable-automation'])
        options.add_experimental_option('useAutomationExtension', False)
        options.add_argument(
            '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0'
        )
        driver = webdriver.Chrome(options=options)
        driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': 'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
        })
        driver.set_page_load_timeout(30)
        return driver

    def _get_page(self, url):
        for attempt in range(3):
            try:
                self.driver.get(url)
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_all_elements_located((By.CLASS_NAME, 'property'))
                )
                time.sleep(random.uniform(2, 4))
                html = self.driver.page_source
                if '验证' not in html and 'captcha' not in html.lower():
                    return html
            except Exception:
                pass
            time.sleep(10 * (attempt + 1))
        return None

    @staticmethod
    def parse_list(html):
        soup = BeautifulSoup(html, 'html.parser')
        cards = soup.find_all('div', class_='property')
        houses = []
        for card in cards:
            try:
                house = {}
                t = card.find('h3', class_='property-content-title-name')
                house['title'] = t.get('title', '').strip() if t else ''

                a = card.find('a', class_='property-ex', href=True)
                house['detail_url'] = a['href'] if a else ''

                pn = card.find('span', class_='property-price-total-num')
                pt = card.find('span', class_='property-price-total-text')
                house['total_price'] = f"{pn.text.strip()}{pt.text.strip()}" if pn and pt else ''

                up = card.find('p', class_='property-price-average')
                house['unit_price'] = up.text.strip() if up else ''

                info = card.find('div', class_='property-content-info')
                if info:
                    texts = [p.text.strip() for p in info.find_all('p', class_='property-content-info-text')]
                    house['layout_full'] = texts[0] if len(texts) > 0 else ''
                    house['area_size'] = texts[1] if len(texts) > 1 else ''
                    house['orientation'] = texts[2] if len(texts) > 2 else ''
                    house['floor'] = texts[3] if len(texts) > 3 else ''
                    house['build_year'] = texts[4] if len(texts) > 4 else ''

                cm = card.find('p', class_='property-content-info-comm-name')
                house['community'] = cm.text.strip() if cm else ''

                ad = card.find('p', class_='property-content-info-comm-address')
                if ad:
                    sp = [s.text.strip() for s in ad.find_all('span')]
                    house['district'] = sp[0] if len(sp) > 0 else ''
                    house['sub_district'] = sp[1] if len(sp) > 1 else ''
                    house['street'] = sp[2] if len(sp) > 2 else ''
                else:
                    house['district'] = house['sub_district'] = house['street'] = ''

                tg = card.find_all('span', class_='property-content-info-tag')
                house['tags'] = ','.join(t.text.strip() for t in tg)
                houses.append(house)
            except Exception:
                continue
        return houses

    def _load_progress(self):
        progress = {}
        try:
            conn = get_db()
            with conn.cursor() as cur:
                cur.execute("SELECT area_code, last_page FROM crawl_progress WHERE source='anjuke'")
                for row in cur.fetchall():
                    progress[row[0]] = row[1]
            conn.close()
        except Exception as e:
            print(f"加载进度失败: {e}")
        return progress

    def _save_progress(self, area_code, page, count):
        try:
            conn = get_db()
            with conn.cursor() as cur:
                cur.execute('''
                    INSERT INTO crawl_progress (area_code, source, last_page, total_count)
                    VALUES (%s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        last_page = GREATEST(last_page, VALUES(last_page)),
                        total_count = total_count + VALUES(total_count),
                        updated_at = CURRENT_TIMESTAMP
                ''', (area_code, 'anjuke', page, count))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"保存进度失败: {e}")

    def _save_to_db(self, houses):
        if not houses:
            return 0
        sql = '''
            INSERT IGNORE INTO house_listings
            (title, total_price, unit_price, area_size, layout_full,
             orientation, floor, build_year, community, district,
             sub_district, street, tags, area_code, detail_url, source)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        '''
        inserted = 0
        try:
            conn = get_db()
            with conn.cursor() as cur:
                for h in houses:
                    cur.execute(sql, (
                        h.get('title'), h.get('total_price'), h.get('unit_price'),
                        h.get('area_size'), h.get('layout_full'), h.get('orientation'),
                        h.get('floor'), h.get('build_year'), h.get('community'),
                        h.get('district'), h.get('sub_district'), h.get('street'),
                        h.get('tags'), h.get('area_code'), h.get('detail_url'), 'anjuke'
                    ))
                    if cur.rowcount > 0:
                        inserted += 1
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"写入数据库失败: {e}")
        return inserted

    def run(self, pages_per_area=10, areas_per_batch=2):
        progress = self._load_progress()

        remaining = [a for a in self.areas if progress.get(a, 0) < 50]
        remaining.sort(key=lambda a: progress.get(a, 0))

        if not remaining:
            print("所有区域已爬完")
            return

        batch = remaining[:areas_per_batch]
        print(f"\n本批次区域: {batch} | 每区域页数: {pages_per_area}")
        print("-" * 50)

        self.driver = self._create_driver()
        try:
            print("浏览器预热...")
            self.driver.get('https://chengdu.anjuke.com/')
            time.sleep(random.uniform(3, 5))

            total_new = 0
            t0 = time.time()

            for area in batch:
                start = progress.get(area, 0) + 1
                end = min(start + pages_per_area - 1, 50)
                print(f"\n  [{area}] 第{start}-{end}页")
                area_inserted = 0

                for page in range(start, end + 1):
                    url = (f'https://chengdu.anjuke.com/sale/{area}/'
                           if page == 1 else
                           f'https://chengdu.anjuke.com/sale/{area}/p{page}/')

                    html = self._get_page(url)
                    if html is None:
                        print(f"    第{page}页被拦截，终止")
                        break

                    houses = self.parse_list(html)
                    if not houses:
                        break

                    for h in houses:
                        h['area_code'] = area

                    n = self._save_to_db(houses)
                    area_inserted += n
                    total_new += n

                    self._save_progress(area, page, n)

                    print(f"    第{page:2d}页: {len(houses)}条解析 -> {n}条入库 (累计{area_inserted})")
                    time.sleep(random.uniform(8, 15))

                print(f"  [{area}] 完成: {area_inserted} 条入库")

            print(f"\n 完成: {total_new} 条新数据入库 | 耗时{(time.time()-t0)/60:.1f}分钟")

        finally:
            self.driver.quit()
            print("浏览器已关闭")


if __name__ == '__main__':
    spider = ChengduAnjukeSpider(headless=True)
    spider.run(pages_per_area=10, areas_per_batch=2)
