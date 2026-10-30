from __future__ import annotations

import argparse
import json
import re
import time
import urllib.parse
import urllib.request
from urllib.error import HTTPError
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


COMMONS_API = "https://commons.wikimedia.org/w/api.php"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
USER_AGENT = "HuashiFaceLibrary/0.1 (local personal reference library)"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


DEFAULT_PEOPLE = [
    ("刘亦菲", "Liu Yifei", "Q242676", "Liu Yifei at the 2016 BAZAAR Stars’ Charity Night.jpg"),
    ("巩俐", "Gong Li", "Q150903", "Gong Li Cannes 2016.jpg"),
    ("章子怡", "Zhang Ziyi", "Q180852", "Zhang Ziyi-63357 (cropped).jpg"),
    ("范冰冰", "Fan Bingbing", "Q381074", "Fan Bingbing-3213 (cropped).jpg"),
    ("陈冲", "Joan Chen", "Q270672", "Joan Chen, 2012 (cropped)a.jpg"),
    ("赵薇", "Zhao Wei", "Q197471", "Zhao Wei.jpg"),
    ("王菲", "Faye Wong", "Q464650", "Faye Wong.jpg"),
    ("汤唯", "Tang Wei", "Q270687", "20250425 Tang Wei 汤唯 03.jpg"),
    ("李冰冰", "Li Bingbing", "Q254166", "Li Bingbing Cannes 2011.jpg"),
    ("白灵", "Bai Ling", "Q464612", "Bai Ling 2007.jpg"),
    ("李玟", "CoCo Lee", "Q703216", "CoCo Lee at Shanghai 2013718 (cropped).jpg"),
    ("迪丽热巴", "Dilraba Dilmurat", "Q18663212", "迪麗熱巴20200802上海腾讯视频推介会 (cropped).jpg"),
    ("周迅", "Zhou Xun", "Q198030", "Zhou Xun (周迅) at the 29th Shanghai Television Festival Magnolia Awards on June 28, 2024.png"),
    ("张梓琳", "Zhang Zilin", "Q197355", "Miss World 2007 - Zhang Zilin (3243539382) (cropped).jpg"),
    ("郑佩佩", "Cheng Pei-pei", "Q269513", "Cheng Pei Pei.jpg"),
    ("张柏芝", "Cecilia Cheung", "Q270681", "Cecilia Cheung 2012.jpg"),
    ("杨幂", "Yang Mi", "Q1137458", "杨幂 ELLE30周年风尚大典 （4）.jpg"),
    ("萨顶顶", "Sa Dingding", "Q257889", "Sa Dingding.jpg"),
    ("邓紫棋", "G.E.M.", "Q665090", "2018.09.22 大连商演 邓紫棋 (1).jpg"),
    ("陈法拉", "Fala Chen", "Q707187", "Fala Chen (2019) 01.png"),
    ("王霏霏", "Fei", "Q3457830", "王霏霏 上海见面会.jpg"),
    ("刘嘉玲", "Carina Lau", "Q706219", "Carina Lau (2023).png"),
    ("高圆圆", "Gao Yuanyuan", "Q702999", "Art Life 2013 1211 IMG 3605.JPG"),
    ("钟欣潼", "Gillian Chung", "Q466493", "GILLIAN CHUNG HK 2019.jpg"),
    ("宋茜", "Victoria Song", "Q340123", "Victoria Song in January 2024.png"),
    ("张靓颖", "Jane Zhang", "Q51169", "Jane Zhang 2014.jpg"),
    ("莫文蔚", "Karen Mok", "Q716027", "Karen Mok (莫文蔚) at the TV show \"The Singing Battle (天籁之战)\" on 31 Oct 2016 (cropped).jpg"),
    ("邬君梅", "Vivian Wu", "Q464754", "邬君梅.jpg"),
    ("赵丽颖", "Zhao Liying", "Q9349416", "Zanilia Zhao from \"The Unseen Sister\" at Red Carpet of the Tokyo International Film Festival 2024 (54577031092).jpg"),
    ("孙俪", "Sun Li", "Q2547121", "Sun Li (孙俪) at the premiere event of the film \"Looking Up\" (银河补习班) in July 2019 (2).png"),
    ("周冬雨", "Zhou Dongyu", "Q1074995", "周冬雨 - 2017微博电影之夜(3) - cropped.jpg"),
    ("陈好", "Chen Hao", "Q271135", "Chen Hao, 2007 (cropped).jpg"),
    ("朱珠", "Zhu Zhu", "Q8264902", "Zhu Zhu, 2012 (cropped).jpg"),
    ("佘诗曼", "Charmaine Sheh", "Q2316321", "Sheh20190611.jpg"),
    ("周洁琼", "Zhou Jieqiong", "Q24833180", "170520 미니 팬미팅 05.jpg"),
    ("白鹿", "Bai Lu", "Q51885061", "Bai Lu.jpg"),
    ("杨紫", "Yang Zi", "Q9080844", "Yang Zi at Ryo band promotion, Wuhan of China, 12 April 2019.jpg"),
    ("景甜", "Jing Tian", "Q7229153", "Jing Tian.jpg"),
    ("张静初", "Zhang Jingchu", "Q470244", "天机富春山居图 (张静初) (cropped).jpg"),
    ("赵露思", "Zhao Lusi", "Q55697066", "ZHAO LUSI (趙露思) P1.jpg"),
    ("程潇", "Cheng Xiao", "Q24959132", "170730 SICAF 폐막식 7.jpg"),
    ("唐嫣", "Tang Yan", "Q7801255", "MJK30544 Tiffany Tang (Berlinale 2017).jpg"),
    ("倪妮", "Ni Ni", "Q3135165", "Nini 2016.9.9 芭莎明星慈善夜 cropped.jpg"),
    ("郑秀文", "Sammi Cheng", "Q701039", "SAMMI CHENG (鄭秀文) - 41ST HONG KONG FILM AWARDS - 2023.04.16.png"),
    ("李沁", "Li Qin", "Q8259870", "Li Qin from \"China Film Week in Tokyo 2019\" at Opening Ceremony of the Tokyo International Film Festival 2019 (49013964087).jpg"),
    ("古力娜扎", "Gülnezer Bextiyar", "Q8259840", "Gülnezer Bextiyar 20190111.jpg"),
    ("柳岩", "Ada Liu", "Q8266679", "Ada Liu and Peng Yu 8 (cropped).jpg"),
    ("梁咏琪", "Gigi Leung", "Q706192", "Gigi Leung 20230401.jpg"),
    ("林忆莲", "Sandy Lam", "Q708766", "Sandy Lam 20240429.jpg"),
    ("李宇春", "Li Yuchun", "Q698103", "Li Yu Chun Chris Lee at her Fans Charity Fund.jpg"),
    ("鞠婧祎", "Ju Jingyi", "Q21017047", "鞠婧祎 (6).jpg"),
    ("关晓彤", "Guan Xiaotong", "Q8962388", "甜甜甜 小鞠太太太太美 晓彤妹子也很漂亮！(关晓彤).jpg"),
    ("姚晨", "Yao Chen", "Q970019", "China 2014 - An Insight, An Idea with Yao Chen.jpg"),
    ("刘诗诗", "Liu Shishi", "Q703714", "Liu ShiShi in 2024 (cropped).jpg"),
    ("虞书欣", "Esther Yu", "Q56259791", "Yu Shuxin - Esther Yu 51243113346.jpg"),
    ("吴宣仪", "Wu Xuanyi", "Q30942487", "Wu Xuanyi.jpg"),
    ("何穗", "Sui He", "Q8965155", "Sui He, 2013 (cropped).jpg"),
    ("徐娇", "Xu Jiao", "Q1003099", "XU JIAO (徐嬌) 2023.png"),
    ("李小璐", "Li Xiaolu", "Q715783", "李小璐.jpg"),
    ("辛芷蕾", "Xin Zhilei", "Q53066688", "Xin Zhilei from \"The Unseen Sister\" at Red Carpet of the Tokyo International Film Festival 2024 (54578121368).jpg"),
    ("吴家丽", "Carrie Ng", "Q701984", "吳家麗.jpg"),
    ("邵美琪", "Maggie Shiu", "Q1372732", "Maggie Shiu.JPG"),
    ("朱茵", "Athena Chu", "Q262468", "Athena Chu.jpg"),
    ("惠英红", "Kara Wai", "Q707211", "SI Twenty-First Annual Made in Hong Kong Film Festival 01.jpg"),
    ("黄圣依", "Eva Huang", "Q708485", "Huang Shengyi.jpg"),
    ("李嘉欣", "Michelle Reis", "Q717070", "Michelle Reis SHISEIDO (3).jpg"),
    ("关之琳", "Rosamund Kwan", "Q714188", "Rosamund Kwan 20181206.png"),
    ("梁洛施", "Isabella Leong", "Q254180", "梁洛施.png"),
    ("孟佳", "Jia", "Q495302", "Miss A Jia at the Korea KPOP World Festival 2013 (cropped).jpg"),
    ("宁艺卓", "Ningning", "Q101161499", "Ningning at Seoul Discovery Expedition event on March 11, 2026 02.jpg"),
    ("韦唯", "Wei Wei", "Q2380538", "Wei Wei Sichuan Earthquake.jpg"),
    ("杨千嬅", "Miriam Yeung", "Q2174226", "Miriam Yeung 20240608.jpg"),
    ("周丽淇", "Niki Chow", "Q464659", "Niki Chow, 2018 (cropped).jpg"),
]


@dataclass(frozen=True)
class FacePhoto:
    person_name: str
    english_name: str
    wikidata_id: str
    file_title: str
    image_url: str
    source_page: str
    width: int
    height: int
    author: str
    license_short_name: str
    license_url: str
    local_file: str = ""


def api_get(url: str, params: dict[str, Any], retries: int = 0) -> dict[str, Any]:
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(f"{url}?{query}", headers={"User-Agent": USER_AGENT})
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code != 429 or attempt >= retries:
                raise
            time.sleep(2.5 * (attempt + 1))
    raise RuntimeError("API request failed")


def download(url: str, destination: Path, retries: int = 3) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                destination.write_bytes(response.read())
                return
        except HTTPError as exc:
            if exc.code != 429 or attempt >= retries:
                raise
            time.sleep(3 * (attempt + 1))


def safe_part(value: str) -> str:
    clean = re.sub(r"[\\/:*?\"<>|#%&{}$!'@+`=]", "_", value.strip())
    clean = re.sub(r"\s+", "_", clean)
    clean = re.sub(r"_+", "_", clean).strip("._")
    return clean or "photo"


def library_filename(photo: FacePhoto, index: int) -> str:
    title = photo.file_title.removeprefix("File:")
    suffix = Path(title).suffix.lower()
    if suffix not in IMAGE_EXTENSIONS:
        suffix = ".jpg"
    stem = safe_part(Path(title).stem)
    name = safe_part(photo.person_name)
    return f"{name}_{index:02d}_{stem}{suffix}"


def write_metadata(root: Path, photos: list[FacePhoto], failures: list[dict[str, str]] | None = None) -> None:
    people: dict[tuple[str, str], dict[str, Any]] = {}
    for photo in photos:
        key = (photo.person_name, photo.wikidata_id)
        people.setdefault(
            key,
            {
                "person_name": photo.person_name,
                "english_name": photo.english_name,
                "wikidata_id": photo.wikidata_id,
                "photos": [],
            },
        )
        people[key]["photos"].append(asdict(photo))
    payload = {
        "source": "Wikidata P18 + Wikimedia Commons imageinfo",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "people": list(people.values()),
        "failures": failures or [],
    }
    root.mkdir(parents=True, exist_ok=True)
    (root / "metadata.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def search_wikidata(chinese_name: str, english_name: str) -> str:
    for language, query in (("zh", chinese_name), ("en", english_name)):
        data = api_get(
            WIKIDATA_API,
            {
                "action": "wbsearchentities",
                "format": "json",
                "language": language,
                "search": query,
                "limit": 5,
            },
        )
        for item in data.get("search", []):
            qid = str(item.get("id") or "")
            label = str(item.get("label") or "")
            description = str(item.get("description") or "").lower()
            if qid and (query.lower() in label.lower() or chinese_name in label or "actress" in description or "singer" in description):
                return qid
    return ""


def wikidata_entity(qid: str) -> dict[str, Any]:
    data = api_get(WIKIDATA_API, {"action": "wbgetentities", "format": "json", "ids": qid, "props": "claims|labels"})
    return data.get("entities", {}).get(qid, {})


def claim_value(entity: dict[str, Any], prop: str) -> str:
    claims = entity.get("claims", {}).get(prop, [])
    for claim in claims:
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(value, str):
            return value
    return ""


def claim_values(entity: dict[str, Any], prop: str) -> list[str]:
    values = []
    claims = entity.get("claims", {}).get(prop, [])
    for claim in claims:
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(value, str):
            values.append(value)
    return values


def commons_file_info(file_title: str) -> dict[str, Any] | None:
    data = api_get(
        COMMONS_API,
        {
            "action": "query",
            "format": "json",
            "titles": file_title if file_title.startswith("File:") else f"File:{file_title}",
            "prop": "imageinfo",
            "iiprop": "url|size|extmetadata",
            "iiurlwidth": 1800,
        },
    )
    pages = data.get("query", {}).get("pages", {})
    for page in pages.values():
        info = (page.get("imageinfo") or [None])[0]
        if isinstance(info, dict):
            return info
    return None


def metadata_value(extmetadata: dict[str, Any], key: str) -> str:
    value = extmetadata.get(key, {}).get("value", "")
    return re.sub(r"<[^>]+>", "", str(value)).strip()


def face_photo_from_file(chinese_name: str, english_name: str, qid: str, file_name: str) -> FacePhoto | None:
    info = commons_file_info(file_name)
    if not info:
        return None
    width = int(info.get("width") or 0)
    height = int(info.get("height") or 0)
    if width < 600 or height < 600:
        return None
    extmetadata = info.get("extmetadata") or {}
    image_url = str(info.get("thumburl") or info.get("url") or "")
    if not image_url:
        return None
    file_title = file_name if file_name.startswith("File:") else f"File:{file_name}"
    return FacePhoto(
        person_name=chinese_name,
        english_name=english_name,
        wikidata_id=qid,
        file_title=file_title,
        image_url=image_url,
        source_page=f"https://commons.wikimedia.org/wiki/{urllib.parse.quote(file_title.replace(' ', '_'))}",
        width=width,
        height=height,
        author=metadata_value(extmetadata, "Artist"),
        license_short_name=metadata_value(extmetadata, "LicenseShortName"),
        license_url=metadata_value(extmetadata, "LicenseUrl"),
    )


def category_file_titles(category: str, limit: int = 30) -> list[str]:
    if not category:
        return []
    title = category if category.startswith("Category:") else f"Category:{category}"
    data = api_get(
        COMMONS_API,
        {
            "action": "query",
            "format": "json",
            "list": "categorymembers",
            "cmtitle": title,
            "cmnamespace": 6,
            "cmlimit": limit,
        },
    )
    return [str(item.get("title") or "") for item in data.get("query", {}).get("categorymembers", []) if item.get("title")]


def search_file_titles(chinese_name: str, english_name: str, limit: int = 20) -> list[str]:
    titles: list[str] = []
    for query in (f'"{english_name}" portrait', f'"{english_name}"', f'"{chinese_name}"'):
        data = api_get(
            COMMONS_API,
            {
                "action": "query",
                "format": "json",
                "generator": "search",
                "gsrsearch": f"{query} filemime:image",
                "gsrnamespace": 6,
                "gsrlimit": limit,
                "prop": "info",
            },
        )
        for page in data.get("query", {}).get("pages", {}).values():
            title = str(page.get("title") or "")
            if title and title not in titles:
                titles.append(title)
    return titles


def ranked_titles(entity: dict[str, Any], chinese_name: str, english_name: str, fallback: bool = True) -> list[str]:
    titles: list[str] = []
    for file_name in claim_values(entity, "P18"):
        title = file_name if file_name.startswith("File:") else f"File:{file_name}"
        if title not in titles:
            titles.append(title)
    if not fallback:
        return titles
    for category in claim_values(entity, "P373"):
        for title in category_file_titles(category):
            if title not in titles:
                titles.append(title)
    for title in search_file_titles(chinese_name, english_name):
        if title not in titles:
            titles.append(title)
    return titles


def title_score(photo: FacePhoto) -> tuple[int, int]:
    title = photo.file_title.lower()
    keywords = ["cropped", "portrait", "headshot", "close", "face", "red carpet", "festival", "awards"]
    keyword_score = sum(1 for keyword in keywords if keyword in title)
    return keyword_score, photo.width * photo.height


def face_photo_for_person(chinese_name: str, english_name: str, qid: str = "", file_title: str = "") -> FacePhoto | None:
    if qid and file_title:
        return face_photo_from_file(chinese_name, english_name, qid, file_title)
    fixed_qid = bool(qid)
    qid = qid or search_wikidata(chinese_name, english_name)
    if not qid:
        return None
    entity = wikidata_entity(qid)
    candidates = [
        photo
        for title in ranked_titles(entity, chinese_name, english_name, fallback=not fixed_qid)[:12]
        if (photo := face_photo_from_file(chinese_name, english_name, qid, title))
    ]
    if not candidates:
        return None
    return sorted(candidates, key=title_score, reverse=True)[0]


def fetch_library(output: Path, limit: int = 30, dry_run: bool = False) -> tuple[list[FacePhoto], list[dict[str, str]]]:
    output.mkdir(parents=True, exist_ok=True)
    photos: list[FacePhoto] = []
    failures: list[dict[str, str]] = []
    for person in DEFAULT_PEOPLE:
        chinese_name, english_name = person[0], person[1]
        qid = person[2] if len(person) > 2 else ""
        file_title = person[3] if len(person) > 3 else ""
        if len(photos) >= limit:
            break
        try:
            photo = face_photo_for_person(chinese_name, english_name, qid, file_title)
        except Exception as exc:  # network APIs are best-effort; record and continue.
            failures.append({"person_name": chinese_name, "english_name": english_name, "reason": str(exc)})
            continue
        if not photo:
            failures.append({"person_name": chinese_name, "english_name": english_name, "reason": "no suitable Wikimedia Commons P18 image"})
            continue
        person_dir = output / safe_part(photo.person_name)
        person_dir.mkdir(parents=True, exist_ok=True)
        filename = library_filename(photo, 1)
        rel_file = f"{person_dir.name}/{filename}"
        destination = output / rel_file
        saved = FacePhoto(**{**asdict(photo), "local_file": rel_file})
        if not dry_run and not destination.exists():
            try:
                download(photo.image_url, destination, retries=0)
            except Exception as exc:
                failures.append({"person_name": chinese_name, "english_name": english_name, "reason": f"download failed: {exc}"})
                continue
        photos.append(saved)
        time.sleep(0.25)
    write_metadata(output, photos, failures)
    return photos, failures


def index_existing_library(output: Path, limit: int = 30) -> tuple[list[FacePhoto], list[dict[str, str]]]:
    photos: list[FacePhoto] = []
    failures: list[dict[str, str]] = []
    for person in DEFAULT_PEOPLE:
        if len({photo.person_name for photo in photos}) >= limit:
            break
        chinese_name, english_name = person[0], person[1]
        qid = person[2] if len(person) > 2 else ""
        file_title = person[3] if len(person) > 3 else ""
        person_dir = output / safe_part(chinese_name)
        files = sorted(
            path
            for path in person_dir.glob("*")
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        )
        if not files:
            failures.append({"person_name": chinese_name, "english_name": english_name, "reason": "not downloaded"})
            continue
        for local in files:
            title = f"File:{file_title}" if file_title else f"File:{local.name}"
            photos.append(
                FacePhoto(
                    person_name=chinese_name,
                    english_name=english_name,
                    wikidata_id=qid,
                    file_title=title,
                    image_url=f"https://commons.wikimedia.org/wiki/Special:Redirect/file/{urllib.parse.quote(file_title or local.name)}?width=1200",
                    source_page=f"https://commons.wikimedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}",
                    width=0,
                    height=0,
                    author="",
                    license_short_name="See Commons file page",
                    license_url="",
                    local_file=f"{person_dir.name}/{local.name}",
                )
            )
    write_metadata(output, photos, failures)
    return photos, failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch a traceable Wikimedia-based celebrity face reference library.")
    parser.add_argument("--output", default="data/faces/中国女明星", help="Output directory for the face library subset.")
    parser.add_argument("--limit", type=int, default=30, help="Maximum number of people to fetch.")
    parser.add_argument("--dry-run", action="store_true", help="Write metadata without downloading images.")
    parser.add_argument("--index-existing", action="store_true", help="Rebuild metadata from already downloaded local files.")
    args = parser.parse_args()
    if args.index_existing:
        photos, failures = index_existing_library(Path(args.output), limit=args.limit)
    else:
        photos, failures = fetch_library(Path(args.output), limit=args.limit, dry_run=args.dry_run)
    print(json.dumps({"saved": len(photos), "failed": len(failures), "output": args.output}, ensure_ascii=False, indent=2))
    return 0 if photos else 1


if __name__ == "__main__":
    raise SystemExit(main())
