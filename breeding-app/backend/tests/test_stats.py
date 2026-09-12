"""家系统计口径：株内平均、真实零值、未测/死亡、小区×重复。"""
from .conftest import make_founder, make_mating, make_trial_with_plots


def _obs(client, plot_id, tag, status, value=None, trait="株高cm"):
    body = {"plot_id": plot_id, "plant_tag": tag, "trait": trait, "status": status}
    if value is not None:
        body["value"] = value
    r = client.post("/api/observations", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _setup(env):
    client, _ = env
    a = make_founder(client, "母系")
    b = make_founder(client, "父系")
    e = make_mating(client, type="CROSS", female_code=a["code"],
                    male_code=b["code"], offspring_names=["F1"])
    tid, plots = make_trial_with_plots(client, e["code"])
    return client, tid, plots, e


def test_repeated_measures_are_not_independent_replicates(env):
    client, tid, plots, e = _setup(env)
    pa = plots[0]["id"]
    # P1 同株两次测定 10 与 20 ⇒ 株均值 15；P2 测定 30
    _obs(client, pa, "P1", "MEASURED", 10.0)
    _obs(client, pa, "P1", "MEASURED", 20.0)
    _obs(client, pa, "P2", "MEASURED", 30.0)

    stats = client.get(f"/api/stats/trial/{tid}/families",
                       params={"trait": "株高cm"}).json()
    fam = stats["families"][0]
    plot_a = next(p for p in fam["plots"] if p["plot_label"] == "A-1")
    # 株内先平均：(15+30)/2 = 22.5；若误把同株当独立重复则为 (10+20+30)/3 = 20
    assert plot_a["mean"] == 22.5
    assert plot_a["n_plants_measured"] == 2  # 2 株，不是 3 次观测


def test_true_zero_missing_dead_are_distinct(env):
    client, tid, plots, e = _setup(env)
    pa = plots[0]["id"]
    _obs(client, pa, "P1", "MEASURED", 0.0)   # 真实零值
    _obs(client, pa, "P2", "MEASURED", 30.0)
    _obs(client, pa, "P3", "MISSING")         # 未测
    _obs(client, pa, "P4", "DEAD")            # 死亡

    stats = client.get(f"/api/stats/trial/{tid}/families",
                       params={"trait": "株高cm"}).json()
    plot_a = next(p for p in stats["families"][0]["plots"]
                  if p["plot_label"] == "A-1")
    assert plot_a["mean"] == 15.0        # 零值进入均值
    assert plot_a["n_true_zero"] == 1
    assert plot_a["n_missing"] == 1      # 未测不进均值，单独计数
    assert plot_a["n_dead"] == 1         # 死亡不进均值，单独计数
    assert plot_a["n_plants_measured"] == 2


def test_family_mean_uses_plot_by_replicate_caliber(env):
    client, tid, plots, e = _setup(env)
    pa, pb = plots[0]["id"], plots[1]["id"]
    # 小区 A（重复1）：株值 15(10,20), 30, 0 ⇒ 15.0
    _obs(client, pa, "P1", "MEASURED", 10.0)
    _obs(client, pa, "P1", "MEASURED", 20.0)
    _obs(client, pa, "P2", "MEASURED", 30.0)
    _obs(client, pa, "P3", "MEASURED", 0.0)
    _obs(client, pa, "P4", "MISSING")
    _obs(client, pa, "P5", "DEAD")
    # 小区 B（重复2）：40, 50 ⇒ 45.0
    _obs(client, pb, "P1", "MEASURED", 40.0)
    _obs(client, pb, "P2", "MEASURED", 50.0)

    stats = client.get(f"/api/stats/trial/{tid}/families",
                       params={"trait": "株高cm"}).json()
    fam = stats["families"][0]
    assert fam["n_plots"] == 2
    assert fam["n_replicates"] == 2
    # 家系均值 = 小区均值的平均（小区是试验单位，不按株数加权）
    assert fam["mean"] == 30.0
    reps = {r["replicate"]: r["mean"] for r in fam["replicates"]}
    assert reps == {1: 15.0, 2: 45.0}
    assert fam["n_missing"] == 1 and fam["n_dead"] == 1
    assert fam["n_true_zero"] == 1
