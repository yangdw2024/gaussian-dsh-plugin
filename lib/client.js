/* Gaussian DSH Plugin client */
(() => {
  // src/client.js
  window.__ModuleLoader__.load({ id: "@gd/gp", factory: (require2) => {
    var module = { exports: {} };
    var exports = module.exports;
    "use strict";
    var import_react = require2("react");
    function stateLabel(state, t) {
      var key = {
        idle: "idle",
        external: "external",
        reused: "reused",
        starting: "starting",
        ready: "ready",
        failed: "failed",
        stopped: "stopped",
        orphan: "orphan"
      }[state];
      return key ? t(key) : state || "\u2014";
    }
    var zh = {
      title: "Gaussian \u8BA1\u7B97\u52A9\u624B",
      description: "\u751F\u6210\u8F93\u5165\u3001\u89E3\u6790\u8F93\u51FA\u3001\u7BA1\u7406\u4EFB\u52A1\u3001\u68C0\u7D22\u77E5\u8BC6\u5E93\u3002",
      loading: "\u6B63\u5728\u8BFB\u53D6\u670D\u52A1\u72B6\u6001\u2026",
      state: "\u670D\u52A1\u72B6\u6001",
      version: "\u7248\u672C",
      gaussian_exe: "Gaussian \u8DEF\u5F84",
      gaussian_exists: "Gaussian \u53EF\u7528",
      work_dir: "\u5DE5\u4F5C\u76EE\u5F55",
      data_dir: "\u6570\u636E\u76EE\u5F55",
      default_mem: "\u9ED8\u8BA4\u5185\u5B58",
      default_nproc: "\u9ED8\u8BA4\u6838\u6570",
      sobko_configured: "Sobko \u77E5\u8BC6\u5E93",
      sobko_running: "Sobko \u8FD0\u884C\u4E2D",
      sobko_mode: "Sobko \u6A21\u5F0F",
      running_job: "\u8FD0\u884C\u4E2D\u4EFB\u52A1",
      address: "\u540E\u7AEF\u5730\u5740",
      log: "\u65E5\u5FD7",
      retry: "\u91CD\u8BD5\u542F\u52A8",
      error: "\u9519\u8BEF",
      stopped: "\u5DF2\u505C\u6B62",
      ready: "\u53EF\u7528",
      failed: "\u542F\u52A8\u5931\u8D25",
      idle: "\u7A7A\u95F2",
      external: "\u5916\u90E8\u5DF2\u63A5\u5165",
      reused: "\u590D\u7528\u5916\u90E8\u540E\u7AEF",
      starting: "\u542F\u52A8\u4E2D",
      orphan: "\u9000\u51FA\u672A\u786E\u8BA4\uFF08\u4FDD\u7559\u6258\u7BA1\uFF09"
    };
    var en = {
      title: "Gaussian Assistant",
      description: "Generate inputs, parse outputs, manage jobs, search knowledge base.",
      loading: "Reading service status\u2026",
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
      orphan: "Orphan (kept managed)"
    };
    var inject = ["slots", "locale"];
    function apply(ctx) {
      var namespace = "gaussian.status";
      var t = ctx.locale.bind(namespace);
      ctx.effect(() => ctx.locale.register(namespace, { zh, en }));
      ctx.effect(() => ctx.slots.inject("plugins.item", () => ctx.slots.register({
        name: "plugins.item",
        id: "gaussian",
        order: 75,
        label: () => t("title"),
        locale: namespace,
        inject: () => ({})
      }, GaussianStatus)));
    }
    function GaussianStatus(_ref) {
      var view = _ref.view;
      var t = _ref.t;
      var _useState = (0, import_react.useState)(void 0);
      var status = _useState[0];
      var setStatus = _useState[1];
      var _useState2 = (0, import_react.useState)("");
      var failure = _useState2[0];
      var setFailure = _useState2[1];
      (0, import_react.useEffect)(() => {
        if (view === "summary") return;
        var abort = new AbortController();
        var refresh = async function() {
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
        var interval = setInterval(() => {
          void refresh();
        }, 3e3);
        return () => {
          abort.abort();
          clearInterval(interval);
        };
      }, [view]);
      if (view === "summary") return t("description");
      var rows;
      if (status) {
        var b = status.backend || null;
        rows = [
          [t("state"), stateLabel(status.state, t)],
          [t("version"), status.version],
          [t("address"), status.baseUrl],
          [t("data_dir"), status.dataDir || b && b.data_dir || "\u2014"]
        ];
        if (b) {
          rows.push([t("gaussian_exe"), b.gaussian && b.gaussian.exe]);
          rows.push([t("gaussian_exists"), b.gaussian && b.gaussian.exists ? "\u2713" : "\u2717"]);
          rows.push([t("work_dir"), b.work_dir]);
          rows.push([t("default_mem"), b.default_mem]);
          rows.push([t("default_nproc"), b.default_nproc]);
          rows.push([t("sobko_configured"), b.sobko && b.sobko.configured ? "\u2713" : "\u2717"]);
          rows.push([t("sobko_mode"), b.sobko && b.sobko.mode]);
          rows.push([t("sobko_running"), b.sobko && b.sobko.running ? "\u2713" : "\u2717"]);
          rows.push([t("running_job"), b.running_job ? "\u662F" : "\u5426"]);
          if (b.sobko && b.sobko.start_error) rows.push([t("error"), b.sobko.start_error]);
        }
        if (status.error) rows.push([t("error"), status.error]);
      } else {
        rows = [[t("state"), t("loading")]];
      }
      return (0, import_react.createElement)(
        "section",
        { style: { display: "grid", gap: 12, overflowWrap: "anywhere" } },
        ...rows.map(function(_ref2) {
          var label = _ref2[0];
          var value = _ref2[1];
          var text = value === null || value === void 0 || value === "" ? "\u2014" : String(value);
          return (0, import_react.createElement)(
            "div",
            { key: label },
            (0, import_react.createElement)("strong", null, label + ": "),
            text
          );
        }),
        failure ? (0, import_react.createElement)("p", { role: "alert" }, failure) : null,
        (0, import_react.createElement)("button", {
          type: "button",
          onClick: async function() {
            try {
              var response = await fetch("/api/gaussian/retry", { method: "POST" });
              if (response.ok) {
                var body = await response.json();
                setStatus(body);
                setFailure(body && body.error ? String(body.error) : "");
              } else {
                setFailure("HTTP " + response.status);
              }
            } catch (e) {
              setFailure(String(e));
            }
          }
        }, t("retry"))
      );
    }
    __export(exports, { apply: () => apply, inject: () => inject });
    function __export(target, all) {
      for (var name in all) Object.defineProperty(target, name, { get: all[name], enumerable: true });
    }
    return module.exports;
  } });
})();
