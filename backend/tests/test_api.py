def test_search_by_code(client):
    resp = client.get("/api/search", params={"q": "600519"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert body["items"][0]["end_date"] == "2026-06-30"
    assert body["items"][0]["change"] == 50000
    assert body["items"][1]["change"] is None


def test_search_by_name_fuzzy(client):
    resp = client.get("/api/search", params={"q": "张三"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert {i["stock_name"] for i in body["items"]} == {"贵州茅台", "五粮液"}


def test_search_pagination(client):
    resp = client.get("/api/search", params={"q": "张三", "page": 2, "page_size": 2})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 1


def test_search_empty_q_rejected(client):
    resp = client.get("/api/search", params={"q": ""})
    assert resp.status_code == 422


def test_search_no_result(client):
    resp = client.get("/api/search", params={"q": "不存在的股东"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["items"] == []


def test_search_page_bounds(client):
    assert client.get("/api/search", params={"q": "张三", "page": 0}).status_code == 422
    assert (
        client.get("/api/search", params={"q": "张三", "page_size": 101}).status_code
        == 422
    )


def test_pv_record_and_query(client):
    before = client.get("/api/pv").json()["total"]
    resp = client.post("/api/pv")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == before + 1
    assert body["today"] >= 1
    assert client.get("/api/pv").json()["total"] == before + 1


def test_login_success(client):
    resp = client.post(
        "/api/auth/login",
        json={"username": "ccfarm", "password": "5800969q"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["username"] == "ccfarm"
    assert body["token"]


def test_login_wrong_password(client):
    resp = client.post(
        "/api/auth/login",
        json={"username": "ccfarm", "password": "wrong"},
    )
    assert resp.status_code == 401


def test_me_with_token(client, auth_headers):
    resp = client.get("/api/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["username"] == "ccfarm"


BAIDU_UA = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; Baiduspider/2.0; "
        "+http://www.baidu.com/search/spider.html)"
    )
}


def test_spa_normal_user_gets_shell(client):
    resp = client.get("/results", params={"q": "张三"})
    assert resp.status_code == 200
    assert '<div id="app">' in resp.text


def test_crawler_home_snapshot(client):
    resp = client.get("/", headers=BAIDU_UA)
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert resp.headers["x-robots-tag"] == "index, follow"
    assert "http://www.cats789.fun/" in resp.text
    assert "股东持股查询" in resp.text
    assert "微盘股筛选" in resp.text
    assert "葛卫东" in resp.text


def test_crawler_results_snapshot_contains_data(client):
    resp = client.get("/results", params={"q": "张三"}, headers=BAIDU_UA)
    assert resp.status_code == 200
    assert resp.headers["x-robots-tag"] == "noindex, follow"
    assert "贵州茅台" in resp.text
    assert "五粮液" in resp.text
    assert "张三" in resp.text
    assert "http://www.cats789.fun/results?q=" in resp.text


def test_crawler_microcap_snapshot(client):
    resp = client.get(
        "/microcap",
        headers={"User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"},
    )
    assert resp.status_code == 200
    assert resp.headers["x-robots-tag"] == "index, follow"
    assert "微盘股筛选" in resp.text
    assert "http://www.cats789.fun/microcap" in resp.text


def test_crawler_login_noindex(client):
    resp = client.get("/login", headers=BAIDU_UA)
    assert resp.status_code == 200
    assert resp.headers["x-robots-tag"] == "noindex, follow"
    assert "登录投资工具箱" in resp.text


def test_logout_invalidates_token(client, auth_headers):
    assert client.post("/api/auth/logout", headers=auth_headers).status_code == 200
    assert client.get("/api/auth/me", headers=auth_headers).status_code == 401
