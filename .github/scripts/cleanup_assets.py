#!/usr/bin/env python3
"""
한 달에 한 번 실행:
1) 노션 DB에서 GHAssetID 모으기
2) GitHub Release 자산 전체 목록 추출
3) 노션에 없는 ID 삭제
"""
import os, requests, sys

# ────────── 환경 변수 (GitHub Actions Secrets) ──────────
GH_TOKEN      = os.environ["GH_TOKEN"]          # repo/full PAT
NOTION_TOKEN  = os.environ["NOTION_TOKEN"]
NOTION_DB     = os.environ["NOTION_DB"]        # DB ID
GH_REPO       = os.environ["GH_REPO"]          # owner/repo

HEAD_GH_API = f"https://api.github.com/repos/{GH_REPO}"
HDR_GH      = {"Authorization": f"Bearer {GH_TOKEN}",
               "Accept": "application/vnd.github+json"}
HDR_N       = {"Authorization": f"Bearer {NOTION_TOKEN}",
               "Notion-Version": "2022-06-28",
               "Content-Type": "application/json"}

# ────────── 1. 노션 DB → 유지해야 할 ID 집합 ──────────
# .github/scripts/cleanup_assets.py  ⟶  notion_keep_ids 함수 전체 교체
def notion_keep_ids():
    keep = set()
    url  = f"https://api.notion.com/v1/databases/{NOTION_DB}/query"

    payload = { "page_size": 100 }            # ★ 필터 제거

    while True:
        try:
            res = requests.post(url, headers=HDR_N, json=payload, timeout=30)
            res.raise_for_status()            # ⟵ 예외가 여기서 나면 except 로
        except requests.HTTPError:
            print("── Notion error body ──")   # ★ 반드시 찍힘
            print(res.text)                   #   → 400 메시지 확인
            print("────────────────────")
            raise

        jsn = res.json()

        for pg in jsn["results"]:
            if pg.get("archived") or pg.get("in_trash"):
                continue

            prop = pg["properties"].get("GHID")
            if not prop:
                continue                      # GHID 열 자체가 없음/빈칸

            if prop["type"] == "number" and prop["number"] is not None:
                keep.add(int(prop["number"]))
            elif prop["type"] == "rich_text" and prop["rich_text"]:
                keep.add(id_decode(prop["rich_text"][0]["plain_text"]))

        if jsn.get("has_more"):
            payload["start_cursor"] = jsn["next_cursor"]
        else:
            break

    return keep


# ────────── 2. GitHub → 현재 존재하는 모든 자산 ID ──────────
def github_all_asset_ids():
    asset_ids = set()
    page = 1
    while True:
        rel = requests.get(f"{HEAD_GH_API}/releases?per_page=100&page={page}",
                           headers=HDR_GH, timeout=30)
        rel.raise_for_status()
        releases = rel.json()
        if not releases: break
        for r in releases:
            for a in r.get("assets", []):
                asset_ids.add(a["id"])
        page += 1
    return asset_ids

# ────────── 3. 삭제 실행 ──────────
def delete_asset(asset_id: int):
    r = requests.delete(f"{HEAD_GH_API}/releases/assets/{asset_id}",
                        headers=HDR_GH, timeout=30)
    if r.status_code == 204:
        print("🗑️  Deleted", asset_id)
    elif r.status_code == 404:
        print("⚠️  Already gone", asset_id)
    else:
        print("❌  Fail", asset_id, r.status_code, r.text, file=sys.stderr)

def main():
    keep = notion_keep_ids()
    print("Keep IDs :", len(keep))
    all_ids = github_all_asset_ids()
    print("All IDs  :", len(all_ids))
    garbage = all_ids - keep
    print("To delete:", len(garbage))
    for aid in sorted(garbage):
        delete_asset(aid)

if __name__ == "__main__":
    main()
