"""
SSAFY Beauty 마스터 컷 2x2 그리드를 상품별 낱장으로 자른다.

왜 이 스크립트가 있나
---------------------
상품 컷(m1·m3)에 누끼가 들어가면서 제품 흰 부분까지 뜯겨 구멍이 났다.
병 몸통과 스포이드 캡에 사각형 자국이 남고, 잘려나간 소품 조각이 옆에
떠 있었다 (SB000002-m1·m3, 2026-09-10 확인).

원본은 이미 흰 배경이라 누끼를 딸 이유가 없다. 그래서 여기서는
**배경을 지우지 않는다.** 하는 일은 셋뿐이다.

  1. 2x2 그리드를 네 칸으로 자른다
  2. 흰 여백을 걷어 제품의 실제 경계를 찾는다
  3. 정사각 흰 캔버스 한가운데에 일정한 여백으로 다시 앉힌다

3번이 "옆에 치우쳐 보이던" 문제를 고친다. 그리드 칸마다 제품이 놓인
위치가 제각각이라, 그냥 4등분만 하면 어떤 상품은 왼쪽에 붙어 나온다.

제형 컷(m2)은 손대지 않는다. 원래 멀쩡하다.

쓰는 법
-------
그리드 원본 4장을 아래 이름으로 scripts/data/master-grid/ 에 둔다.

  grid-a.png  열림·사용 컷 (토닝 패드 / 비타C 세럼 / 핑크 세럼 / 젤리 크림)
  grid-b.png  닫힘 컷      (폼 클렌저 / 선 세럼 / 아이크림 / 겔 마스크)
  grid-c.png  닫힘 컷      (토닝 패드 / 비타C 세럼 / 핑크 세럼 / 젤리 크림)
  grid-d.png  제형 컷      (폼 클렌저 / 선 세럼 / 아이크림 / 겔 마스크)

  python scripts/slice_master_grid.py          # 미리보기만, 파일은 안 쓴다
  python scripts/slice_master_grid.py --write  # public/ 에 실제로 덮어쓴다
"""

import argparse
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(HERE, "data", "master-grid")
OUT_DIR = os.path.join(HERE, "..", "public", "images", "ssafy-beauty")

# 출력 규격. 지금 public/ 에 있는 컷과 같게 맞춘다
CANVAS = 1200
# 제품이 캔버스에서 차지할 최대 비율. 나머지는 사방 여백이 된다
FILL = 0.82
# 이 값보다 밝으면 배경으로 본다. 경계를 찾을 때만 쓰고, 픽셀을 지우지는 않는다
WHITE_CUTOFF = 246

# 그리드 → (칸 순서대로 product_id, 이 그리드가 채우는 슬롯)
# 칸 순서는 좌상 · 우상 · 좌하 · 우하
GRIDS = {
    "grid-a": (["SB000001", "SB000002", "SB000003", "SB000004"], "m3"),
    "grid-b": (["SB000005", "SB000006", "SB000007", "SB000008"], "m1"),
    "grid-c": (["SB000001", "SB000002", "SB000003", "SB000004"], "m1"),
    "grid-d": (["SB000005", "SB000006", "SB000007", "SB000008"], "m3"),
}


def product_box(tile):
    """제품이 실제로 차지하는 사각형. 흰 배경만 걷어낸다."""
    gray = tile.convert("L")
    # 밝은 곳을 0, 제품을 255 로 뒤집어야 getbbox() 가 제품을 잡는다
    mask = gray.point(lambda v: 0 if v >= WHITE_CUTOFF else 255)
    box = mask.getbbox()
    if box is None:
        # 칸이 통째로 비었다. 자르지 말고 그대로 넘긴다
        return (0, 0, tile.width, tile.height)
    return box


def place(tile):
    """제품을 정사각 흰 캔버스 한가운데에 일정한 여백으로 앉힌다."""
    box = product_box(tile)
    cropped = tile.crop(box)

    limit = int(CANVAS * FILL)
    scale = min(limit / cropped.width, limit / cropped.height)
    # 원본보다 키우지 않는다. 없는 해상도를 만들어내면 가장자리가 뭉갠다
    scale = min(scale, 1.0)
    size = (max(1, round(cropped.width * scale)), max(1, round(cropped.height * scale)))
    resized = cropped.resize(size, Image.LANCZOS)

    canvas = Image.new("RGB", (CANVAS, CANVAS), (255, 255, 255))
    canvas.paste(resized, ((CANVAS - size[0]) // 2, (CANVAS - size[1]) // 2))
    return canvas, box


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="public/ 에 실제로 덮어쓴다")
    args = ap.parse_args()

    if not os.path.isdir(SRC_DIR):
        sys.exit(f"원본 폴더가 없습니다: {SRC_DIR}\n그리드 4장을 넣고 다시 실행하세요.")

    planned = []
    for name, (ids, slot) in sorted(GRIDS.items()):
        src = None
        for ext in (".png", ".jpg", ".jpeg", ".webp"):
            candidate = os.path.join(SRC_DIR, name + ext)
            if os.path.isfile(candidate):
                src = candidate
                break
        if src is None:
            print(f"  건너뜀 {name} — 파일 없음")
            continue

        grid = Image.open(src).convert("RGB")
        half_w, half_h = grid.width // 2, grid.height // 2
        quadrants = [
            (0, 0, half_w, half_h),
            (half_w, 0, grid.width, half_h),
            (0, half_h, half_w, grid.height),
            (half_w, half_h, grid.width, grid.height),
        ]

        for product_id, quad in zip(ids, quadrants):
            out, box = place(grid.crop(quad))
            dest = os.path.join(OUT_DIR, f"{product_id}-{slot}.webp")
            planned.append((dest, out))
            print(f"  {os.path.basename(src)} → {product_id}-{slot}.webp  (제품 경계 {box})")

    if not planned:
        sys.exit("자를 그리드를 하나도 못 찾았습니다.")

    if not args.write:
        print(f"\n미리보기입니다. {len(planned)}장을 쓰려면 --write 를 붙이세요.")
        return

    for dest, image in planned:
        image.save(dest, "WEBP", quality=90, method=6)
    print(f"\n{len(planned)}장 저장했습니다. 제형 컷(m2)은 건드리지 않았습니다.")


if __name__ == "__main__":
    main()
