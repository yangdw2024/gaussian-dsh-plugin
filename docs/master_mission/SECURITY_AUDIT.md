# 安全审计报告 (SECURITY_AUDIT) — [待 Phase 4 完成]

> 当前状态：`TODO`（将在 Phase 4 逐条审计 `execution_policy.py`、`job_manager.py`、`resource_scheduler.py`、`process_utils.py` 及 21 项安全控制点后完整填入证据与回归测试结果）。

## 计划审计范围（21 项核心条目）
1. 路径遍历与越权读取/写入
2. Windows Junction 与符号链接逃逸
3. TOCTOU 路径竞争与文件覆盖风险
4. 子进程调用安全（Gaussian/formchk/Multiwfn/VMD/OpenBabel/taskkill 参数注入与 `close_fds`）
5. `GAUSSIAN_ALLOW_REAL_EXECUTION` 默认策略与审批重放保护
6. HMAC-SHA256 文件完整性与人工令牌绑定区分
7. Agent 自签令牌禁止替代人工审批
8. HTTP `/v1/*` 绑定本地回环、CORS 与权限边界
9. 跨进程文件锁与调度上限防绕过
10. PID 复用检测与任务状态机防篡改
11. 大日志 OOM/ReDoS 防护与截断策略
12. 后处理 Cube 体积限制、Zip-Slip 及文件名消毒
13. 恶意 SMILES 复杂度与 RDKit/OpenBabel 超时限流
14. Mock 与真实结果强制标识隔离
15. 日志脱敏与无硬编码密钥/个人绝对路径
16. 异常崩溃重启恢复一致性
