# Gaussian MCP Server 客户端配置模板 / Client Configuration Templates

本目录提供常见 AI Agent 客户端的标准 MCP Stdio 接入模板，均不包含任何硬编码密钥或个人路径：

- [`codex_config.toml`](codex_config.toml) — OpenAI Codex CLI（`~/.codex/config.toml` 或隔离 `CODEX_HOME/config.toml`）
- [`claude_desktop_config.json`](claude_desktop_config.json) — Claude Desktop / Claude Code（`claude_desktop_config.json` / `.mcp.json`）
- [`cursor_mcp.json`](cursor_mcp.json) — Cursor（`.cursor/mcp.json`）

## 核心环境变量说明 / Required & Safety Environment Variables

| 变量名 | 默认值 / 示例 | 安全作用 |
| :--- | :--- | :--- |
| `GAUSSIAN_ALLOW_REAL_EXECUTION` | `"false"` | 宿主级总开关；默认禁止真实拉起 `g16.exe` |
| `GAUSSIAN_WORK_DIR` | `<PATH_TO_RESEARCH_WORK_DIR>` | 受控科研工作目录 |
| `GAUSSIAN_ALLOWED_WRITE_ROOTS` | `<PATH_TO_RESEARCH_WORK_DIR>` | 写入白名单（严禁配置为源码根目录或系统盘） |
| `GAUSSIAN_ALLOWED_READ_ROOTS` | `<PATH_TO_RESEARCH_READ_ROOTS>` | 额外只读科研数据目录（支持逗号或分号分隔） |
| `GAUSSIAN_MCP_ENABLE_SOBKO` | `"auto"` | `"auto"` / `"true"` / `"false"` 控制是否注册可选 Sobko 工具 |
