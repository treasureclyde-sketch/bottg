#!/usr/bin/env python3
"""Генерирует static/barbershops.json — топ барбершопов Уфы из 2ГИС.

Запускать изредка, чтобы обновить список. Ключ 2ГИС в браузер не попадает —
он нужен только здесь.

Использование:
    DGIS_KEY=твой_ключ python3 generate_data.py
    # или: python3 generate_data.py твой_ключ

Параметры через env (необязательно):
    DGIS_CITY=Уфа   DGIS_QUERY=барбершоп   LIMIT=80
"""
import json
import math
import os
import ssl
import sys
import urllib.parse
import urllib.request
from pathlib import Path

KEY = os.environ.get("DGIS_KEY") or (sys.argv[1] if len(sys.argv) > 1 else "")
CITY = os.environ.get("DGIS_CITY", "Уфа")
QUERY = os.environ.get("DGIS_QUERY", "барбершоп")
LIMIT = int(os.environ.get("LIMIT", "80"))
OUT = Path(__file__).parent / "static" / "barbershops.json"

if not KEY:
    sys.exit("Нет ключа. Запусти: DGIS_KEY=твой_ключ python3 generate_data.py")

_ca = os.environ.get("CA_BUNDLE") or "/root/.ccr/ca-bundle.crt"
_ctx = ssl.create_default_context(cafile=_ca) if os.path.exists(_ca) else ssl.create_default_context()


def get(url, params):
    full = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(full, headers={"User-Agent": "barber-leads/1.0"})
    with urllib.request.urlopen(req, timeout=30, context=_ctx) as r:
        return json.loads(r.read())


def photo_from(item):
    for ec in item.get("external_content", []) or []:
        for k in ("main_photo_url", "url", "preview_url"):
            if ec.get(k):
                return ec[k]
        for u in (ec.get("preview_urls") or []):
            if u:
                return u
    return ""


def phone_from(item):
    for g in item.get("contact_groups", []) or []:
        for c in g.get("contacts", []) or []:
            if c.get("type") == "phone":
                return c.get("value") or c.get("text") or ""
    return ""


def main():
    reg = get("https://catalog.api.2gis.com/2.0/region/search", {"q": CITY, "key": KEY})
    items = (reg.get("result") or {}).get("items") or []
    if not items:
        sys.exit("Регион не найден в 2ГИС")
    region_id = str(items[0]["id"])
    print("region_id:", region_id)

    fields = "items.point,items.reviews,items.external_content,items.contact_groups,items.address"
    shops = []
    for page in range(1, 13):  # page_size demo-ключа ограничен 10
        res = get("https://catalog.api.2gis.com/3.0/items", {
            "q": QUERY, "region_id": region_id, "fields": fields,
            "page": page, "page_size": 10, "key": KEY,
        })
        page_items = (res.get("result") or {}).get("items") or []
        if not page_items:
            break
        for it in page_items:
            rev = it.get("reviews") or {}
            rating = float(rev.get("general_rating") or 0)
            count = int(rev.get("general_review_count") or 0)
            pt = it.get("point") or {}
            name = it.get("name") or ""
            if not name or rating < 4.0:
                continue
            shops.append({
                "id": "2gis/" + str(it.get("id")),
                "name": name, "rating": rating, "reviews": count,
                "photo": photo_from(it), "address": it.get("address_name") or "",
                "phone": phone_from(it), "lat": pt.get("lat"), "lon": pt.get("lon"),
            })

    # dedup + сортировка: рейтинг * вес отзывов
    seen, uniq = set(), []
    for s in shops:
        if s["id"] in seen:
            continue
        seen.add(s["id"]); uniq.append(s)
    uniq.sort(key=lambda s: s["rating"] * math.log10(s["reviews"] + 10), reverse=True)
    uniq = uniq[:LIMIT]

    OUT.write_text(json.dumps(uniq, ensure_ascii=False, indent=1), encoding="utf-8")
    with_photo = sum(1 for s in uniq if s["photo"])
    print(f"Сохранено {len(uniq)} барбершопов в {OUT} (с фото: {with_photo})")


if __name__ == "__main__":
    main()
