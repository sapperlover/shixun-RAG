# 评测题集（V1.2 附录 D.1）

- `questions_v1.jsonl`：正式冻结题集，**D1 签核前为空**。每行一题，字段见 `backend/app/schemas/resources.py::EvalQuestion`；
  格式示例见 `data/demo/questions_demo.jsonl`（【模拟】演示题，不得放入正式题集）。
- 分布要求：≥10 题；T1（2 跳）≥4、T2（3 跳）≥4；金标准路径必须有原文来源支持，不虚构学分、上限等数值。
- 冻结：`sha256sum questions_v1.jsonl > questions_v1.sha256` 后提交；此后修改题集会让 `make eval` 拒绝运行。
- `negatives.jsonl`：负例（漏年份、关系未核验、无证据、冲突、服务故障等），**单独统计**，不改变三项指标分母。
- `runs/`：评测输出（records.jsonl + summary.json），不进 git。
