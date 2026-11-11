# 跨 Agent 兼容性矩阵 (COMPATIBILITY_MATRIX) — [待 Phase 5 完成]

| 客户端 / 平台 | 协议 / 接入方式 | 安装状态 | 实机验证状态 | 备注 |
| :--- | :--- | :--- | :--- | :--- |
| DeepSeek Harness (DSH) | Node Plugin + Python Backend (`/v1/*`) | 已检出桌面 Profile 路径 | `TODO (Phase 5)` | 严禁破坏用户现网配置 |
| Codex CLI (`0.148.0`) | MCP Stdio (`backend/mcp_server.py`) | 已安装 (`codex-cli 0.148.0`) | `TODO (Phase 5)` | 使用隔离 `CODEX_HOME` 测试 |
| Claude Code | MCP Stdio (`claude_desktop_config.json` / `.mcp.json`) | `NOT_FOUND` | `NOT_RUN` | 仅提供已校验配置模板 |
| Cursor | MCP Stdio (`.cursor/mcp.json`) | `NOT_FOUND` | `NOT_RUN` | 仅提供已校验配置模板 |
| Agensi Agent Skills | 独立 `SKILL.md` ZIP（无/有 MCP 降级双模式） | 本地打包测试 | `TODO (Phase 7)` | 需符合 Agensi 非托管 MCP 规范 |
