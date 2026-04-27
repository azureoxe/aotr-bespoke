#!/usr/bin/env python3
"""算每套 Bespoke 房源到最近 MRT 站的真实步行时间。
1. 从 OneMap 拉所有 MRT 站，按站名去重 → mrt_stations.json
2. 对每套房，找直线最近的 5 个候选 MRT，调 Google Distance Matrix（步行模式）取最准的
3. 增量缓存：已算过的房源不重算
"""
import json, urllib.request, urllib.parse, math, os, time, re

OUT_STATIONS = os.path.join(os.path.dirname(__file__), "mrt_stations.json")
OUT_WALK     = os.path.join(os.path.dirname(__file__), "mrt_walk.json")
GEOCODES     = os.path.join(os.path.dirname(__file__), "geocodes.json")
ENV_FILE     = os.path.join(os.path.dirname(__file__), ".env")

with open(ENV_FILE) as f:
    for line in f:
        if line.startswith("GOOGLE_MAPS_API_KEY="):
            API_KEY = line.split("=", 1)[1].strip()
            break

# ========== Step 1: 拉 MRT 站列表 ==========
def fetch_mrt_stations():
    """OneMap 搜 'MRT STATION' 返回所有结果（含 EXIT 等重复），按站名去重。"""
    if os.path.exists(OUT_STATIONS):
        with open(OUT_STATIONS) as f:
            stations = json.load(f)
        print(f"已缓存 {len(stations)} 个 MRT 站，跳过抓取")
        return stations

    print("从 OneMap 抓 MRT 站...")
    seen = {}  # 站名 -> {name, lat, lng, lines}
    page = 1
    while True:
        url = "https://www.onemap.gov.sg/api/common/elastic/search?" + urllib.parse.urlencode({
            "searchVal": "MRT STATION", "returnGeom": "Y", "getAddrDetails": "N", "pageNum": page
        })
        try:
            with urllib.request.urlopen(url, timeout=15) as r:
                d = json.load(r)
        except Exception as e:
            print(f"  page {page} 失败: {e}"); break

        results = d.get("results", [])
        if not results: break

        for r in results:
            sv = r.get("SEARCHVAL", "")
            # 过滤掉 EXIT、ENTRANCE 等出入口
            if any(x in sv for x in ["EXIT", "ENTRANCE", "EXIT/", "/EXIT"]): continue
            # 提取站名（去掉括号里的线路代码）
            name = re.sub(r"\s*\(.*?\)\s*$", "", sv).strip()
            # 提取线路代码（如 NS12 / EW23）
            lines_match = re.search(r"\(([^)]+)\)", sv)
            lines = lines_match.group(1) if lines_match else ""
            if name in seen: continue  # 同名只取第一个
            try:
                seen[name] = {
                    "name": name,
                    "lines": lines,
                    "lat": float(r["LATITUDE"]),
                    "lng": float(r["LONGITUDE"])
                }
            except (KeyError, ValueError): pass

        if page >= d.get("totalNumPages", 1): break
        page += 1
        time.sleep(0.2)  # 节流

    stations = list(seen.values())
    with open(OUT_STATIONS, "w") as f:
        json.dump(stations, f, ensure_ascii=False, indent=1)
    print(f"✅ 共 {len(stations)} 个 MRT 站，存 {OUT_STATIONS}")
    return stations

# ========== Step 2: 直线距离 + 真实步行时间 ==========
def haversine(lat1, lng1, lat2, lng2):
    """返回千米。"""
    R = 6371
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(a))

def walk_matrix(origin, candidates):
    """Google Distance Matrix walking 模式，1 origin × N destinations。"""
    url = "https://maps.googleapis.com/maps/api/distancematrix/json?" + urllib.parse.urlencode({
        "origins": f"{origin['lat']},{origin['lng']}",
        "destinations": "|".join(f"{c['lat']},{c['lng']}" for c in candidates),
        "mode": "walking",
        "key": API_KEY,
    })
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)

# ========== Step 3: 主流程 ==========
def main():
    stations = fetch_mrt_stations()

    with open(GEOCODES) as f:
        geocodes = json.load(f)
    addrs = sorted([a for a, g in geocodes.items() if g and g.get("lat")])
    print(f"待算房源: {len(addrs)} 套")

    cache = {}
    if os.path.exists(OUT_WALK):
        with open(OUT_WALK) as f:
            cache = json.load(f)
        print(f"已缓存 {len(cache)} 套房")

    todo = [a for a in addrs if a not in cache]
    print(f"待算 {len(todo)} 套，预计 {len(todo) * 0.3:.0f} 秒")
    if not todo:
        print("✅ 全部已缓存")
        return

    for i, addr in enumerate(todo, 1):
        g = geocodes[addr]
        # 直线最近的 5 个候选
        cands = sorted(stations, key=lambda s: haversine(g["lat"], g["lng"], s["lat"], s["lng"]))[:5]
        try:
            r = walk_matrix(g, cands)
            if r.get("status") != "OK":
                print(f"[{i}/{len(todo)}] ❌ API: {r.get('status')}"); continue
            els = r["rows"][0]["elements"]
            best = None
            for j, el in enumerate(els):
                if el.get("status") != "OK": continue
                walk_min = round(el["duration"]["value"] / 60)
                walk_dist = el["distance"]["value"]
                if best is None or walk_min < best["min"]:
                    best = {
                        "station": cands[j]["name"],
                        "lines": cands[j]["lines"],
                        "min": walk_min,
                        "dist_m": walk_dist,
                    }
            if best:
                cache[addr] = best
                print(f"[{i}/{len(todo)}] ✅ {addr[:40]:42s} → {best['station'][:25]:27s} 步行 {best['min']}min ({best['dist_m']}m)")
            else:
                cache[addr] = None
                print(f"[{i}/{len(todo)}] ⚠️  {addr[:40]} 无可达 MRT")
        except Exception as e:
            print(f"[{i}/{len(todo)}] ❌ {e}")

        if i % 20 == 0:
            with open(OUT_WALK, "w") as f:
                json.dump(cache, f, ensure_ascii=False, indent=1)

        time.sleep(0.1)

    with open(OUT_WALK, "w") as f:
        json.dump(cache, f, ensure_ascii=False, indent=1)
    print(f"\n✅ 完成，写入 {OUT_WALK}")

if __name__ == "__main__":
    main()
