#!/usr/bin/env python3
"""一次性地理编码所有 Bespoke 房源地址，结果存到 geocodes.json。
之后只需要重新跑（增量识别新地址，已编码的不重复请求）。
"""
import json, urllib.request, urllib.parse, time, re, os

API_URL = "https://script.google.com/macros/s/AKfycbxZiDMWyA9fkpVOAaXuCczGeZXmpid9EYgKHyRRdecsdpkw8pZIhRZNesq5kcYTV_cT/exec"
OUT = os.path.join(os.path.dirname(__file__), "geocodes.json")

def fetch_properties():
    with urllib.request.urlopen(API_URL, timeout=30) as r:
        return json.load(r)["data"]

def geocode(addr):
    """优先用 postal code，因为新加坡 postal code 6位精确到楼栋。"""
    m = re.search(r"Singapore\s+(\d{6})", addr)
    queries = []
    if m:
        queries.append(m.group(1))
    street_part = addr.split(",")[0].strip()
    queries.append(street_part)

    for q in queries:
        url = "https://www.onemap.gov.sg/api/common/elastic/search?" + urllib.parse.urlencode({
            "searchVal": q, "returnGeom": "Y", "getAddrDetails": "Y", "pageNum": 1
        })
        try:
            with urllib.request.urlopen(url, timeout=10) as r:
                results = json.load(r).get("results", [])
                if results:
                    return {
                        "lat": float(results[0]["LATITUDE"]),
                        "lng": float(results[0]["LONGITUDE"]),
                        "matched": results[0].get("ADDRESS", "")
                    }
        except Exception as e:
            print(f"   warn: {e}")
        time.sleep(0.4)  # 节流，2.5/s
    return None

def main():
    cache = {}
    if os.path.exists(OUT):
        with open(OUT) as f:
            cache = json.load(f)
        print(f"已缓存 {len(cache)} 个地址")

    props = fetch_properties()
    addrs = sorted({p["address"] for p in props if p.get("address")})
    print(f"共 {len(addrs)} 个唯一地址")

    todo = [a for a in addrs if a not in cache]
    print(f"待编码 {len(todo)} 个新地址，预计 {len(todo) * 0.4:.0f} 秒")
    if not todo:
        print("✅ 全部已缓存")
        return

    for i, addr in enumerate(todo, 1):
        result = geocode(addr)
        if result:
            cache[addr] = result
            print(f"[{i}/{len(todo)}] ✅ {addr[:50]:50s} → {result['lat']:.4f},{result['lng']:.4f}")
        else:
            cache[addr] = None  # 标记为编码失败，避免重试
            print(f"[{i}/{len(todo)}] ❌ {addr[:50]}")

        # 每 20 条保存一次，避免中断丢数据
        if i % 20 == 0:
            with open(OUT, "w") as f:
                json.dump(cache, f, ensure_ascii=False, indent=1)

    with open(OUT, "w") as f:
        json.dump(cache, f, ensure_ascii=False, indent=1)

    success = sum(1 for v in cache.values() if v)
    print(f"\n完成：{success}/{len(cache)} 成功，写入 {OUT}")

if __name__ == "__main__":
    main()
