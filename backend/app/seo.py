"""面向搜索引擎爬虫的服务端页面快照（动态渲染）。

前端是 Vue SPA，正文由 JS 渲染，部分搜索引擎（尤其是百度）抓取效果不稳定。
这里对已知爬虫 UA 返回一份与服务端数据一致、可直接索引的静态 HTML，
内容与真实页面来自同一批数据，避免出现"伪装页面"式的差异。
"""

from __future__ import annotations

import html
import math
import re
from urllib.parse import parse_qs, quote

from fastapi import Request
from fastapi.responses import HTMLResponse

from .db import get_microcap_snapshot, search
from .microcap import latest_microcap

SITE_URL = "http://www.cats789.fun"

CRAWLER_UA_RE = re.compile(
    r"baiduspider|googlebot|bingbot|sogou|360spider|yisouspider|bytespider|"
    r"petalbot|yandex|duckduckbot|semrushbot|applebot|facebookexternalhit|"
    r"twitterbot|linkedinbot",
    re.IGNORECASE,
)

HOME_TITLE = "股东查询 - A股十大股东持股记录与变动 | 投资工具箱"
HOME_DESCRIPTION = (
    "输入股东姓名或 A 股代码，免费查询 A 股十大股东持股记录与持仓变动，"
    "覆盖沪深北全市场，数据每日更新。"
)
RESULTS_DESCRIPTION = "查看股东姓名或 A 股代码对应的持股记录与持仓变动，覆盖沪深北全市场，数据每日更新。"
MICROCAP_TITLE = "微盘股筛选 - 总市值最低 30 只 A 股 | 投资工具箱"
MICROCAP_DESCRIPTION = (
    "查看最近交易日总市值最低的 30 只 A 股微盘股名单，排除 ST 及有 ST 风险的股票，"
    "数据每 6 小时更新。"
)


def is_crawler(request: Request) -> bool:
    """按 User-Agent 判断是否为已知搜索引擎爬虫。"""
    return bool(CRAWLER_UA_RE.search(request.headers.get("user-agent", "")))


def _int_param(values: list[str] | None, default: int = 1) -> int:
    try:
        return max(default, int((values or [str(default)])[0]))
    except ValueError:
        return default


def _page(
    title: str,
    description: str,
    canonical: str,
    body: str,
    noindex: bool = False,
) -> HTMLResponse:
    robots = "noindex, follow" if noindex else "index, follow"
    document = f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{html.escape(title)}</title>
    <meta name="description" content="{html.escape(description)}" />
    <meta name="robots" content="{robots}" />
    <link rel="canonical" href="{html.escape(canonical, quote=True)}" />
    <meta property="og:type" content="website" />
    <meta property="og:site_name" content="投资工具箱" />
    <meta property="og:title" content="{html.escape(title)}" />
    <meta property="og:description" content="{html.escape(description)}" />
    <meta property="og:url" content="{html.escape(canonical, quote=True)}" />
    <meta name="twitter:card" content="summary" />
    <meta name="twitter:title" content="{html.escape(title)}" />
    <meta name="twitter:description" content="{html.escape(description)}" />
    <style>
      body {{ font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
             max-width: 960px; margin: 0 auto; padding: 24px; color: #1f2937; line-height: 1.7; }}
      h1, h2 {{ color: #111827; }}
      a {{ color: #4f46e5; text-decoration: none; }}
      table {{ border-collapse: collapse; width: 100%; margin: 16px 0; }}
      th, td {{ border: 1px solid #e5e7eb; padding: 8px 10px; text-align: left; font-size: 14px; }}
      th {{ background: #f3f4f6; }}
      nav, footer {{ color: #6b7280; }}
    </style>
  </head>
  <body>
    <nav>
      <a href="{SITE_URL}/">投资工具箱</a> ·
      <a href="{SITE_URL}/microcap">微盘股筛选</a>
    </nav>
    <main>
      {body}
    </main>
    <footer>投资工具箱 - A股股东持股查询与微盘股筛选</footer>
  </body>
</html>"""
    return HTMLResponse(content=document, headers={"X-Robots-Tag": robots})


def _home_snapshot() -> HTMLResponse:
    keywords = [
        "全国社保基金",
        "高毅",
        "中央汇金",
        "香港中央结算",
        "中国证券金融",
        "招商中证白酒",
        "易方达蓝筹",
        "中欧医疗",
        "谢恺",
        "徐开东",
        "赵建平",
        "葛卫东",
        "章建平",
        "吕强",
        "洪泽君",
    ]
    links = "、".join(
        f'<a href="{SITE_URL}/results?q={quote(k)}">{html.escape(k)}</a>' for k in keywords
    )
    body = f"""
      <h1>股东持股查询</h1>
      <p>{HOME_DESCRIPTION}</p>
      <p>支持按股东姓名（模糊）或 A 股代码精确查询，持股记录按披露时间从新到旧排序，
         并可查看较上期变动（新进 / 增持 / 减持）。</p>
      <p><a href="{SITE_URL}/results">立即查询股东持股</a> ·
         <a href="{SITE_URL}/microcap">微盘股筛选</a></p>
      <h2>热门股东 / 机构查询</h2>
      <p>{links}</p>"""
    return _page(HOME_TITLE, HOME_DESCRIPTION, f"{SITE_URL}/", body)


def _results_snapshot(query_params: dict[str, list[str]]) -> HTMLResponse:
    q = (query_params.get("q") or [""])[0].strip()
    if not q:
        body = f"""
      <h1>股东持股查询结果</h1>
      <p>输入股东姓名或 A 股代码进行查询，例如
         <a href="{SITE_URL}/results?q=600519">600519（贵州茅台）</a>、
         <a href="{SITE_URL}/results?q=全国社保基金">全国社保基金</a>。</p>"""
        return _page(
            "股东持股查询 - 查询结果 | 投资工具箱",
            RESULTS_DESCRIPTION,
            f"{SITE_URL}/results",
            body,
            noindex=True,
        )

    page = _int_param(query_params.get("page"))
    result = search(q, page, 20)
    total = result["total"]
    total_pages = max(1, math.ceil(total / 20))

    if result["items"]:
        rows = "".join(
            "<tr>"
            f"<td>{html.escape(item['stock_code'])}</td>"
            f"<td>{html.escape(item['stock_name'])}</td>"
            f"<td>{html.escape(item['holder_name'])}</td>"
            f"<td>{item['hold_num']:,}</td>"
            f"<td>{html.escape(item['end_date'])}</td>"
            f"<td>{html.escape(item.get('change_text') or '新进')}</td>"
            "</tr>"
            for item in result["items"]
        )
        pager = ""
        if total_pages > 1:
            prev_link = (
                f'<a href="{SITE_URL}/results?q={quote(q)}&amp;page={page - 1}">上一页</a>'
                if page > 1
                else "上一页"
            )
            next_link = (
                f'<a href="{SITE_URL}/results?q={quote(q)}&amp;page={page + 1}">下一页</a>'
                if page < total_pages
                else "下一页"
            )
            pager = f"<p>{prev_link} · 第 {page} / {total_pages} 页 · {next_link}</p>"
        body = f"""
      <h1>「{html.escape(q)}」的 A 股持股记录</h1>
      <p>共 {total} 条持股记录，按披露时间从新到旧排序（第 {page} 页）。</p>
      <table>
        <thead><tr><th>A股代码</th><th>股票名称</th><th>股东名称</th>
        <th>本期持股</th><th>披露时间</th><th>较上期变动</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
      {pager}"""
    else:
        body = f"""
      <h1>「{html.escape(q)}」的 A 股持股记录</h1>
      <p>未找到相关持股记录，请换个股东姓名或 A 股代码试试。</p>
      <p>热门查询：<a href="{SITE_URL}/results?q=全国社保基金">全国社保基金</a>、
         <a href="{SITE_URL}/results?q=中央汇金">中央汇金</a>、
         <a href="{SITE_URL}/results?q=葛卫东">葛卫东</a>。</p>"""

    canonical = f"{SITE_URL}/results?q={quote(q)}"
    title = f"「{q}」股东持股查询 - 投资工具箱"
    description = f"查询「{q}」的 A 股持股记录与持仓变动，覆盖沪深北全市场，数据每日更新。"
    return _page(title, description, canonical, body, noindex=True)


def _microcap_snapshot(query_params: dict[str, list[str]]) -> HTMLResponse:
    date = (query_params.get("date") or [""])[0].strip()
    snap = get_microcap_snapshot(date) if date else latest_microcap()
    canonical = f"{SITE_URL}/microcap" + (f"?date={quote(date)}" if date else "")

    if not snap or not snap.get("items"):
        body = """
      <h1>微盘股筛选</h1>
      <p>还没有微盘股数据，服务每 6 小时自动拉取，请稍后再来查看。</p>"""
    else:
        rows = "".join(
            "<tr>"
            f"<td>{item['rank']}</td>"
            f"<td>{html.escape(item['code'])}</td>"
            f"<td>{html.escape(item['name'])}</td>"
            f"<td>{item['mktcap_yi']:,.2f} 亿</td>"
            "</tr>"
            for item in snap["items"]
        )
        body = f"""
      <h1>微盘股筛选 - 总市值最低 30 只 A 股</h1>
      <p>{snap['trade_date']} 入选的微盘股（总市值最低 30 只，排除 ST 及有 ST 风险的股票）。</p>
      <table>
        <thead><tr><th>排名</th><th>代码</th><th>名称</th><th>总市值</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>"""
    return _page(MICROCAP_TITLE, MICROCAP_DESCRIPTION, canonical, body)


def _login_snapshot() -> HTMLResponse:
    body = "<h1>登录</h1><p>登录投资工具箱后可使用更多功能。</p>"
    return _page("登录 - 投资工具箱", "登录投资工具箱。", f"{SITE_URL}/login", body, noindex=True)


def _generic_snapshot() -> HTMLResponse:
    body = f"""
      <h1>投资工具箱</h1>
      <p>请访问 <a href="{SITE_URL}/">股东查询</a> 或
         <a href="{SITE_URL}/microcap">微盘股筛选</a>。</p>"""
    return _page(HOME_TITLE, HOME_DESCRIPTION, f"{SITE_URL}/", body)


def crawler_snapshot(path: str, request: Request) -> HTMLResponse:
    """根据路径返回对应页面的静态快照。"""
    query_params = parse_qs(request.url.query)
    if not path.startswith("/"):
        path = "/" + path
    if path in ("", "/"):
        return _home_snapshot()
    if path == "/microcap":
        return _microcap_snapshot(query_params)
    if path.startswith("/results"):
        return _results_snapshot(query_params)
    if path == "/login":
        return _login_snapshot()
    return _generic_snapshot()
