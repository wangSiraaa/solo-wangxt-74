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
标签丢失观测、观测补录留痕、同株多次测定不作独立重复、真实零值/未测/死亡区分；
亲本修订的证据与确认人、矛盾草案、多支后代与改名后的影响分析、
循环/未知来源阻止（指出路径）、重分组只移动不复制、发布版本保留与人工决定不变。

## 亲本修订工作流（授粉记录纠错）

原交配事件**永不被覆盖**；修订走独立记录：

1. **草案（DRAFT）**：登记 `事件 + 字段(母/父) + 新亲本 + 证据 + 提出人`；
   草案不影响谱系与统计，可查看影响分析（谱系受影响后代 / 家系统计受影响后代分别列出）。
2. **确认（CONFIRMED）**：必须证据非空、确认人 ≠ 提出人；
   存在相互矛盾的草案时双方都不能确认（须先驳回其一）；
   若会造成世代循环或后代来源未知，阻止生效并指出路径（如 `GM-0006 → GM-0008 → GM-0010`）。
3. **生效后**：谱系与家系统计按“现行亲本”重算；同字段旧修订转为 SUPERSEDED（历史保留）。
4. **发布与重算**：已发布结果是不可变版本；修订生效自动形成**待确认的重算**，
   人工批准才成为新发布版本，驳回则旧版本继续有效；
   人工淘汰/保留决定任何自动流程都不得改动。
5. **重分组口径**：家系=现行亲本组合；修订只把对应小区的观测移动到新分组，
   不复制数据、不增加样本量；证据不足的亲本不会成为确定结论。

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

- `POST /api/germplasm` 登记基础材料；`PATCH /api/germplasm/{code}` 改名（编号不变）
- `GET /api/germplasm/{code}/pedigree|trace` 谱系与回溯（含原始/现行亲本与修订留痕）
- `POST /api/matings` 登记交配（可带新后代名称或挂接已有材料编号）
- `POST /api/trials`、`POST /api/trials/{id}/plots` 试验与小区
- `POST /api/observations`、`PATCH /api/observations/{id}` 观测录入与补录
- `GET /api/stats/trial/{id}/families?trait=…` 家系统计（现行亲本分组）
- `POST /api/revisions`、`POST /api/revisions/{code}/confirm|reject` 亲本修订
- `POST /api/trials/{id}/publish`、`GET /api/trials/{id}/publications` 发布版本
- `GET /api/recalc`、`POST /api/recalc/{code}/approve|reject` 待确认重算
- `PUT /api/decisions/{code}`、`GET /api/decisions` 人工淘汰/保留决定

## 目录

```
backend/app/      models.py（数据模型） pedigree.py（NetworkX 校验） stats.py（统计口径）
backend/tests/    pytest 用例
frontend/src/     React 页面（家系筛选 / 材料 / 交配 / 谱系 / 试验小区）
```
