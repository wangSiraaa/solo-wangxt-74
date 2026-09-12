"""观测录入与补录：状态/数值一致性、补录留痕、标签丢失、来源回溯。"""
from .conftest import make_founder, make_mating, make_trial_with_plots


def _setup(env):
    client, _ = env
    a = make_founder(client, "母系")
    b = make_founder(client, "父系")
    e = make_mating(client, type="CROSS", female_code=a["code"],
                    male_code=b["code"], offspring_names=["F1甲"])
    tid, plots = make_trial_with_plots(client, e["code"])
    return client, plots, e


def test_status_value_consistency(env):
    client, plots, _ = _setup(env)
    pid = plots[0]["id"]
    # 已测必须带值
    r = client.post("/api/observations", json={
        "plot_id": pid, "plant_tag": "P1", "trait": "株高cm", "status": "MEASURED"})
    assert r.status_code == 422
    # 未测/死亡不能带值
    for st in ("MISSING", "DEAD"):
        r = client.post("/api/observations", json={
            "plot_id": pid, "plant_tag": "P1", "trait": "株高cm",
            "status": st, "value": 5.0})
        assert r.status_code == 422
    # 真实零值合法
    r = client.post("/api/observations", json={
        "plot_id": pid, "plant_tag": "P1", "trait": "株高cm",
        "status": "MEASURED", "value": 0.0})
    assert r.status_code == 201
    assert r.json()["value"] == 0.0


def test_backfill_missing_to_measured_leaves_provenance(env):
    client, plots, _ = _setup(env)
    pid = plots[0]["id"]
    r = client.post("/api/observations", json={
        "plot_id": pid, "plant_tag": "P9", "trait": "粒重g", "status": "MISSING"})
    obs_id = r.json()["id"]
    assert r.json()["backfilled"] is False

    # 补录必须注明来源
    r = client.patch(f"/api/observations/{obs_id}",
                     json={"status": "MEASURED", "value": 2.5})
    assert r.status_code == 422

    r = client.patch(f"/api/observations/{obs_id}", json={
        "status": "MEASURED", "value": 2.5, "source": "考种补录-赵"})
    assert r.status_code == 200
    body = r.json()
    assert body["backfilled"] is True
    assert body["value"] == 2.5
    assert body["source"] == "考种补录-赵"
    assert body["updated_at"] >= body["created_at"]


def test_dead_and_measured_transitions_are_guarded(env):
    client, plots, _ = _setup(env)
    pid = plots[0]["id"]
    dead = client.post("/api/observations", json={
        "plot_id": pid, "plant_tag": "P1", "trait": "株高cm",
        "status": "DEAD"}).json()
    r = client.patch(f"/api/observations/{dead['id']}", json={
        "status": "MEASURED", "value": 90.0, "source": "误标"})
    assert r.status_code == 422  # 死亡植株不能再有测定值

    measured = client.post("/api/observations", json={
        "plot_id": pid, "plant_tag": "P2", "trait": "株高cm",
        "status": "MEASURED", "value": 88.0}).json()
    r = client.patch(f"/api/observations/{measured['id']}", json={
        "status": "MISSING", "source": "想撤回"})
    assert r.status_code == 422  # 已测不能改回未测

    # 已测 → 已测（更正数值）允许，且留来源
    r = client.patch(f"/api/observations/{measured['id']}", json={
        "status": "MEASURED", "value": 89.5, "source": "复核更正-王"})
    assert r.status_code == 200
    assert r.json()["value"] == 89.5


def test_lost_label_observation_has_no_fabricated_identity(env):
    client, plots, _ = _setup(env)
    pid = plots[0]["id"]
    # 标签丢失：不填材料编号，允许录入，身份如实为空
    r = client.post("/api/observations", json={
        "plot_id": pid, "plant_tag": "P7", "trait": "株高cm",
        "status": "MEASURED", "value": 95.0, "source": "田间记载"})
    assert r.status_code == 201
    assert r.json()["germplasm_code"] is None

    # 编造不存在的编号 ⇒ 拒绝，而不是悄悄接受
    r = client.post("/api/observations", json={
        "plot_id": pid, "plant_tag": "P8", "trait": "株高cm",
        "status": "MEASURED", "value": 90.0, "germplasm_code": "GM-9999"})
    assert r.status_code == 404


def test_offspring_trace_shows_mating_and_observation_provenance(env):
    client, plots, e = _setup(env)
    child = e["offspring"][0]
    pid = plots[0]["id"]
    client.post("/api/observations", json={
        "plot_id": pid, "plant_tag": "P1", "trait": "株高cm",
        "status": "MISSING", "germplasm_code": child["code"]})
    obs = client.get(f"/api/observations/by-plot/{pid}").json()[0]
    client.patch(f"/api/observations/{obs['id']}", json={
        "status": "MEASURED", "value": 101.0, "source": "补录-赵"})

    trace = client.get(f"/api/germplasm/{child['code']}/trace").json()
    # 交配来源
    assert trace["origin"]["event_code"] == e["code"]
    assert trace["origin"]["type"] == "CROSS"
    # 观测来源（含补录留痕）
    rec = trace["observations"][0]
    assert rec["backfilled"] is True
    assert rec["source"] == "补录-赵"
    assert rec["value"] == 101.0
    assert rec["plot_label"] == "A-1"
