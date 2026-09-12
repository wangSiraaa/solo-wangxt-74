# 育种谱系与家系筛选（本地应用）

管理亲本组合、世代与家系田间观测的本地应用。**全部数据为虚构植物数据，仅作软件演示，不涉及任何生物实验操作。**

- **React** 前端：材料、交配、谱系、试验小区、家系筛选五个视图，支持来源回溯
- **FastAPI** 后端：用 **NetworkX** 有向图校验亲缘关系（禁止后代成为祖先）
- **PostgreSQL** 存储：材料身份、交配事件、性状观测（本地演示/测试可用 SQLite）

## 快速开始

### 方式一：Docker Compose（PostgreSQL）

```bash
docker compose up --build
# 前端 http://localhost:5173  后端 http://localhost:8000/docs
```

首次启动自动写入虚构演示数据（`SEED_DEMO=1`，可置 0 关闭）。

### 方式二：本地开发（无需 Docker，SQLite 零配置）

```bash
cd backend
pip install -r requirements-dev.txt
DATABASE_URL="sqlite+pysqlite:///./breeding.db" SEED_DEMO=1 \
  python -m uvicorn app.main:app --port 8000

cd ../frontend
npm install && npm run dev   # http://localhost:5173，/api 代理到 8000
```

连接 PostgreSQL 时设 `DATABASE_URL=postgresql+psycopg://user:pass@host:5432/dbname`。

## 测试

```bash
cd backend
python -m pytest tests/ -q
```

覆盖：混合世代交配、谱系成环拒绝、同名材料编号区分、未知父本不伪造、
标签丢失观测、观测补录留痕、同株多次测定不作独立重复、真实零值/未测/死亡区分。

## 核心数据规则

| 规则 | 实现 |
| --- | --- |
| 同名材料 | `name` 不唯一，稳定编号 `GM-0001…` 全局唯一，界面标注同名 |
| 自交 vs 杂交 | `SELF` 父母本相同；`CROSS` 必须不同亲本，父本可未知 |
| 未知亲本 | 存 `NULL`，谱系/回溯显示“未知”，绝不创建占位材料 |
| 禁止成环 | 登记后代前用 NetworkX 检查 `后代→…→亲本` 路径，存在即 422 |
| 混合世代 | 后代世代 = 已知亲本最高世代 + 1 |
| 观测三态 | `MEASURED`（可含真实零值 0.0）/ `MISSING`（未测）/ `DEAD`（死亡），校验数值与状态一致 |
| 标签丢失 | 观测的 `germplasm_id` 可为空；编造不存在编号会被 404 拒绝 |
| 补录留痕 | `MISSING→MEASURED` 置 `backfilled`，任何修改必须填来源；`DEAD` 不可改为已测 |

## 家系统计口径（小区 × 重复）

1. 同株多次测定先在**株内平均**，不作为独立重复；
2. 小区均值 = 小区内已测株的株均值之平均；
3. 家系均值 = 各小区均值之平均（小区是试验单位，不按株数加权），并给出各重复均值；
4. 未测/死亡不进均值，分别计数；真实零值正常参与均值并单独计数。

## 主要 API

- `POST /api/germplasm` 登记基础材料；`GET /api/germplasm/{code}/pedigree|trace` 谱系与回溯
- `POST /api/matings` 登记交配（可带新后代名称或挂接已有材料编号）
- `POST /api/trials`、`POST /api/trials/{id}/plots` 试验与小区
- `POST /api/observations`、`PATCH /api/observations/{id}` 观测录入与补录
- `GET /api/stats/trial/{id}/families?trait=…` 家系统计

## 目录

```
backend/app/      models.py（数据模型） pedigree.py（NetworkX 校验） stats.py（统计口径）
backend/tests/    pytest 用例
frontend/src/     React 页面（家系筛选 / 材料 / 交配 / 谱系 / 试验小区）
```
