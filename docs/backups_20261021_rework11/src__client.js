/**
 * Gaussian DSH Plugin — UI 状态页
 *
 * 在 DSH 客户端插件列表中注入 "Gaussian 计算助手" 状态页，
 * 显示后端服务状态、Gaussian 可执行文件、Sobko 知识库、运行中任务等。
 */

window.__ModuleLoader__.load({ id: "gaussian-dsh", factory: (require) => {
  var module = { exports: {} };
  var exports = module.exports;
  "use strict";

  var import_react = require("react");

  // m2: 不再把端口写死；优先读取宿主注入的全局配置，回退到本机回环默认。
  // external 模式换端口时可由宿主设置 window.GAUSSIAN_BACKEND_URL。
  function backendBase() {
    try {
      if (window.GAUSSIAN_BACKEND_URL) return String(window.GAUSSIAN_BACKEND_URL).replace(/\/$/, "");
    } catch (e) { /* ignore */ }
    return "http://127.0.0.1:8765";
  }

  var zh = {
    title: "Gaussian 计算助手",
    description: "生成输入、解析输出、管理任务、检索知识库。",
    loading: "正在读取服务状态…",
    state: "服务状态",
    version: "版本",
    gaussian_exe: "Gaussian 路径",
    gaussian_exists: "Gaussian 可用",
    work_dir: "工作目录",
    data_dir: "数据目录",
    default_mem: "默认内存",
    default_nproc: "默认核数",
    sobko_configured: "Sobko 知识库",
    sobko_running: "Sobko 运行中",
    sobko_mode: "Sobko 模式",
    running_job: "运行中任务",
    address: "后端地址",
    log: "日志",
    retry: "重试连接",
    error: "错误",
    stopped: "已停止",
    ready: "可用",
    failed: "连接失败",
  };

  var en = {
    title: "Gaussian Assistant",
    description: "Generate inputs, parse outputs, manage jobs, search knowledge base.",
    loading: "Reading service status…",
    state: "Service state",
    version: "Version",
    gaussian_exe: "Gaussian path",
    gaussian_exists: "Gaussian available",
    work_dir: "Work directory",
    data_dir: "Data directory",
    default_mem: "Default memory",
    default_nproc: "Default cores",
    sobko_configured: "Sobko KB",
    sobko_running: "Sobko running",
    sobko_mode: "Sobko mode",
    running_job: "Running job",
    address: "Backend address",
    log: "Log",
    retry: "Retry",
    error: "Error",
    stopped: "Stopped",
    ready: "Ready",
    failed: "Failed",
  };

  var inject = ["slots", "locale"];

  function apply(ctx) {
    var namespace = "gaussian.status";
    var t = ctx.locale.bind(namespace);
    ctx.effect(() => ctx.locale.register(namespace, { zh: zh, en: en }));
    ctx.effect(() => ctx.slots.inject("plugins.item", () => ctx.slots.register({
      name: "plugins.item",
      id: "gaussian",
      order: 75,
      label: () => t("title"),
      locale: namespace,
      inject: () => ({}),
    }, GaussianStatus)));
  }

  function GaussianStatus(_ref) {
    var view = _ref.view;
    var t = _ref.t;
    var _useState = (0, import_react.useState)(undefined);
    var status = _useState[0];
    var setStatus = _useState[1];
    var _useState2 = (0, import_react.useState)("");
    var failure = _useState2[0];
    var setFailure = _useState2[1];

    (0, import_react.useEffect)(() => {
      if (view === "summary") return;
      var abort = new AbortController();
      var refresh = async function () {
        try {
          var response = await fetch(backendBase() + "/v1/status", { signal: abort.signal });
          if (!response.ok) throw new Error("HTTP " + response.status);
          setStatus(await response.json());
          setFailure("");
        } catch (error) {
          if (!abort.signal.aborted) setFailure(String(error));
        }
      };
      void refresh();
      var interval = setInterval(() => { void refresh(); }, 3000);
      return () => { abort.abort(); clearInterval(interval); };
    }, [view]);

    if (view === "summary") return t("description");

    var rows = status ? [
      [t("state"), status.status === "ok" ? t("ready") : t("failed")],
      [t("version"), status.version],
      [t("gaussian_exe"), status.gaussian?.exe],
      [t("gaussian_exists"), status.gaussian?.exists ? "✓" : "✗"],
      [t("work_dir"), status.work_dir],
      [t("default_mem"), status.default_mem],
      [t("default_nproc"), status.default_nproc],
      [t("sobko_configured"), status.sobko?.configured ? "✓" : "✗"],
      [t("sobko_mode"), status.sobko?.mode],
      [t("running_job"), status.running_job ? "是" : "否"],
      [t("address"), backendBase()],
      ...(status.sobko?.start_error ? [[t("error"), status.sobko.start_error]] : []),
    ] : [[t("state"), t("loading")]];

    return (0, import_react.createElement)(
      "section",
      { style: { display: "grid", gap: 12, overflowWrap: "anywhere" } },
      ...rows.map(function (_ref2) {
        var label = _ref2[0];
        var value = _ref2[1];
        return (0, import_react.createElement)("div", { key: label },
          (0, import_react.createElement)("strong", null, label + ": "),
          String(value)
        );
      }),
      failure ? (0, import_react.createElement)("p", { role: "alert" }, failure) : null,
      (0, import_react.createElement)("button", {
        type: "button",
        onClick: async function () {
          try {
            var response = await fetch(backendBase() + "/v1/status");
            if (response.ok) setStatus(await response.json());
          } catch (e) { setFailure(String(e)); }
        },
      }, t("retry"))
    );
  }

  __export(exports, { apply: () => apply, inject: () => inject });
  function __export(target, all) {
    for (var name in all) Object.defineProperty(target, name, { get: all[name], enumerable: true });
  }

  return module.exports;
}});
