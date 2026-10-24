/**
 * Gaussian DSH Plugin — UI 状态页
 *
 * 在 DSH 客户端插件列表中注入 "Gaussian 计算助手" 状态页，
 * 显示后端服务状态、Gaussian 可执行文件、Sobko 知识库、运行中任务等。
 */

window.__ModuleLoader__.load({ id: "@gd/gp", factory: (require) => {
  var module = { exports: {} };
  var exports = module.exports;
  "use strict";

  var import_react = require("react");

  // R15: renderer 不再直连后端端口，只访问 host 同源 /api/gaussian/* 路由。
  function stateLabel(state, t) {
    var key = {
      idle: "idle", external: "external", reused: "reused",
      starting: "starting", ready: "ready", failed: "failed",
      stopped: "stopped", orphan: "orphan",
    }[state];
    return key ? t(key) : (state || "—");
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
    retry: "重试启动",
    error: "错误",
    stopped: "已停止",
    ready: "可用",
    failed: "启动失败",
    idle: "空闲",
    external: "外部已接入",
    reused: "复用外部后端",
    starting: "启动中",
    orphan: "退出未确认（保留托管）",
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
    idle: "Idle",
    external: "External",
    reused: "Reused external",
    starting: "Starting",
    orphan: "Orphan (kept managed)",
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
          var response = await fetch("/api/gaussian/status", { signal: abort.signal });
          if (!response.ok) throw new Error("HTTP " + response.status);
          var body = await response.json();
          setStatus(body);
          setFailure(body && body.error ? String(body.error) : "");
        } catch (error) {
          if (!abort.signal.aborted) setFailure(String(error));
        }
      };
      void refresh();
      var interval = setInterval(() => { void refresh(); }, 3000);
      return () => { abort.abort(); clearInterval(interval); };
    }, [view]);

    if (view === "summary") return t("description");

    var rows;
    if (status) {
      var b = status.backend || null;
      rows = [
        [t("state"), stateLabel(status.state, t)],
        [t("version"), status.version],
        [t("address"), status.baseUrl],
        [t("data_dir"), status.dataDir || (b && b.data_dir) || "—"],
      ];
      if (b) {
        rows.push([t("gaussian_exe"), b.gaussian && b.gaussian.exe]);
        rows.push([t("gaussian_exists"), b.gaussian && b.gaussian.exists ? "✓" : "✗"]);
        rows.push([t("work_dir"), b.work_dir]);
        rows.push([t("default_mem"), b.default_mem]);
        rows.push([t("default_nproc"), b.default_nproc]);
        rows.push([t("sobko_configured"), b.sobko && b.sobko.configured ? "✓" : "✗"]);
        rows.push([t("sobko_mode"), b.sobko && b.sobko.mode]);
        rows.push([t("sobko_running"), b.sobko && b.sobko.running ? "✓" : "✗"]);
        rows.push([t("running_job"), b.running_job ? "是" : "否"]);
        if (b.sobko && b.sobko.start_error) rows.push([t("error"), b.sobko.start_error]);
      }
      if (status.error) rows.push([t("error"), status.error]);
    } else {
      rows = [[t("state"), t("loading")]];
    }

    return (0, import_react.createElement)(
      "section",
      { style: { display: "grid", gap: 12, overflowWrap: "anywhere" } },
      ...rows.map(function (_ref2) {
        var label = _ref2[0];
        var value = _ref2[1];
        var text = (value === null || value === undefined || value === "") ? "—" : String(value);
        return (0, import_react.createElement)("div", { key: label },
          (0, import_react.createElement)("strong", null, label + ": "),
          text
        );
      }),
      failure ? (0, import_react.createElement)("p", { role: "alert" }, failure) : null,
      (0, import_react.createElement)("button", {
        type: "button",
        onClick: async function () {
          try {
            var response = await fetch("/api/gaussian/retry", { method: "POST" });
            if (response.ok) {
              var body = await response.json();
              setStatus(body);
              setFailure(body && body.error ? String(body.error) : "");
            } else {
              setFailure("HTTP " + response.status);
            }
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
