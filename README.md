# 农产品残留限量版本与复检裁决

面向农产品检测站复核员，处理采信、判定、核算、复核与归档。

## 启动

```bash
docker compose up --build -d
```

访问 http://localhost:18254 。初次启动自动运行脏样例，可切换 clean.csv 与 legacy.csv。顶部“运行批次”会重新计算，同源输入复用批次。

## 业务模块

- 报告采信：`/m1_ingest`、`/api/m1_ingest`
- 项目映射：`/m2_mapping`、`/api/m2_mapping`
- 限量选版：`/m3_versions`、`/api/m3_versions`
- 检出量换算：`/m4_segments`、`/api/m4_segments`
- 复检裁决：`/m5_calculate`、`/api/m5_calculate`
- 批次判级：`/m6_reconcile`、`/api/m6_reconcile`
- 报告归档：`/m7_archive`、`/api/m7_archive`

## 核心规则

按采样日期选择有效限量，低于检出限保留区间；复检不得越过样本关联与方法适用范围。完整数值、边界和异常定义见 `docs/DATA-DICTIONARY.md`。

## 验证

```bash
docker compose exec -T app pytest -q
docker compose config --quiet
```

原始样例在 `sample_data/`。测试在 `tests/`。封存文件是单份CSV，含运行清单、计算证据、隔离原因与对账。复核需提交当前版本，陈旧复核返回409。

## 证据校验与封存

- 证据内容校验值（`archive.content_sha256`）只覆盖来源原件校验值、规则版本、参数、计算证据、隔离原因与批次对账；`elapsed_ms`、`generated_at` 放在运行清单 `runtime` 区，不参与校验。同一来源重新核验，校验值保持不变，而处理时刻各自留痕。
- 对账未平时封存接口 `POST /api/runs/<id>/seal` 返回 422 并指出未平批次，归档页同步禁用封存与下载；账目相符后方可封存。
- 封存登记后，同批次提交内容校验值不一致的证据返回 409（`EVIDENCE_CHANGED`），已确认证据不被覆盖；封存失败（未平、冲突、批次不存在）不写入任何状态，旧版证据原样保留。封存为幂等操作。

## 数据与限制

SQLite保存在records命名卷，普通重启与构建不会清除。确认可丢弃本项目数据后，运行 `docker compose down -v` 再启动可重置。单文件上限2MB；不接入外部业务系统；历史规则由本项目样例定义，不代表实际行业标准。
