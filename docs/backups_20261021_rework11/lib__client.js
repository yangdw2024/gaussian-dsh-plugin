/* Gaussian DSH Plugin client */
(() => {
  // src/client.js
  window.__ModuleLoader__.load({ id: "gaussian-dsh", factory: (require2) => {
    var module = { exports: {} };
    var exports = module.exports;
    "use strict";
    var import_react = require2("react");
    function backendBase() {
      try {
        if (window.GAUSSIAN_BACKEND_URL) return String(window.GAUSSIAN_BACKEND_URL).replace(/\/$/, "");
      } catch (e) {
      }
      return "http://127.0.0.1:8765";
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
      retry: "\u91CD\u8BD5\u8FDE\u63A5",
      error: "\u9519\u8BEF",
      stopped: "\u5DF2\u505C\u6B62",
      ready: "\u53EF\u7528",
      failed: "\u8FDE\u63A5\u5931\u8D25"
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
      failed: "Failed"
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
            var response = await fetch(backendBase() + "/v1/status", { signal: abort.signal });
            if (!response.ok) throw new Error("HTTP " + response.status);
            setStatus(await response.json());
            setFailure("");
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
      var rows = status ? [
        [t("state"), status.status === "ok" ? t("ready") : t("failed")],
        [t("version"), status.version],
        [t("gaussian_exe"), status.gaussian?.exe],
        [t("gaussian_exists"), status.gaussian?.exists ? "\u2713" : "\u2717"],
        [t("work_dir"), status.work_dir],
        [t("default_mem"), status.default_mem],
        [t("default_nproc"), status.default_nproc],
        [t("sobko_configured"), status.sobko?.configured ? "\u2713" : "\u2717"],
        [t("sobko_mode"), status.sobko?.mode],
        [t("running_job"), status.running_job ? "\u662F" : "\u5426"],
        [t("address"), backendBase()],
        ...status.sobko?.start_error ? [[t("error"), status.sobko.start_error]] : []
      ] : [[t("state"), t("loading")]];
      return (0, import_react.createElement)(
        "section",
        { style: { display: "grid", gap: 12, overflowWrap: "anywhere" } },
        ...rows.map(function(_ref2) {
          var label = _ref2[0];
          var value = _ref2[1];
          return (0, import_react.createElement)(
            "div",
            { key: label },
            (0, import_react.createElement)("strong", null, label + ": "),
            String(value)
          );
        }),
        failure ? (0, import_react.createElement)("p", { role: "alert" }, failure) : null,
        (0, import_react.createElement)("button", {
          type: "button",
          onClick: async function() {
            try {
              var response = await fetch(backendBase() + "/v1/status");
              if (response.ok) setStatus(await response.json());
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
