"""Turn Chinese AI updates and Hugging Face papers into stable RSS feeds."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime, parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


ROOT = Path(__file__).resolve().parent
FEED_DIR = ROOT / "feeds"
UTC = timezone.utc
NOW = datetime.now(UTC)
OFFICIAL_DAYS = 120
HF_DAYS = 45
RADAR_DAYS = 120
PAPERS_DAYS = 14
MAX_ITEMS = 100

QWEN_URL = "https://qwen.ai/research"
QWEN_API = "https://qwen.ai/api/v2/article/retrieval?type=qwen_ai&language=zh-CN"
KIMI_URL = "https://www.kimi.com/en/blog/"
KIMI_PLATFORM_URL = "https://platform.kimi.com/blog"
MINIMAX_URL = "https://www.minimax.io/blog"
ZAI_URL = "https://docs.bigmodel.cn/cn/update/new-releases"
DEEPSEEK_URL = "https://api-docs.deepseek.com/zh-cn/updates/"
TOKENHUB_URL = "https://cloud.tencent.com/document/product/1823/130675"
HF_API = "https://huggingface.co/api/models"
HF_PAPERS_API = "https://huggingface.co/api/daily_papers"
HF_ORGS = ("Qwen", "deepseek-ai", "moonshotai", "MiniMaxAI", "zai-org", "tencent", "XiaomiMiMo")

FEED_INFO = {
    "official": (
        "国产 AI｜重大官方动态",
        "Qwen、Kimi、MiniMax、智谱、DeepSeek、腾讯 HY 的官方发布与重要变更",
        "china-ai-official.xml",
        OFFICIAL_DAYS,
    ),
    "huggingface": (
        "国产 AI｜Hugging Face 新模型",
        "七个官方组织新建的模型仓库；仅按 createdAt 收录",
        "china-ai-huggingface.xml",
        HF_DAYS,
    ),
    "tokenhub": (
        "国产 AI｜TokenHub 模型雷达",
        "腾讯云 TokenHub 新增支持的国产模型",
        "tokenhub-models.xml",
        RADAR_DAYS,
    ),
    "papers": (
        "Hugging Face｜Daily Papers",
        "Hugging Face Daily Papers 每日收录的研究论文",
        "huggingface-daily-papers.xml",
        PAPERS_DAYS,
    ),
}

NEGATIVE = re.compile(
    r"教程|指南|直播|招聘|抽奖|客户案例|获奖|活动预告|限时|特惠|促销|"
    r"tutorial|how to|webinar|hiring|giveaway|customer story|case study|"
    r"coding plan|benchmark(?:ing)? only",
    re.I,
)
POSITIVE = re.compile(
    r"qwen|kimi|moonshot|mini.?max|glm|deepseek|hunyuan|"
    r"\bhy\d|mimo|模型|发布|开源|上线|价格|降价|涨价|"
    r"api|agent|coding|speech|music|image|video|"
    r"multimodal|多模态|上下文|旗舰|技术报告|open.weights|release|"
    r"technical report|mathematical proof",
    re.I,
)
HF_VARIANT = re.compile(
    r"(?:^|[-_./])(?:gguf|awq|gptq|fp8|bf16|fp4|int4|int8|4bit|8bit|"
    r"quant(?:ized)?|demo|benchmark|dataset)(?:$|[-_./])",
    re.I,
)


@dataclass(frozen=True)
class Item:
    guid: str
    title: str
    link: str
    published: datetime
    description: str


def session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.headers.update({
        "User-Agent": "ai-rss/1.0 (+https://github.com; public official pages)",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    })
    return s


def get(s: requests.Session, url: str, **kwargs) -> requests.Response:
    response = s.get(url, timeout=25, **kwargs)
    response.raise_for_status()
    response.encoding = "utf-8"
    return response


def soup(s: requests.Session, url: str) -> BeautifulSoup:
    return BeautifulSoup(get(s, url).text, "html.parser")


def clean(value: str | None, limit: int = 500) -> str:
    value = re.sub(r"\s+", " ", value or "").strip()
    return value[:limit].rstrip()


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        match = re.search(r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})", value)
        if not match:
            match = re.search(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", value)
        if not match:
            return None
        parsed = datetime(*map(int, match.groups()), 12, tzinfo=UTC)
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def make_item(source: str, title: str, link: str, date: str | None,
              description: str = "", key: str | None = None) -> Item | None:
    published = parse_date(date)
    if not published or not title or not link:
        return None
    digest = hashlib.sha256((key or link).encode("utf-8")).hexdigest()[:20]
    return Item(
        guid=f"urn:ai-rss:{source}:{digest}",
        title=f"[{source}] {clean(title, 180)}",
        link=link,
        published=published,
        description=clean(description) or f"{source} 官方更新",
    )


def important(item: Item) -> bool:
    actual_title = re.sub(r"^\[[^]]+\]\s*", "", item.title)
    return not NEGATIVE.search(actual_title) and bool(POSITIVE.search(actual_title))


def qwen(s: requests.Session) -> list[Item]:
    payload = get(s, QWEN_API, headers={"Referer": QWEN_URL}).json()
    data = payload.get("data", {}).get("articles")
    if not isinstance(data, list):
        raise ValueError("Qwen API did not return a list")
    result = []
    for row in data:
        if not isinstance(row, dict) or not row.get("path"):
            continue
        extra = row.get("extra") or {}
        link = "https://qwen.ai/blog?id=" + quote(str(row["path"]), safe="")
        item = make_item("Qwen", row.get("title", ""), link, extra.get("date"),
                         extra.get("description") or extra.get("introduction", ""))
        if item and important(item):
            result.append(item)
    return result


def kimi_research(s: requests.Session) -> list[Item]:
    result = []
    page = soup(s, KIMI_URL)
    for card in page.select(".menu-card"):
        anchor = card.select_one('a[href^="/en/blog/"]')
        title = card.select_one(".card-title")
        date = card.select_one(".card-date")
        if not anchor or not title or not date:
            continue
        link = urljoin(KIMI_URL, anchor["href"])
        item = make_item("Kimi", title.get_text(" ", strip=True), link,
                         date.get_text(" ", strip=True))
        if item and important(item):
            result.append(item)
    return result


def kimi_platform(s: requests.Session) -> list[Item]:
    result = []
    page = soup(s, KIMI_PLATFORM_URL)
    for card in page.select(".post-item"):
        anchor = card.select_one("h3 a[href]")
        date = card.select_one("time[datetime]")
        if not anchor or not date:
            continue
        item = make_item("Kimi", anchor.get_text(" ", strip=True),
                         urljoin(KIMI_PLATFORM_URL, anchor["href"]),
                         date["datetime"])
        if item and important(item):
            result.append(item)
    return result


def minimax(s: requests.Session) -> list[Item]:
    page = soup(s, MINIMAX_URL)
    result = []
    for heading in page.find_all("h3"):
        anchor = heading.find_parent("a", href=True)
        if not anchor or not anchor["href"].startswith("/blog/"):
            continue
        date = re.search(r"20\d{2}-\d{2}-\d{2}", anchor.get_text(" ", strip=True))
        summary = anchor.find("article")
        item = make_item(
            "MiniMax", heading.get_text(" ", strip=True),
            urljoin(MINIMAX_URL, anchor["href"]),
            date.group(0) if date else None,
            summary.get_text(" ", strip=True) if summary else "",
        )
        if item and important(item):
            result.append(item)
    return result


def zai(s: requests.Session) -> list[Item]:
    page = soup(s, ZAI_URL)
    result = []
    for label in page.select('[data-component-part="update-label"]'):
        description = label.parent.select_one('[data-component-part="update-description"]')
        if not description:
            continue
        title = description.get_text(" ", strip=True)
        date = label.get_text(" ", strip=True)
        body = label.parent.parent.get_text(" ", strip=True)
        anchor = label.parent.select_one('a[href^="#"]')
        link = ZAI_URL + (anchor["href"] if anchor else "")
        item = make_item("智谱", title, link, date, body, key=date + title)
        if item and important(item):
            result.append(item)
    return result


def deepseek(s: requests.Session) -> list[Item]:
    page = soup(s, DEEPSEEK_URL)
    main = page.find("main")
    if not main:
        raise ValueError("DeepSeek main content missing")
    current_date = None
    result = []
    for heading in main.find_all(["h2", "h3"]):
        if heading.name == "h2":
            current_date = heading.get_text(" ", strip=True)
            continue
        title = heading.get_text(" ", strip=True).replace("\u200b", "").strip()
        paragraph = heading.find_next_sibling("p")
        description = paragraph.get_text(" ", strip=True) if paragraph else ""
        link = DEEPSEEK_URL + "#" + heading.get("id", "")
        item = make_item("DeepSeek", title, link, current_date, description)
        if item and important(item):
            result.append(item)
    return result


def tokenhub_rows(s: requests.Session) -> list[tuple[str, str, str]]:
    page = soup(s, TOKENHUB_URL)
    result = []
    for row in page.find_all("tr"):
        cells = [cell.get_text(" ", strip=True) for cell in row.find_all("td")]
        if len(cells) < 3 or not parse_date(cells[2]):
            continue
        result.append((cells[0], cells[1], cells[2]))
    if not result:
        raise ValueError("TokenHub product table missing")
    return result


def tokenhub_feeds(s: requests.Session) -> tuple[list[Item], list[Item]]:
    official, radar = [], []
    for kind, description, date in tokenhub_rows(s):
        if not re.search(r"新增.*模型|模型.*新增|模型.*上线", kind + description):
            continue
        key = date + ":" + description
        radar_item = make_item("TokenHub", description, TOKENHUB_URL,
                               date, kind + "：" + description, key=key)
        if radar_item:
            radar.append(radar_item)
        if re.search(r"\bHy\d[\w.-]*|Hunyuan|混元", description, re.I):
            official_item = make_item("腾讯 HY", description, TOKENHUB_URL,
                                      date, kind + "：" + description, key=key)
            if official_item:
                official.append(official_item)
    return official, radar


def huggingface_org(s: requests.Session, org: str) -> list[Item]:
    rows = get(s, HF_API, params={
        "author": org, "sort": "createdAt", "direction": "-1", "limit": 100,
    }).json()
    if not isinstance(rows, list):
        raise ValueError(f"Hugging Face {org} did not return a list")
    result = []
    for row in rows:
        model_id = row.get("id") or row.get("modelId")
        if not model_id or not model_id.lower().startswith(org.lower() + "/"):
            continue
        name = model_id.split("/", 1)[1]
        if HF_VARIANT.search(name):
            continue
        if org == "tencent" and not re.match(r"(?:Hunyuan|Hy\d|HY[-_])", name, re.I):
            continue
        item = make_item(
            "HF " + org, model_id,
            "https://huggingface.co/" + quote(model_id, safe="/"),
            row.get("createdAt"),
            f"{org} 官方组织新建模型仓库。仅按 createdAt 收录，不把模型卡修改当作新发布。",
        )
        if item:
            result.append(item)
    return result


def huggingface_papers(s: requests.Session) -> list[Item]:
    """Read recent Daily Papers dates; use the Daily submission date, not arXiv's date."""
    result = []
    for offset in range(5):
        date = (NOW - timedelta(days=offset)).date().isoformat()
        rows = get(s, HF_PAPERS_API, params={
            "date": date, "sort": "publishedAt", "limit": 100,
        }).json()
        if not isinstance(rows, list):
            raise ValueError(f"Hugging Face Daily Papers {date} did not return a list")
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("paper"), dict):
                continue
            paper = row["paper"]
            paper_id = paper.get("id")
            if not isinstance(paper_id, str) or not re.fullmatch(r"\d{4}\.\d{4,5}", paper_id):
                continue
            item = make_item(
                "HF Papers", paper.get("title", ""),
                "https://huggingface.co/papers/" + paper_id,
                paper.get("submittedOnDailyAt") or row.get("publishedAt"),
                paper.get("summary", ""), key=paper_id,
            )
            if item:
                result.append(item)
    return result


def read_existing(path: Path) -> list[Item]:
    if not path.exists():
        return []
    result = []
    try:
        root = ET.parse(path).getroot()
        for node in root.findall("./channel/item"):
            raw = node.findtext("pubDate")
            if not raw:
                continue
            published = parsedate_to_datetime(raw).astimezone(UTC)
            guid = node.findtext("guid")
            link = node.findtext("link")
            title = node.findtext("title")
            if guid and link and title:
                result.append(Item(guid, title, link, published,
                                   node.findtext("description") or ""))
    except (ET.ParseError, ValueError) as exc:
        raise ValueError(f"Existing feed is invalid: {path}: {exc}") from exc
    return result


def render_feed(title: str, description: str, items: list[Item]) -> bytes:
    root = ET.Element("rss", version="2.0")
    channel = ET.SubElement(root, "channel")
    ET.SubElement(channel, "title").text = title
    repository = os.getenv("GITHUB_REPOSITORY", "")
    ET.SubElement(channel, "link").text = (
        f"https://github.com/{repository}" if repository else "https://github.com/"
    )
    ET.SubElement(channel, "description").text = description
    ET.SubElement(channel, "language").text = "zh-cn"
    if items:
        ET.SubElement(channel, "lastBuildDate").text = format_datetime(items[0].published)
    for item in items:
        node = ET.SubElement(channel, "item")
        ET.SubElement(node, "title").text = item.title
        ET.SubElement(node, "link").text = item.link
        ET.SubElement(node, "guid", isPermaLink="false").text = item.guid
        ET.SubElement(node, "pubDate").text = format_datetime(item.published)
        ET.SubElement(node, "description").text = item.description
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True) + b"\n"


def write_feed(kind: str, fresh: list[Item]) -> int:
    title, description, filename, days = FEED_INFO[kind]
    path = FEED_DIR / filename
    prior = read_existing(path)
    if kind == "official":
        prior = [item for item in prior if important(item)]
    cutoff = NOW - timedelta(days=days)
    merged = {item.guid: item for item in prior if item.published >= cutoff}
    for item in fresh:
        if cutoff <= item.published <= NOW + timedelta(days=1):
            merged[item.guid] = item
    ordered = sorted(merged.values(), key=lambda item: (-item.published.timestamp(), item.guid))
    ordered = ordered[:MAX_ITEMS]
    if not ordered:
        raise ValueError(f"No usable items for {kind}; refusing to replace feed")
    content = render_feed(title, description, ordered)
    if not path.exists() or path.read_bytes() != content:
        path.write_bytes(content)
    return len(ordered)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, help="Override feed output directory")
    args = parser.parse_args()
    global FEED_DIR
    if args.output_dir:
        FEED_DIR = args.output_dir
    FEED_DIR.mkdir(parents=True, exist_ok=True)

    s = session()
    collected: dict[str, list[Item]] = {kind: [] for kind in FEED_INFO}
    failures = []
    successes = 0

    for name, collector in (
        ("Qwen", qwen), ("Kimi Research", kimi_research),
        ("Kimi Platform", kimi_platform), ("MiniMax", minimax),
        ("智谱", zai), ("DeepSeek", deepseek),
    ):
        try:
            items = collector(s)
            if not items:
                raise ValueError("no articles found")
            collected["official"].extend(items)
            successes += 1
            print(f"{name}: {len(items)} parsed")
        except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError) as exc:
            failures.append(f"{name}: {exc}")

    try:
        official, radar = tokenhub_feeds(s)
        collected["official"].extend(official)
        collected["tokenhub"].extend(radar)
        successes += 1
        print(f"TokenHub: {len(official)} HY, {len(radar)} radar")
    except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError) as exc:
        failures.append(f"TokenHub: {exc}")

    for org in HF_ORGS:
        try:
            items = huggingface_org(s, org)
            collected["huggingface"].extend(items)
            successes += 1
            print(f"HF {org}: {len(items)} parsed")
        except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError) as exc:
            failures.append(f"HF {org}: {exc}")

    try:
        items = huggingface_papers(s)
        if not items:
            raise ValueError("no papers found")
        collected["papers"].extend(items)
        successes += 1
        print(f"HF Daily Papers: {len(items)} parsed")
    except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError) as exc:
        failures.append(f"HF Daily Papers: {exc}")

    if not successes:
        print("All sources failed; existing feeds kept", file=sys.stderr)
        for failure in failures:
            print("WARN " + failure, file=sys.stderr)
        return 1

    for kind, items in collected.items():
        try:
            count = write_feed(kind, items)
            print(f"{kind}: {count} feed entries")
        except ValueError as exc:
            failures.append(str(exc))

    for failure in failures:
        print("WARN " + failure, file=sys.stderr)
    return 0 if all((FEED_DIR / info[2]).exists() for info in FEED_INFO.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
