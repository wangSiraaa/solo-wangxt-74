"""亲本修订：证据与确认人、影响分析、循环/未知来源阻止、
发布版本保留、待确认重算、人工决定不变、重分组不复制数据。"""
import pytest

from .conftest import make_founder, make_mating, make_trial_with_plots


def _obs(client, plot_id, tag, value, trait="株高cm"):
    r = client.post("/api/observations", json={
        "plot_id": plot_id, "plant_tag": tag, "trait": trait,
        "status": "MEASURED", "value": value})
    assert r.status_code == 201, r.text
    return r.json()


def _draft(client, event_code, field, new_parent_code, evidence="标签照片#1", proposer="李"):
    return client.post("/api/revisions", json={
        "event_code": event_code, "field": field,
        "new_parent_code": new_parent_code,
        "evidence": evidence, "proposer": proposer})


def _confirm(client, code, confirmer="王"):
    return client.post(f"/api/revisions/{code}/confirm", json={"confirmer": confirmer})


@pytest.fixture()
def cross_env(env):
    """E1: F × Mold → O1；另有两个可充当新父本的基础材料。"""
    client, session = env
    f = make_founder(client, "母本F")
    m_old = make_founder(client, "旧父本")
    m_new = make_founder(client, "新父本")
    e1 = make_mating(client, type="CROSS", female_code=f["code"],
                     male_code=m_old["code"], offspring_names=["O1"])
    o1 = e1["offspring"][0]
    return client, session, {"F": f, "Mold": m_old, "Mnew": m_new, "E1": e1, "O1": o1}


# ---------- 证据与确认人 ----------

def test_insufficient_evidence_is_not_confirmed(cross_env):
    client, _, x = cross_env
    r = _draft(client, x["E1"]["code"], "MALE", x["Mnew"]["code"], evidence="")
    assert r.status_code == 201
    code = r.json()["code"]

    r = _confirm(client, code)
    assert r.status_code == 422
    assert "证据不足" in r.json()["detail"]

    # 草案不影响任何结论：谱系与现行亲本仍是旧父本
    ped = client.get(f"/api/germplasm/{x['O1']['code']}/pedigree").json()
    assert x["Mold"]["code"] in [a["code"] for a in ped["ancestors"]]
    assert x["Mnew"]["code"] not in [a["code"] for a in ped["ancestors"]]


def test_confirmer_must_differ_from_proposer(cross_env):
    client, _, x = cross_env
    code = _draft(client, x["E1"]["code"], "MALE", x["Mnew"]["code"]).json()["code"]
    r = _confirm(client, code, confirmer="李")  # 与提出人相同
    assert r.status_code == 422
    assert "确认人不能与提出人相同" in r.json()["detail"]
    r = _confirm(client, code, confirmer="")    # 缺确认人
    assert r.status_code == 422


def test_revision_does_not_overwrite_original_mating(cross_env):
    client, _, x = cross_env
    code = _draft(client, x["E1"]["code"], "MALE", x["Mnew"]["code"]).json()["code"]
    r = _confirm(client, code)
    assert r.status_code == 200, r.text

    # 原交配事实仍在
    event = client.get(f"/api/matings/{x['E1']['code']}").json()
    assert event["male"]["code"] == x["Mold"]["code"]        # 原始记录不变
    assert event["male_effective"]["code"] == x["Mnew"]["code"]  # 现行亲本已更新

    # 回溯同时呈现原始与现行亲本及修订留痕
    trace = client.get(f"/api/germplasm/{x['O1']['code']}/trace").json()
    assert trace["origin"]["male_original"]["code"] == x["Mold"]["code"]
    assert trace["origin"]["male"]["code"] == x["Mnew"]["code"]
    rev = trace["origin"]["revisions"][0]
    assert rev["code"] == code and rev["status"] == "CONFIRMED"
    assert rev["evidence"] and rev["confirmer"] == "王"

    # 谱系按现行亲本
    ped = client.get(f"/api/germplasm/{x['O1']['code']}/pedigree").json()
    anc = [a["code"] for a in ped["ancestors"]]
    assert x["Mnew"]["code"] in anc and x["Mold"]["code"] not in anc


# ---------- 影响分析：多支后代与改名 ----------

def test_impact_lists_pedigree_and_stats_affected_separately(cross_env):
    client, _, x = cross_env
    # 一株材料 O1 分出多支后代：自交一支、杂交一支
    e2 = make_mating(client, type="SELF", female_code=x["O1"]["code"],
                     offspring_names=["支系D1", "支系D2"])
    e3 = make_mating(client, type="CROSS", female_code=x["O1"]["code"],
                     male_code=x["Mnew"]["code"], offspring_names=["支系D3"])
    d1, d2 = e2["offspring"]
    d3 = e3["offspring"][0]

    r = _draft(client, x["E1"]["code"], "MALE", x["Mnew"]["code"])
    impact = r.json()["impact"]
    ped_codes = {g["code"] for g in impact["pedigree_affected"]}
    stats_codes = {g["code"] for g in impact["stats_affected"]}

    # 谱系受影响：O1 及其全部分支后裔
    assert ped_codes == {x["O1"]["code"], d1["code"], d2["code"], d3["code"]}
    # 家系统计受影响：仅直接后代 O1（下游家系的亲本组合未变）
    assert stats_codes == {x["O1"]["code"]}


def test_renamed_descendant_still_tracked_by_code(cross_env):
    client, _, x = cross_env
    e2 = make_mating(client, type="SELF", female_code=x["O1"]["code"],
                     offspring_names=["旧名字D1"])
    d1 = e2["offspring"][0]
    # 部分后代被改名：身份靠编号，不受影响
    r = client.patch(f"/api/germplasm/{d1['code']}", json={"name": "改名后D1"})
    assert r.status_code == 200

    r = _draft(client, x["E1"]["code"], "MALE", x["Mnew"]["code"])
    impact = r.json()["impact"]
    renamed = [g for g in impact["pedigree_affected"] if g["code"] == d1["code"]]
    assert renamed and renamed[0]["name"] == "改名后D1"


# ---------- 矛盾草案 ----------

def test_contradictory_drafts_block_confirmation(cross_env):
    client, _, x = cross_env
    m3 = make_founder(client, "第三父本")
    rv1 = _draft(client, x["E1"]["code"], "MALE", x["Mnew"]["code"]).json()["code"]
    rv2 = _draft(client, x["E1"]["code"], "MALE", m3["code"]).json()["code"]

    # 列表与详情都标注矛盾
    revs = {r["code"]: r for r in client.get("/api/revisions").json()}
    assert revs[rv1]["conflicts_with"] == [rv2]
    assert revs[rv2]["conflicts_with"] == [rv1]

    # 矛盾未解决，双方都不能确认
    r = _confirm(client, rv1)
    assert r.status_code == 409
    assert rv2 in r.json()["detail"]

    # 驳回其一后另一个可确认
    r = client.post(f"/api/revisions/{rv2}/reject", json={"resolver": "王"})
    assert r.status_code == 200
    assert _confirm(client, rv1).status_code == 200

    # 再提矛盾草案并确认 ⇒ 旧修订转为 SUPERSEDED（历史保留）
    rv3 = _draft(client, x["E1"]["code"], "MALE", m3["code"]).json()["code"]
    assert _confirm(client, rv3).status_code == 200
    revs = {r["code"]: r for r in client.get("/api/revisions").json()}
    assert revs[rv1]["status"] == "SUPERSEDED"
    assert revs[rv3]["status"] == "CONFIRMED"


# ---------- 循环与未知来源 ----------

def test_cycle_revision_blocked_with_path(cross_env):
    client, _, x = cross_env
    e2 = make_mating(client, type="SELF", female_code=x["O1"]["code"],
                     offspring_names=["D1"])
    d1 = e2["offspring"][0]
    e3 = make_mating(client, type="SELF", female_code=d1["code"],
                     offspring_names=["D2"])
    d2 = e3["offspring"][0]

    # 把 E1 的父本修订为 O1 的下游后代 D2 ⇒ 世代循环
    rv = _draft(client, x["E1"]["code"], "MALE", d2["code"]).json()["code"]
    detail = client.get(f"/api/revisions/{rv}").json()
    assert detail["blocking_issue"] is not None

    r = _confirm(client, rv)
    assert r.status_code == 422
    msg = r.json()["detail"]
    assert "世代循环" in msg
    # 指出路径：O1 → D1 → D2
    assert f"{x['O1']['code']} → {d1['code']} → {d2['code']}" in msg


def test_unknown_origin_revision_blocked(cross_env):
    client, _, x = cross_env
    # E2: F × 未知父本 → O2
    e2 = make_mating(client, type="CROSS", female_code=x["F"]["code"],
                     male_code=None, offspring_names=["O2"])
    # 把唯一已知亲本（母本）也修订为未知 ⇒ 后代来源未知
    rv = _draft(client, e2["code"], "FEMALE", None).json()["code"]
    r = _confirm(client, rv)
    assert r.status_code == 422
    assert "来源未知" in r.json()["detail"]


# ---------- 发布版本 / 待确认重算 / 人工决定 ----------

@pytest.fixture()
def stats_env(env):
    """E1(F×Mold)→O1 观测[10,20]；E2(F×Mnew)→O2 观测[30]；同试验同重复。"""
    client, session = env
    f = make_founder(client, "母本F")
    m_old = make_founder(client, "旧父本")
    m_new = make_founder(client, "新父本")
    e1 = make_mating(client, type="CROSS", female_code=f["code"],
                     male_code=m_old["code"], offspring_names=["O1"])
    e2 = make_mating(client, type="CROSS", female_code=f["code"],
                     male_code=m_new["code"], offspring_names=["O2"])
    r = client.post("/api/trials", json={"name": "鉴定圃", "season": "2026-春"})
    tid = r.json()["id"]
    plots = {}
    for label, ev in (("P-1", e1), ("P-2", e2)):
        rr = client.post(f"/api/trials/{tid}/plots", json={
            "label": label, "replicate": 1, "family_code": ev["code"]})
        assert rr.status_code == 201, rr.text
        plots[label] = rr.json()["id"]
    _obs(client, plots["P-1"], "A", 10.0)
    _obs(client, plots["P-1"], "B", 20.0)
    _obs(client, plots["P-2"], "A", 30.0)
    return client, session, {
        "F": f, "Mold": m_old, "Mnew": m_new, "E1": e1, "E2": e2, "tid": tid,
        "O1": e1["offspring"][0], "O2": e2["offspring"][0],
    }


def _stats(client, tid):
    return client.get(f"/api/stats/trial/{tid}/families",
                      params={"trait": "株高cm"}).json()


def test_regrouping_moves_observations_without_duplication(stats_env):
    client, _, x = stats_env
    tid = x["tid"]

    before = _stats(client, tid)
    assert len(before["families"]) == 2
    total_before = sum(f["n_plants_measured"] for f in before["families"])
    assert total_before == 3

    # 按旧家系发布 v1
    r = client.post(f"/api/trials/{tid}/publish",
                    json={"trait": "株高cm", "published_by": "王"})
    assert r.status_code == 201 and r.json()["version"] == 1

    # 人工决定：O1 保留、O2 淘汰
    client.put(f"/api/decisions/{x['O1']['code']}",
               json={"decision": "KEPT", "decided_by": "李老师"})
    client.put(f"/api/decisions/{x['O2']['code']}",
               json={"decision": "CULLED", "decided_by": "李老师"})

    # 修订 E1 父本：旧父本 → 新父本（与 E2 同组合）
    rv = _draft(client, x["E1"]["code"], "MALE", x["Mnew"]["code"]).json()["code"]
    r = _confirm(client, rv)
    assert r.status_code == 200, r.text
    proposals = r.json()["recalc_proposals"]
    assert len(proposals) == 1  # 新分组形成待确认的重算

    after = _stats(client, tid)
    # 重分组：两个事件合并为一个家系 (F × 新父本)
    assert len(after["families"]) == 1
    fam = after["families"][0]
    assert set(fam["event_codes"]) == {x["E1"]["code"], x["E2"]["code"]}
    # 只移动对应观测，不复制：总样本量不变，均值按小区口径
    total_after = sum(f["n_plants_measured"] for f in after["families"])
    assert total_after == total_before == 3
    assert fam["mean"] == 22.5  # (小区均值15 与 30) / 2

    # 旧发布版本原样保留
    pubs = client.get(f"/api/trials/{tid}/publications",
                      params={"trait": "株高cm"}).json()
    assert [p["version"] for p in pubs] == [1]
    v1 = client.get(f"/api/publications/{pubs[0]['id']}").json()
    assert len(v1["payload"]["families"]) == 2  # 旧分组不变

    # 重算待确认：批准前发布版本不变；批准后形成 v2
    recalc = client.get(f"/api/recalc/{proposals[0]}").json()
    assert recalc["status"] == "PENDING"
    assert len(recalc["payload"]["families"]) == 1
    r = client.post(f"/api/recalc/{proposals[0]}/approve",
                    json={"resolver": "王老师"})
    assert r.status_code == 200
    assert r.json()["publication"]["version"] == 2
    pubs = client.get(f"/api/trials/{tid}/publications",
                      params={"trait": "株高cm"}).json()
    assert [p["version"] for p in pubs] == [1, 2]  # 两版本并存

    # 人工决定不被自动流程改变
    decisions = {d["germplasm_code"]: d["decision"]
                 for d in client.get("/api/decisions").json()}
    assert decisions[x["O1"]["code"]] == "KEPT"
    assert decisions[x["O2"]["code"]] == "CULLED"


def test_recalc_rejection_keeps_old_publication(stats_env):
    client, _, x = stats_env
    tid = x["tid"]
    client.post(f"/api/trials/{tid}/publish",
                json={"trait": "株高cm", "published_by": "王"})
    rv = _draft(client, x["E1"]["code"], "MALE", x["Mnew"]["code"]).json()["code"]
    proposals = _confirm(client, rv).json()["recalc_proposals"]
    r = client.post(f"/api/recalc/{proposals[0]}/reject",
                    json={"resolver": "王老师"})
    assert r.status_code == 200
    pubs = client.get(f"/api/trials/{tid}/publications",
                      params={"trait": "株高cm"}).json()
    assert [p["version"] for p in pubs] == [1]  # 仍只有旧版本
