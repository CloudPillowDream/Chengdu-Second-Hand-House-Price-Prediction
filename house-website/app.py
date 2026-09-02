from flask import Flask, render_template, request, jsonify
import pymysql
import pandas as pd
import numpy as np
import pickle
import json
import os
from pathlib import Path

app = Flask(__name__)

DB_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': 'Qq735228(',  
    'database': 'chengdu_house',
    'charset': 'utf8mb4'
}

MODEL_DIR = Path(__file__).parent / "ml"
MODEL_PATH = MODEL_DIR / "xgboost_model.pkl"
SCALER_PATH = MODEL_DIR / "scaler.pkl"
ENC_MAP_PATH = MODEL_DIR / "enc_map.pkl"
FEATURES_PATH = MODEL_DIR / "feature_names.pkl"

model = None
scaler = None
enc_map = None
feature_names = None

def load_model():

    global model, scaler, enc_map, feature_names
    try:
        if MODEL_PATH.exists():
            with open(MODEL_PATH, "rb") as f:
                model = pickle.load(f)
            print(f"[OK] 模型已加载: {MODEL_PATH}")
        if SCALER_PATH.exists():
            with open(SCALER_PATH, "rb") as f:
                scaler = pickle.load(f)
            print(f"[OK] Scaler已加载")
        if ENC_MAP_PATH.exists():
            with open(ENC_MAP_PATH, "rb") as f:
                enc_map = pickle.load(f)
            print(f"[OK] 编码映射已加载")
        if FEATURES_PATH.exists():
            with open(FEATURES_PATH, "rb") as f:
                feature_names = pickle.load(f)
            print(f"[OK] 特征列表已加载: {len(feature_names)}个特征")
        if model is None:
            print("[WARN] 未找到XGBoost模型，将使用规则预测")
    except Exception as e:
        print(f"[ERROR] 加载模型失败: {e}")
        model = None

load_model()

def get_db_connection():
    return pymysql.connect(**DB_CONFIG)

def create_features(input_data):
    area = float(input_data.get('area', 100))
    district = input_data.get('district', '锦江区')
    rooms = float(input_data.get('rooms', 3))
    halls = float(input_data.get('halls', 1))
    toilets = float(input_data.get('toilets', 1))
    build_year = float(input_data.get('build_year', 2015))
    has_subway = 1 if input_data.get('has_subway', False) else 0
    nearest_subway_dist = float(input_data.get('nearest_subway_dist', 2000))
    subway_count = float(input_data.get('subway_count', 0))
    school_count = float(input_data.get('school_count', 0))
    lng = float(input_data.get('lng', 0))
    lat = float(input_data.get('lat', 0))
    community = input_data.get('community', '')
    street = input_data.get('street', '')
    
    house_age = 2026 - build_year
    
    row = {
        'area_num': area,
        'room_count': rooms,
        'hall_count': halls,
        'toilet_count': toilets,
        'house_age': house_age,
        'nearest_subway_dist': nearest_subway_dist,
        'subway_count': subway_count,
        'school_count': school_count,
        'has_subway': has_subway,
        'lng': lng,
        'lat': lat,
        'district': district,
        'community': community,
        'street': street,
    }
    
    F = pd.DataFrame([row])
    
    # 交互特征
    F['area_x_subway'] = F['area_num'] * F['subway_count']
    F['area_x_school'] = F['area_num'] * F['school_count']
    F['age_x_area'] = F['house_age'] * F['area_num']
    F['age_x_subwaydist'] = F['house_age'] * (F['nearest_subway_dist'].fillna(5000) + 1)
    F['subway_x_school'] = F['subway_count'] * F['school_count']
    F['room_density'] = F['room_count'] / (F['area_num'] + 1)
    F['area_per_room'] = F['area_num'] / (F['room_count'] + 1)
    
    # 非线性变换
    F['log_area'] = np.log1p(F['area_num'])
    F['area_squared'] = F['area_num'] ** 2
    F['sqrt_area'] = np.sqrt(F['area_num'])
    F['inv_subway_dist'] = 1 / (F['nearest_subway_dist'].fillna(5000) + 100)
    F['age_squared'] = F['house_age'] ** 2
    F['log_age'] = np.log1p(F['house_age'].clip(lower=0))
    
    # 分箱
    F['area_bin'] = pd.cut(F['area_num'], bins=[0,60,90,120,150,200,500],
                           labels=['<60','60-90','90-120','120-150','150-200','200+']).astype(str)
    F['age_bin'] = pd.cut(F['house_age'], bins=[-1,5,10,15,20,30,100],
                          labels=['新房','5-10年','10-15年','15-20年','20-30年','30年+']).astype(str)
    F['subway_bin'] = pd.cut(F['nearest_subway_dist'].fillna(9999),
                             bins=[-1,500,1000,2000,5000,99999],
                             labels=['<500m','500-1k','1k-2k','2k-5k','无地铁']).astype(str)
    
    # 目标编码
    gm = enc_map.get('global_mean', 200.0) if enc_map else 200.0
    
    if enc_map:
        F['district_te'] = F['district'].map(enc_map.get('district_te', {})).fillna(gm)
        F['area_bin_te'] = F['area_bin'].map(enc_map.get('area_bin_te', {})).fillna(gm)
        F['age_bin_te'] = F['age_bin'].map(enc_map.get('age_bin_te', {})).fillna(gm)
        F['subway_bin_te'] = F['subway_bin'].map(enc_map.get('subway_bin_te', {})).fillna(gm)
        F['district_price_mean'] = F['district'].map(enc_map.get('district_mean', {})).fillna(gm)
        F['district_price_std'] = F['district'].map(enc_map.get('district_std', {})).fillna(gm)
        F['district_price_median'] = F['district'].map(enc_map.get('district_median', {})).fillna(gm)
    else:
        for col in ['district_te', 'area_bin_te', 'age_bin_te', 'subway_bin_te',
                    'district_price_mean', 'district_price_std', 'district_price_median']:
            F[col] = gm
    
    # 组合特征
    F['total_rooms'] = F['room_count'] + F['hall_count']
    F['toilet_ratio'] = F['toilet_count'] / (F['room_count'] + 1)
    F['is_luxury'] = ((F['area_num'] > 150) & (F['subway_count'] >= 2)).astype(int)
    F['old_and_far'] = ((F['house_age'] > 20) & (F['nearest_subway_dist'].fillna(9999) > 2000)).astype(int)
    
    # 删除类别列
    F = F.drop(columns=['district','community','street','area_bin','age_bin','subway_bin'], errors='ignore')
    
    # 删除全NaN列
    all_nan = F.columns[F.isnull().all()].tolist()
    if all_nan:
        F = F.drop(columns=all_nan)
    
    # 填充剩余NaN
    for col in F.columns:
        if F[col].isnull().sum() > 0:
            med = F[col].median()
            F[col] = F[col].fillna(med if not pd.isna(med) else gm)
    
    # 对齐特征顺序
    if feature_names:
        for c in feature_names:
            if c not in F.columns:
                F[c] = 0
        F = F[feature_names]
    
    return F.astype(float)


@app.route('/')
def home():
    """首页"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM house_listings")
            total = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(DISTINCT district) FROM house_listings WHERE district IS NOT NULL")
            district_count = cur.fetchone()[0]
            
            cur.execute("""
                SELECT AVG(CAST(REGEXP_REPLACE(total_price, '[^0-9.]', '') AS DECIMAL(10,2))) 
                FROM house_listings
            """)
            avg_price = cur.fetchone()[0] or 0
    finally:
        conn.close()
    
    return render_template('index.html', 
                         total=total, 
                         district_count=district_count,
                         avg_price=round(float(avg_price), 2),
                         has_model=(model is not None))

@app.route('/predict')
def predict_page():
    """房价预测页面"""
    districts = ['高新区','锦江区','青羊区','武侯区','成华区','天府新区',
                 '金牛区','双流区','龙泉驿','温江区','郫都区','新都区']
    return render_template('predict.html', districts=districts, has_model=(model is not None))

@app.route('/api/predict', methods=['POST'])
def api_predict():
    """房价预测API"""
    data = request.get_json()
    
    try:
        if model is not None and scaler is not None:
            # XGBoost预测
            X_features = create_features(data)
            X_scaled = scaler.transform(X_features)
            prediction = model.predict(X_scaled)[0]
            prediction = max(10, min(2000, float(prediction)))
            model_type = "xgboost"
        else:
            # 规则预测(fallback)
            area = float(data.get('area', 100))
            district = data.get('district', '锦江区')
            rooms = int(data.get('rooms', 3))
            build_year = float(data.get('build_year', 2015))
            has_subway = data.get('has_subway', False)
            nearest_subway_dist = float(data.get('nearest_subway_dist', 2000))
            
            DISTRICT_BASE = {
                '锦江区': 22000, '青羊区': 21500, '武侯区': 20000, '金牛区': 17500,
                '成华区': 18000, '高新区': 25000, '天府新区': 19500, '双流区': 14500,
                '龙泉驿': 13000, '温江区': 11500, '郫都区': 11000, '新都区': 10500,
            }
            base = DISTRICT_BASE.get(district, 16000)
            room_coeff = {1: 1.05, 2: 1.0, 3: 0.98, 4: 0.95, 5: 0.92, 6: 0.88}.get(rooms, 0.95)
            age = max(0, 2026 - build_year)
            age_coeff = max(0.6, 1 - age * 0.015)
            
            subway_coeff = 1.0
            if has_subway or nearest_subway_dist < 1500:
                if nearest_subway_dist < 500: subway_coeff = 1.12
                elif nearest_subway_dist < 1000: subway_coeff = 1.08
                elif nearest_subway_dist < 1500: subway_coeff = 1.04
            
            unit_price = base * room_coeff * age_coeff * subway_coeff
            prediction = (unit_price * area) / 10000
            model_type = "fallback"
        
        unit_price = (prediction * 10000) / float(data.get('area', 100))
        
        return jsonify({
            'total_price': round(prediction, 2),
            'unit_price': round(unit_price, 0),
            'model': model_type,
            'status': 'ok'
        })
        
    except Exception as e:
        return jsonify({'error': str(e), 'status': 'error'}), 500

@app.route('/search')
def search_page():
    """房源搜索页面"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT district FROM house_listings WHERE district IS NOT NULL")
            districts = [r[0] for r in cur.fetchall()]
    finally:
        conn.close()
    return render_template('search.html', districts=districts)

@app.route('/api/search')
def api_search():
    """搜索API"""
    district = request.args.get('district', '')
    layout = request.args.get('layout', '')
    min_price = request.args.get('min_price', type=float)
    max_price = request.args.get('max_price', type=float)
    page = request.args.get('page', 1, type=int)
    page_size = 12
    
    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            where = "WHERE 1=1"
            params = []
            
            if district:
                where += " AND district = %s"
                params.append(district)
            if layout:
                where += " AND layout_full LIKE %s"
                params.append(f'%{layout}%')
            
            # 查询总数
            cur.execute(f"SELECT COUNT(*) as total FROM house_listings {where}", params)
            total = cur.fetchone()['total']
            
            # 查询数据
            offset = (page - 1) * page_size
            cur.execute(f"""
                SELECT * FROM house_listings 
                {where}
                ORDER BY id DESC
                LIMIT %s OFFSET %s
            """, params + [page_size, offset])
            
            listings = cur.fetchall()
            
            # 价格过滤（在Python层做，因为total_price是字符串）
            if min_price or max_price:
                filtered = []
                for h in listings:
                    match = str(h['total_price']).replace('万', '') if h['total_price'] else None
                    if match:
                        try:
                            price = float(match)
                            if min_price and price < min_price:
                                continue
                            if max_price and price > max_price:
                                continue
                            filtered.append(h)
                        except:
                            filtered.append(h)
                    else:
                        filtered.append(h)
                listings = filtered
            
            return jsonify({
                'listings': listings,
                'total': total,
                'page': page,
                'total_pages': (total + page_size - 1) // page_size
            })
    finally:
        conn.close()

@app.route('/analytics')
def analytics_page():
    """数据分析页面"""
    conn = get_db_connection()
    stats = {}
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            # 基础统计
            cur.execute("SELECT COUNT(*) as count FROM house_listings")
            stats['total'] = cur.fetchone()['count']
            
            # 各区域统计
            cur.execute("""
                SELECT district, 
                       COUNT(*) as count,
                       AVG(CAST(REGEXP_REPLACE(total_price, '[^0-9.]', '') AS DECIMAL(10,2))) as avg_price
                FROM house_listings 
                WHERE district IS NOT NULL
                GROUP BY district
                ORDER BY avg_price DESC
            """)
            stats['districts'] = cur.fetchall()
            
            # 户型分布TOP10
            cur.execute("""
                SELECT layout_full, COUNT(*) as count
                FROM house_listings 
                WHERE layout_full IS NOT NULL
                GROUP BY layout_full
                ORDER BY count DESC
                LIMIT 10
            """)
            stats['layouts'] = cur.fetchall()
            
            # 热门小区TOP10
            cur.execute("""
                SELECT community, district, COUNT(*) as count,
                       AVG(CAST(REGEXP_REPLACE(total_price, '[^0-9.]', '') AS DECIMAL(10,2))) as avg_price
                FROM house_listings 
                WHERE community IS NOT NULL
                GROUP BY community, district
                ORDER BY count DESC
                LIMIT 10
            """)
            stats['top_communities'] = cur.fetchall()
    finally:
        conn.close()
    
    return render_template('analytics.html', stats=stats)

if __name__ == '__main__':
    print("访问地址: http://127.0.0.1:5000")
    app.run(debug=True, port=5000)