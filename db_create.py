import pymysql

DB_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': 'Qq735228(',
    'charset': 'utf8mb4'
}

DATABASE_NAME = 'chengdu_house'


def init_database():
    conn = pymysql.connect(**DB_CONFIG)

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS {DATABASE_NAME} "
                f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            print("数据库 'chengdu_house' 已就绪")

        conn.select_db(DATABASE_NAME)

        with conn.cursor() as cursor:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS house_listings (
                    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
                    title VARCHAR(500) NOT NULL COMMENT '房源标题',
                    total_price VARCHAR(50) COMMENT '总价',
                    unit_price VARCHAR(50) COMMENT '单价',
                    area_size VARCHAR(50) COMMENT '建筑面积',
                    layout_full VARCHAR(50) COMMENT '户型',
                    orientation VARCHAR(20) COMMENT '朝向',
                    floor VARCHAR(100) COMMENT '楼层',
                    build_year VARCHAR(20) COMMENT '建造年份',
                    community VARCHAR(200) COMMENT '小区名称',
                    district VARCHAR(50) COMMENT '城区',
                    sub_district VARCHAR(50) COMMENT '商圈',
                    street VARCHAR(300) COMMENT '详细地址',
                    tags VARCHAR(300) COMMENT '特色标签',
                    area_code VARCHAR(30) COMMENT '区域代码',
                    detail_url VARCHAR(800) COMMENT '详情页链接',
                    source VARCHAR(20) DEFAULT 'anjuke' COMMENT '数据来源',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_district (district),
                    INDEX idx_area_code (area_code),
                    INDEX idx_community (community)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                  COLLATE utf8mb4_unicode_ci COMMENT='成都二手房房源核心数据'
            ''')
            print("表 'house_listings' 已创建")

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS crawl_progress (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    area_code VARCHAR(30) NOT NULL,
                    source VARCHAR(20) DEFAULT 'anjuke',
                    last_page INT DEFAULT 0,
                    total_count INT DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                               ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY uk_area_source (area_code, source)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                  COLLATE utf8mb4_unicode_ci COMMENT='爬虫进度记录'
            ''')
            print("[OK] 表 'crawl_progress' 已创建")

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS house_poi (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    community VARCHAR(200) COMMENT '小区名称',
                    street VARCHAR(300) COMMENT '详细地址',
                    lng DECIMAL(10, 7) COMMENT '经度',
                    lat DECIMAL(10, 7) COMMENT '纬度',
                    nearest_subway_dist INT DEFAULT -1 COMMENT '最近地铁站距离（米）',
                    subway_count INT DEFAULT 0 COMMENT '1500米内地铁站数量',
                    school_count INT DEFAULT 0 COMMENT '2000米内学校数量',
                    poi_updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                                     ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_location (lng, lat),
                    INDEX idx_street (street(100))
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                  COLLATE utf8mb4_unicode_ci COMMENT='房源周边POI特征'
            ''')
            print("[OK] 表 'house_poi' 已创建")

            conn.commit()

        print("完成")

    except pymysql.err.OperationalError as e:
        print(f"连接失败: {e}")
    finally:
        conn.close()


if __name__ == '__main__':
    init_database()
