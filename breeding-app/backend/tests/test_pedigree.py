"""谱系校验：自交/杂交分别建模、环禁止、混合世代、未知父本、同名材料。"""
from app.models import Germplasm

from .conftest import make_founder, make_mating


def test_self_and_cross_are_distinct_models(env):
    client, _ = env
    a = make_founder(client, "甲系")
    b = make_founder(client, "乙系")

    # 自交：父母本必须相同（或父本留空）
    r = client.post("/api/matings", json={
        "type": "SELF", "female_code": a["code"], "male_code": b["code"],
        "offspring_names": ["S1"],
    })
    assert r.status_code == 422

    # 杂交：父母本必须不同
    r = client.post("/api/matings", json={
        "type": "CROSS", "female_code": a["code"], "male_code": a["code"],
        "offspring_names": ["X1"],
    })
    assert r.status_code == 422

    # 合法自交：父本留空 ⇒ 存为父本=母本
    e = make_mating(client, type="SELF", female_code=a["code"],
                    offspring_names=["甲S1"])
    assert e["type"] == "SELF"
    assert e["male"]["code"] == a["code"]

    # 合法杂交
    e = make_mating(client, type="CROSS", female_code=a["code"],
                    male_code=b["code"], offspring_names=["甲×乙F1"])
    assert e["male"]["code"] == b["code"]


def test_descendant_cannot_become_ancestor(env):
    client, _ = env
    a = make_founder(client, "轮回亲本")
    b = make_founder(client, "供体亲本")
    e1 = make_mating(client, type="CROSS", female_code=a["code"],
                     male_code=b["code"], offspring_names=["F1代"])
    f1 = e1["offspring"][0]

    # F1 是 A 的后代：把 A 登记为 F1 的后代 ⇒ 成环，必须拒绝
    r = client.post("/api/matings", json={
        "type": "CROSS", "female_code": f1["code"], "male_code": b["code"],
        "offspring_codes": [a["code"]],
    })
    assert r.status_code == 422
    assert "后代不能成为祖先" in r.json()["detail"]

    # 自己作为自己的亲本
    r = client.post("/api/matings", json={
        "type": "CROSS", "female_code": a["code"], "male_code": b["code"],
        "offspring_codes": [a["code"]],
    })
    assert r.status_code == 422

    # 每个材料至多一个来源事件
    r = client.post("/api/matings", json={
        "type": "CROSS", "female_code": b["code"], "male_code": a["code"],
        "offspring_codes": [f1["code"]],
    })
    assert r.status_code == 422
    assert "已有来源交配事件" in r.json()["detail"]


def test_mixed_generation_cross(env):
    client, _ = env
    low = make_founder(client, "低世代系", generation=0)
    high = make_founder(client, "高世代系", generation=3)

    e = make_mating(client, type="CROSS", female_code=low["code"],
                    male_code=high["code"], offspring_names=["混世代F"])
    # 混合世代：取已知亲本最高世代 + 1
    assert e["offspring"][0]["generation"] == 4


def test_unknown_male_is_not_fabricated(env):
    client, session = env
    a = make_founder(client, "母本系")
    before = session.query(Germplasm).count()

    e = make_mating(client, type="CROSS", female_code=a["code"],
                    male_code=None, offspring_names=["半同胞1"])
    # 父本如实为空，材料库没有多出任何“未知父本”占位材料
    assert e["male"] is None
    after = session.query(Germplasm).count()
    assert after - before == 1  # 只多了后代本身

    child = e["offspring"][0]
    ped = client.get(f"/api/germplasm/{child['code']}/pedigree").json()
    assert [x["code"] for x in ped["ancestors"]] == [a["code"]]

    trace = client.get(f"/api/germplasm/{child['code']}/trace").json()
    assert trace["origin"]["male"] is None
    assert trace["origin"]["female"]["code"] == a["code"]


def test_same_name_distinguished_by_stable_code(env):
    client, _ = env
    x = make_founder(client, "矮秆优系")
    y = make_founder(client, "矮秆优系")
    assert x["code"] != y["code"]

    r = client.get("/api/germplasm", params={"search": "矮秆优系"})
    assert len(r.json()) == 2
    assert {g["code"] for g in r.json()} == {x["code"], y["code"]}
