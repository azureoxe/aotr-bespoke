#!/usr/bin/env python3
"""算所有 Bespoke 房源到 10 所主流学校的公交通勤时间。
增量：已算过的 (地址, 学校) 不会重复请求。
"""
import json, urllib.request, urllib.parse, os, time, sys
from datetime import datetime, timedelta

OUT = os.path.join(os.path.dirname(__file__), "commute.json")
GEOCODES_FILE = os.path.join(os.path.dirname(__file__), "geocodes.json")
ENV_FILE = os.path.join(os.path.dirname(__file__), ".env")

# 读 API key
with open(ENV_FILE) as f:
    for line in f:
        if line.startswith("GOOGLE_MAPS_API_KEY="):
            API_KEY = line.split("=", 1)[1].strip()
            break

# 10 所学校（lat/lng 来自明道学校库）
SCHOOLS = [
    {"key": "NUS",     "name_cn": "新加坡国立大学",       "name_en": "NUS",            "lat": 1.297137, "lng": 103.777527},
    {"key": "NTU",     "name_cn": "南洋理工大学",         "name_en": "NTU",            "lat": 1.344585, "lng": 103.681254},
    {"key": "SMU",     "name_cn": "新加坡管理大学",       "name_en": "SMU",            "lat": 1.296273, "lng": 103.850158},
    {"key": "JCU",     "name_cn": "詹姆斯库克大学",       "name_en": "JCU Singapore",  "lat": 1.315849, "lng": 103.876108},
    {"key": "Curtin",  "name_cn": "科廷大学新加坡",       "name_en": "Curtin SG",      "lat": 1.288494, "lng": 103.779539},
    {"key": "SIM",     "name_cn": "新加坡管理学院",       "name_en": "SIM",            "lat": 1.329307, "lng": 103.776531},
    {"key": "MDIS",    "name_cn": "新加坡管理发展学院",   "name_en": "MDIS",           "lat": 1.297073, "lng": 103.801167},
    {"key": "PSB",     "name_cn": "新加坡PSB学院",        "name_en": "PSB",            "lat": 1.291153, "lng": 103.857678},
    {"key": "Kaplan",  "name_cn": "新加坡楷博",           "name_en": "Kaplan",         "lat": 1.302293, "lng": 103.849796},
    {"key": "LASALLE", "name_cn": "拉萨尔艺术学院",       "name_en": "LASALLE",        "lat": 1.302940, "lng": 103.851517},
]

# 出发时间：下周一 9 AM 北京时间（== SG 时间无差，都是 UTC+8）
def next_monday_9am_ts():
    now = datetime.now()
    days_ahead = 0 - now.weekday() + 7  # 下周一
    next_monday = now + timedelta(days=days_ahead)
    return int(next_monday.replace(hour=9, minute=0, second=0, microsecond=0).timestamp())

DEPARTURE_TS = next_monday_9am_ts()

def call_distance_matrix(origins, destinations):
    """Google Distance Matrix: 一次请求最多 25 origins × 25 destinations。"""
    url = "https://maps.googleapis.com/maps/api/distancematrix/json?" + urllib.parse.urlencode({
        "origins": "|".join(f"{o['lat']},{o['lng']}" for o in origins),
        "destinations": "|".join(f"{d['lat']},{d['lng']}" for d in destinations),
        "mode": "transit",
        "departure_time": DEPARTURE_TS,
        "key": API_KEY,
    })
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)

def main():
    # 加载已编码的房源地址 → lat/lng
    with open(GEOCODES_FILE) as f:
        geocodes = json.load(f)
    addrs = sorted([a for a, g in geocodes.items() if g and g.get("lat")])
    print(f"待算房源: {len(addrs)} 套")
    print(f"学校: {len(SCHOOLS)} 所")
    print(f"出发时间: {datetime.fromtimestamp(DEPARTURE_TS)} (周一 9:00)")

    # 加载已有缓存
    cache = {"schools": SCHOOLS, "matrix": {}, "computed_at": ""}
    if os.path.exists(OUT):
        with open(OUT) as f:
            cache = json.load(f)
        print(f"已缓存 {sum(len(v) for v in cache.get('matrix', {}).values())} 个 (房源,学校) 对")
    cache["schools"] = SCHOOLS

    # 找出还没算的 (addr, school) 对
    todo = []
    for addr in addrs:
        for sch in SCHOOLS:
            if cache["matrix"].get(addr, {}).get(sch["key"]) is None:
                todo.append((addr, sch))
    print(f"待算 {len(todo)} 个 (房源,学校) 对")
    if not todo:
        print("✅ 全部已缓存")
        return

    # 按学校分组：每次请求 25 个房源 × 1 个学校
    BATCH = 25
    school_to_addrs = {}
    for addr, sch in todo:
        school_to_addrs.setdefault(sch["key"], []).append(addr)

    total_calls = sum((len(v) + BATCH - 1) // BATCH for v in school_to_addrs.values())
    done_calls = 0
    print(f"预计 {total_calls} 次 API 请求\n")

    for sch_key, sch_addrs in school_to_addrs.items():
        sch = next(s for s in SCHOOLS if s["key"] == sch_key)
        for i in range(0, len(sch_addrs), BATCH):
            batch_addrs = sch_addrs[i:i + BATCH]
            origins = [{"lat": geocodes[a]["lat"], "lng": geocodes[a]["lng"]} for a in batch_addrs]
            try:
                resp = call_distance_matrix(origins, [sch])
            except Exception as e:
                print(f"  ❌ API 错误: {e}")
                time.sleep(2)
                continue

            if resp.get("status") != "OK":
                print(f"  ❌ {resp.get('status')} - {resp.get('error_message','')}")
                continue

            ok_in_batch = 0
            for j, addr in enumerate(batch_addrs):
                el = resp["rows"][j]["elements"][0]
                if el.get("status") == "OK":
                    cache["matrix"].setdefault(addr, {})[sch_key] = {
                        "min": round(el["duration"]["value"] / 60),
                        "km": round(el["distance"]["value"] / 1000, 1),
                    }
                    ok_in_batch += 1
                else:
                    cache["matrix"].setdefault(addr, {})[sch_key] = None
            done_calls += 1
            print(f"[{done_calls}/{total_calls}] {sch_key} ← {len(batch_addrs)} 房源 ({ok_in_batch} OK)")

            # 每 5 次请求保存一次（防中断丢数据）
            if done_calls % 5 == 0:
                cache["computed_at"] = datetime.now().isoformat()
                with open(OUT, "w") as f:
                    json.dump(cache, f, ensure_ascii=False, indent=1)

            time.sleep(0.1)  # Google 限速 100/sec，留点 buffer

    # 最终保存
    cache["computed_at"] = datetime.now().isoformat()
    with open(OUT, "w") as f:
        json.dump(cache, f, ensure_ascii=False, indent=1)

    # 统计
    total_pairs = sum(len(v) for v in cache["matrix"].values())
    ok_pairs = sum(1 for v in cache["matrix"].values() for vv in v.values() if vv)
    print(f"\n完成：{ok_pairs}/{total_pairs} 成功")
    print(f"写入 {OUT}")

if __name__ == "__main__":
    main()
