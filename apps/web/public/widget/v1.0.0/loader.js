(() => {
  "use strict";

  const SDK_VERSION = "1.0.0";
  const GLOBAL_NAME = "MaliyetWidget";
  const WIDGET_SELECTOR = "[data-maliyet-widget]";
  const DEPLOYMENT_ID_PATTERN =
    /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
  const DECIMAL_PATTERN = /^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$/;
  const scriptElement = document.currentScript;
  const scriptApiBase = scriptElement?.dataset?.maliyetApiBase ?? "";
  const mounted = new WeakMap();

  class WidgetError extends Error {
    constructor(code) {
      super(code);
      this.name = "WidgetError";
      this.code = code;
    }
  }

  function canonicalApiBase(rawValue) {
    if (typeof rawValue !== "string" || rawValue.trim() === "") {
      throw new WidgetError("invalid_configuration");
    }

    let parsed;
    try {
      parsed = new URL(rawValue.trim());
    } catch {
      throw new WidgetError("invalid_configuration");
    }

    if (
      parsed.protocol !== "https:" ||
      parsed.username !== "" ||
      parsed.password !== "" ||
      parsed.search !== "" ||
      parsed.hash !== ""
    ) {
      throw new WidgetError("invalid_configuration");
    }

    parsed.pathname = parsed.pathname.replace(/\/+$/, "");
    return parsed.toString().replace(/\/$/, "");
  }

  function deploymentId(rawValue) {
    if (typeof rawValue !== "string" || !DEPLOYMENT_ID_PATTERN.test(rawValue.trim())) {
      throw new WidgetError("invalid_configuration");
    }
    return rawValue.trim().toLowerCase();
  }

  function resolveElement(target) {
    if (typeof target === "string") {
      const element = document.querySelector(target);
      if (element === null) {
        throw new WidgetError("invalid_target");
      }
      return element;
    }
    if (target === null || typeof target !== "object" || target.nodeType !== 1) {
      throw new WidgetError("invalid_target");
    }
    return target;
  }

  function projectionPayload(payload) {
    if (payload === null || typeof payload !== "object" || Array.isArray(payload)) {
      throw new WidgetError("invalid_response");
    }

    const { title, currency, estimate_min: estimateMin, estimate_max: estimateMax } = payload;
    if (
      typeof title !== "string" ||
      title.trim() === "" ||
      title.length > 160 ||
      typeof currency !== "string" ||
      !/^[A-Z]{3}$/.test(currency) ||
      typeof estimateMin !== "string" ||
      estimateMin.length > 64 ||
      !DECIMAL_PATTERN.test(estimateMin) ||
      typeof estimateMax !== "string" ||
      estimateMax.length > 64 ||
      !DECIMAL_PATTERN.test(estimateMax)
    ) {
      throw new WidgetError("invalid_response");
    }

    return Object.freeze({
      title,
      currency,
      estimateMin,
      estimateMax,
    });
  }

  function textNode(tagName, className, value) {
    const node = document.createElement(tagName);
    node.className = className;
    node.textContent = value;
    return node;
  }

  function renderProjection(element, projection) {
    const card = document.createElement("section");
    card.className = "maliyet-widget__card";
    card.setAttribute("aria-live", "polite");

    const title = textNode("h3", "maliyet-widget__title", projection.title);
    const range = textNode(
      "p",
      "maliyet-widget__range",
      `${projection.estimateMin}–${projection.estimateMax} ${projection.currency}`,
    );
    card.replaceChildren(title, range);
    element.replaceChildren(card);
  }

  function renderError(element) {
    const message = textNode(
      "p",
      "maliyet-widget__error",
      "Hesaplama şu anda gösterilemiyor.",
    );
    message.setAttribute("role", "status");
    element.replaceChildren(message);
  }

  function emit(element, eventName, detail) {
    if (typeof CustomEvent === "function" && typeof element.dispatchEvent === "function") {
      element.dispatchEvent(new CustomEvent(eventName, { detail }));
    }
  }

  function responseErrorCode(status) {
    if (status === 403) {
      return "origin_denied";
    }
    if (status === 404) {
      return "not_found";
    }
    if (status === 429) {
      return "quota_exceeded";
    }
    return "request_failed";
  }

  async function mount(target, options = {}) {
    let element;
    try {
      element = resolveElement(target);
    } catch (error) {
      return Object.freeze({
        ok: false,
        code: error instanceof WidgetError ? error.code : "invalid_target",
      });
    }

    const existing = mounted.get(element);
    if (existing !== undefined) {
      return existing;
    }

    const task = (async () => {
      try {
        const publicDeploymentId = deploymentId(
          options.deploymentId ?? element.dataset.deploymentId,
        );
        const apiBase = canonicalApiBase(
          options.apiBase ?? element.dataset.maliyetApiBase ?? scriptApiBase,
        );
        const endpoint = `${apiBase}/organizations/widget/deployments/${encodeURIComponent(publicDeploymentId)}/projection`;

        element.setAttribute("data-maliyet-state", "loading");
        const response = await fetch(endpoint, {
          method: "GET",
          mode: "cors",
          credentials: "omit",
          cache: "no-store",
          redirect: "error",
          referrerPolicy: "no-referrer",
        });
        if (!response.ok) {
          throw new WidgetError(responseErrorCode(response.status));
        }

        const projection = projectionPayload(await response.json());
        renderProjection(element, projection);
        element.setAttribute("data-maliyet-state", "ready");
        emit(element, "maliyet:ready", Object.freeze({ version: SDK_VERSION }));
        return Object.freeze({ ok: true });
      } catch (error) {
        mounted.delete(element);
        const code = error instanceof WidgetError ? error.code : "request_failed";
        element.setAttribute("data-maliyet-state", "error");
        renderError(element);
        emit(element, "maliyet:error", Object.freeze({ code }));
        return Object.freeze({ ok: false, code });
      }
    })();

    mounted.set(element, task);
    return task;
  }

  async function mountAll(root = document) {
    if (root === null || typeof root.querySelectorAll !== "function") {
      return [];
    }
    const elements = Array.from(root.querySelectorAll(WIDGET_SELECTOR));
    return Promise.all(elements.map((element) => mount(element)));
  }

  const sdk = Object.freeze({
    version: SDK_VERSION,
    mount,
    mountAll,
  });

  const existingSdk = window[GLOBAL_NAME];
  if (existingSdk !== undefined) {
    return;
  }

  Object.defineProperty(window, GLOBAL_NAME, {
    value: sdk,
    writable: false,
    configurable: false,
    enumerable: true,
  });

  const autoMount = () => {
    void mountAll();
  };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", autoMount, { once: true });
  } else {
    queueMicrotask(autoMount);
  }
})();
