# -*- coding: utf-8 -*-
"""히어로 1 + 배너 행 — 계약 §5-1 의 `hero` · `banners[]` 를 조립한다 (Jira 218).

프론트 확정(2026-09-09)
    * 전용 칸(reserved)은 **배너 칸**에 둔다. `banner_slots=6&reserved=2` 면 칸 5·6 이 `new_brand`
    * `hero.banner_type` 은 **항상** 온다 — 프론트가 이미지 변형 5종을 이 값으로 고른다
    * 성분 축 배너는 그 성분이 전성분 **위치가중 ≥ 0.3** 인 상품에만 붙인다 (미량 성분 경고와 충돌 방지)
    * `reason` 은 아이템당 **key 하나**, 우선순위 attribute → content → cf → new_brand → popular

축 값은 어디서 오나 (trait_source)
    session    시드 상품(긍정 가중 상품)에서 가장 많이 나온 값 — concern · ingredient · clean · category · price_bin
    profile    페르소나 속성 — segment (skin_type → skin_tone → eye_color → hair_color 순으로 축에 있는 첫 값)
    coldstart  시드도 속성도 없을 때 — 축에서 상품이 가장 많은 값
    explore    아직 안 쓴다 (프론트 플랜의 무작위 탐색은 서버가 아니라 화면 몫)

배너는 정확도 장치가 아니다 (§5-1). 축은 **후보를 거르는 필터**고 축 안 순위는 추천 점수 그대로다.
`items` 와 `banners` 의 product_id 는 겹치지 않는다. `hero` 만 `items[0]` 과 같을 수 있다.
"""
from __future__ import annotations

import collections
import json
import os

import numpy as np

AXES = ("concern", "ingredient", "clean", "price_bin", "category", "segment")
DEFAULT_AXES = ("concern", "segment")
INGREDIENT_MIN_POSITION = 0.3           # 프론트 요청 — 전성분 앞 30% 안
SEGMENT_ATTRS = ("skin_type", "skin_tone", "eye_color", "hair_color")
REASON_PRIORITY = ("attribute", "content", "cf", "new_brand", "popular")

BD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(BD, "..", ".."))
BANNER_AXES_JSON = os.path.join(ROOT, "batch", "ingest", "data", "serving", "banner_axes.json")


def pick_reason(reasons: dict) -> dict:
    """근거 dict → key 하나만 남긴 dict. 우선순위는 프론트 확정."""
    for k in REASON_PRIORITY:
        if k in reasons:
            return {k: reasons[k]}
    return dict(list(reasons.items())[:1]) if reasons else {"popular": "많은 사용자가 선택한 상품"}


class BannerPlanner:
    """카탈로그의 축 소속을 들고 있다가 사용자마다 hero·banners 를 만든다.

    소속은 상품 기록에서 **직접** 계산한다 (banner_axes.json 의 top-20 목록은 등록 상품이
    없어서). segment 만 lift 산출물이 필요해 banner_axes.json 을 읽는다.
    """

    def __init__(self, enc, products, index, axes_json=BANNER_AXES_JSON):
        self.enc = enc
        self.products = products
        self.index = index
        self.members: dict[str, dict[str, set]] = {a: collections.defaultdict(set) for a in AXES}
        self.attrs_of: list[dict[str, list]] = []          # 행 → {axis: [values]}
        self._segment_from_json(axes_json)
        for p in products:
            self._add(p)

    # ── 소속 ──────────────────────────────────────────────────────────────
    def _segment_from_json(self, path):
        self.segment_values: set[str] = set()
        if not os.path.exists(path):
            return
        d = json.load(open(path, encoding="utf-8"))
        for row in d.get("axes", {}).get("segment", []):
            if row.get("too_thin"):
                continue
            v = row["banner_value"]
            self.segment_values.add(v)
            for g in row.get("product_ids", []):
                if g in self.index:
                    self.members["segment"][v].add(g)

    def product_axes(self, p) -> dict[str, list]:
        """상품 하나의 축 값들 — hero 문구와 소속에 같이 쓴다"""
        e = self.enc
        tg = e.split_tags(p)
        # 위치가중 내림차순 — 전성분 앞에 있는 성분이 첫 값. 어휘집 등재 순서로 두면
        # 앞 30% 안에 히알루론산이 있는 상품은 전부 히알루론산이 문구가 됐다 (프론트 지적 2026-09-10)
        ing = [k for k, w in sorted(e.ingredient_values(p).items(), key=lambda kv: -kv[1])
               if w >= INGREDIENT_MIN_POSITION]
        pb_label = e.price_bin_label(p)          # 원화 경계 (Jira 302)
        pb = [pb_label] if pb_label is not None else []
        cat = [c for c in (p.get("secondary_category"),) if c]
        return {"concern": list(tg["concern"]), "ingredient": ing, "clean": list(tg["clean"]),
                "price_bin": pb, "category": cat}

    def _add(self, p):
        ax = self.product_axes(p)
        self.attrs_of.append(ax)
        for a, vals in ax.items():
            for v in vals:
                self.members[a][v].add(p["product_id"])

    def grow(self, new_products):
        """등록 상품이 붙었을 때 (Jira 216) 소속을 이어 쓴다"""
        for p in new_products:
            self._add(p)

    # ── 축 값 고르기 ──────────────────────────────────────────────────────
    def trait_values(self, seed_rows, persona):
        """축 → (banner_value, trait_source). 시드에서 가장 많은 값, 세그먼트는 프로필."""
        out = {}
        for a in ("concern", "ingredient", "clean", "category", "price_bin"):
            c = collections.Counter(v for i in seed_rows for v in self.attrs_of[i].get(a, []))
            if c:
                out[a] = (c.most_common(1)[0][0], "session")
        if persona:
            for attr in SEGMENT_ATTRS:
                v = persona.get(attr)
                if v in self.segment_values:
                    out["segment"] = (v, "profile")
                    break
        return out

    def coldstart_value(self, axis):
        m = self.members.get(axis) or {}
        if not m:
            return None
        return max(m.items(), key=lambda kv: len(kv[1]))[0]

    # ── 조립 ──────────────────────────────────────────────────────────────
    HERO_AXES_DEFAULT = ("concern", "ingredient", "clean", "category", "price_bin", "segment")
    # 히어로 축 선택 정책의 판. 규칙이 바뀌면 올린다 — 데이터 파트가 banner_daily 를 이 값과 프론트
    # BANNER_POLICY_VERSION 으로 같이 자를 수 있게 (프론트 3-5 합의 2026-09-15, Jira 307).
    #   hero-2026-09-15: axes 순서 우선(304) + axes[0] 트레잇 없으면 상품 자신 값·coldstart(307)
    HERO_POLICY_VERSION = "hero-2026-09-15"
    CONTENT_AXES = ("concern", "ingredient", "clean", "category", "price_bin")

    def _hero(self, product_id, axis, value, source):
        return {"product_id": product_id, "banner_type": axis, "banner_value": value,
                "trait_source": source, "hero_policy_version": self.HERO_POLICY_VERSION}

    def hero_for(self, product_id, traits, axes=()):
        """items[0] 에 축 문구를 얹는다. banner_type 은 항상 있다.

        1. 요청 `axes[0]` (Jira 307, 프론트 3-2 합의): 트레잇이 있고 상품에도 그 값이 있으면 그것(trait_source 는
           트레잇 출처). **트레잇이 없는데 상품에 그 축 값이 있으면 상품 자신의 값을 쓰고 `trait_source=coldstart`** —
           가격 성향 사용자는 항상 가격 문구를 보고, 근거가 세션이 아니란 것이 로그에 남는다. 카탈로그 최빈값은
           히어로 상품과 안 맞을 수 있어 쓰지 않는다. segment 는 상품 속성이 아니라 채우지 않는다.
        2. 그 외: 사용자 축(traits)과 맞는 값을 `axes` 순서로 먼저, 거기 없는 축은 기본 순서
           (concern → ingredient → clean → category → price_bin → segment)로 이어 훑는다 (Jira 304).
        3. 어느 축도 안 맞으면 상품 자신의 값(concern → ingredient → clean → category → price_bin)."""
        ax = self.attrs_of[self.index[product_id]]
        order = [a for a in axes if a in self.HERO_AXES_DEFAULT]
        first = order[0] if order else None
        if first in self.CONTENT_AXES and not traits.get(first) and ax.get(first):
            return self._hero(product_id, first, ax[first][0], "coldstart")
        order += [a for a in self.HERO_AXES_DEFAULT if a not in order]
        for a in order:
            t = traits.get(a)
            if not t:
                continue
            if a == "segment":
                if product_id in self.members["segment"].get(t[0], ()):
                    return self._hero(product_id, "segment", t[0], t[1])
            elif t[0] in ax.get(a, []):
                return self._hero(product_id, a, t[0], t[1])
        for a in self.CONTENT_AXES:
            if ax.get(a):
                return self._hero(product_id, a, ax[a][0], "session")
        return self._hero(product_id, "category",
                          self.products[self.index[product_id]].get("secondary_category"), "session")

    def plan(self, scores, seed_rows, persona, axes, banner_slots, reserved, exclude, is_new):
        """배너 칸 채우기. 앞 (banner_slots - reserved) 칸은 축 순환, 뒤 reserved 칸은 new_brand.

        scores: (상품수,) 점수 — 후보 밖은 -inf. exclude: items 와 전환 상품 (겹치지 않게).
        돌려주는 것: (banners, traits)
        """
        n = len(scores)
        used = set(exclude)
        traits = self.trait_values(seed_rows, persona)
        order = [int(i) for i in np.argsort(-scores) if np.isfinite(scores[i])]
        banners = []

        def take(cands, kind, value, source, flag=False):
            for i in order:
                g = self.products[i]["product_id"]
                if g in used or (cands is not None and g not in cands):
                    continue
                if flag != bool(is_new[i]) and kind == "new_brand":
                    continue
                used.add(g)
                return {"banner_slot": len(banners) + 1, "banner_type": kind, "banner_value": value,
                        "product_id": g, "product_name": self.products[i].get("product_name"),
                        "brand_name": self.products[i].get("brand_name"),
                        "score": round(float(scores[i]), 6), "reserved": flag,
                        "trait_source": source, "_row": i}
            return None

        r = max(0, min(int(reserved), int(banner_slots)))
        n_axis = int(banner_slots) - r
        # 축 칸 — axes 를 순환. 값이 없는 축(시드도 프로필도 없음)은 coldstart 값으로
        k = 0
        guard = 0
        while len(banners) < n_axis and guard < n_axis * len(axes) + 1:
            guard += 1
            a = axes[k % len(axes)]; k += 1
            if a in traits:
                v, src = traits[a]
            else:
                v, src = self.coldstart_value(a), "coldstart"
                if v is None:
                    continue
            b = take(self.members[a].get(v, set()), a, v, src)
            if b:
                banners.append(b)
        # 축이 다 말랐으면 점수순 일반 상품으로 채운다 — 칸은 비지 않는다. 문구는 그 상품의 축
        while len(banners) < n_axis:
            b = take(None, "category", None, "session")
            if b is None:
                break
            ax = self.attrs_of[b["_row"]]
            for a in ("concern", "ingredient", "clean", "category", "price_bin"):
                if ax.get(a):
                    b["banner_type"], b["banner_value"] = a, ax[a][0]
                    break
            banners.append(b)
        # 전용 칸 — 신규 상품 점수순. 신규가 모자라면 일반 상품으로 채우되 reserved=false
        for _ in range(r):
            b = take(None, "new_brand", None, "session", flag=True)
            if b is None:
                b = take(None, "category", None, "session")
                if b is None:
                    break
                ax = self.attrs_of[b["_row"]]
                for a in ("concern", "ingredient", "clean", "category", "price_bin"):
                    if ax.get(a):
                        b["banner_type"], b["banner_value"] = a, ax[a][0]
                        break
            banners.append(b)
        for b in banners:
            b["banner_slot"] = banners.index(b) + 1
        return banners, traits
