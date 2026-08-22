(() => {
  "use strict";

  const SDK_VERSION = "1.2.0";
  const GLOBAL_NAME = "MaliyetWidget";
  const WIDGET_SELECTOR = "[data-maliyet-widget]";
  const DEPLOYMENT_ID_PATTERN =
    /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
  const DECIMAL_PATTERN = /^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$/;
  const HEX_COLOR_PATTERN = /^#[0-9A-F]{6}$/;
  const THEMES = new Set(["auto", "light", "dark"]);
  const LOCALES = new Set(["tr", "en"]);
  const DENSITIES = new Set(["comfortable", "compact"]);
  const FONT_FAMILIES = new Set(["system", "sans", "serif", "monospace"]);
  const FONT_STACKS = Object.freeze({
    system: "ui-sans-serif, system-ui, sans-serif",
    sans: "Arial, Helvetica, sans-serif",
    serif: 'Georgia, "Times New Roman", serif',
    monospace: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
  });
  const ERROR_MESSAGES = Object.freeze({
    tr: "Hesaplama şu anda gösterilemiyor.",
    en: "The calculation cannot be displayed right now.",
  });
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

  function optionalEnumValue(rawValue, allowed) {
    if (rawValue === undefined) return undefined;
    if (typeof rawValue !== "string" || !allowed.has(rawValue)) {
      throw new WidgetError("invalid_configuration");
    }
    return rawValue;
  }

  function optionalBooleanValue(rawValue) {
    if (rawValue === undefined) return undefined;
    if (typeof rawValue === "boolean") return rawValue;
    if (rawValue === "true") return true;
    if (rawValue === "false") return false;
    throw new WidgetError("invalid_configuration");
  }

  function optionValue(options, key, datasetValue) {
    return Object.hasOwn(options, key) ? options[key] : datasetValue;
  }

  function localPresentationPreferences(element, options) {
    if (options === null || typeof options !== "object" || Array.isArray(options)) {
      throw new WidgetError("invalid_configuration");
    }
    return Object.freeze({
      theme: optionalEnumValue(
        optionValue(options, "theme", element.dataset.maliyetTheme),
        THEMES,
      ),
      locale: optionalEnumValue(
        optionValue(options, "locale", element.dataset.maliyetLocale),
        LOCALES,
      ),
      density: optionalEnumValue(
        optionValue(options, "density", element.dataset.maliyetDensity),
        DENSITIES,
      ),
      showTitle: optionalBooleanValue(
        optionValue(options, "showTitle", element.dataset.maliyetShowTitle),
      ),
    });
  }

  function resolvePresentation(local, published) {
    return Object.freeze({
      theme: local.theme ?? published?.theme ?? "auto",
      locale: local.locale ?? published?.locale ?? "tr",
      density: local.density ?? published?.density ?? "comfortable",
      showTitle: local.showTitle ?? published?.showTitle ?? true,
    });
  }

  function resolveElement(target) {
    if (typeof target === "string") {
      const element = document.querySelector(target);
      if (element === null) throw new WidgetError("invalid_target");
      return element;
    }
    if (target === null || typeof target !== "object" || target.nodeType !== 1) {
      throw new WidgetError("invalid_target");
    }
    return target;
  }

  function publishedPresentationPayload(rawValue) {
    if (rawValue === undefined) return null;
    if (rawValue === null || typeof rawValue !== "object" || Array.isArray(rawValue)) {
      throw new WidgetError("invalid_response");
    }

    const {
      theme,
      locale,
      density,
      show_title: showTitle,
      light_background_color: lightBackgroundColor,
      light_text_color: lightTextColor,
      light_border_color: lightBorderColor,
      dark_background_color: darkBackgroundColor,
      dark_text_color: darkTextColor,
      dark_border_color: darkBorderColor,
      error_color: errorColor,
      border_radius_px: borderRadiusPx,
      font_family: fontFamily,
    } = rawValue;

    if (
      typeof theme !== "string" ||
      !THEMES.has(theme) ||
      typeof locale !== "string" ||
      !LOCALES.has(locale) ||
      typeof density !== "string" ||
      !DENSITIES.has(density) ||
      typeof showTitle !== "boolean" ||
      typeof lightBackgroundColor !== "string" ||
      !HEX_COLOR_PATTERN.test(lightBackgroundColor) ||
      typeof lightTextColor !== "string" ||
      !HEX_COLOR_PATTERN.test(lightTextColor) ||
      typeof lightBorderColor !== "string" ||
      !HEX_COLOR_PATTERN.test(lightBorderColor) ||
      typeof darkBackgroundColor !== "string" ||
      !HEX_COLOR_PATTERN.test(darkBackgroundColor) ||
      typeof darkTextColor !== "string" ||
      !HEX_COLOR_PATTERN.test(darkTextColor) ||
      typeof darkBorderColor !== "string" ||
      !HEX_COLOR_PATTERN.test(darkBorderColor) ||
      typeof errorColor !== "string" ||
      !HEX_COLOR_PATTERN.test(errorColor) ||
      !Number.isInteger(borderRadiusPx) ||
      borderRadiusPx < 0 ||
      borderRadiusPx > 32 ||
      typeof fontFamily !== "string" ||
      !FONT_FAMILIES.has(fontFamily)
    ) {
      throw new WidgetError("invalid_response");
    }

    return Object.freeze({
      theme,
      locale,
      density,
      showTitle,
      lightBackgroundColor,
      lightTextColor,
      lightBorderColor,
      darkBackgroundColor,
      darkTextColor,
      darkBorderColor,
      errorColor,
      borderRadiusPx,
      fontFamily,
    });
  }

  function projectionPayload(payload) {
    if (payload === null || typeof payload !== "object" || Array.isArray(payload)) {
      throw new WidgetError("invalid_response");
    }
    const {
      title,
      currency,
      estimate_min: estimateMin,
      estimate_max: estimateMax,
      presentation,
    } = payload;
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
      presentation: publishedPresentationPayload(presentation),
    });
  }

  function applyPublishedBranding(element, published) {
    if (published === null) return;
    if (element.style === undefined || typeof element.style.setProperty !== "function") {
      throw new WidgetError("invalid_target");
    }
    element.style.setProperty("--maliyet-widget-bg", published.lightBackgroundColor);
    element.style.setProperty("--maliyet-widget-text", published.lightTextColor);
    element.style.setProperty("--maliyet-widget-border", published.lightBorderColor);
    element.style.setProperty("--maliyet-widget-bg-dark", published.darkBackgroundColor);
    element.style.setProperty("--maliyet-widget-text-dark", published.darkTextColor);
    element.style.setProperty("--maliyet-widget-border-dark", published.darkBorderColor);
    element.style.setProperty("--maliyet-widget-error", published.errorColor);
    element.style.setProperty("--maliyet-widget-radius", `${published.borderRadiusPx}px`);
    element.style.setProperty("--maliyet-widget-font-family", FONT_STACKS[published.fontFamily]);
  }

  function textNode(tagName, className, value) {
    const node = document.createElement(tagName);
    node.className = className;
    node.textContent = value;
    return node;
  }

  function renderProjection(element, projection, config) {
    const card = document.createElement("section");
    card.className =
      `maliyet-widget__card maliyet-widget--theme-${config.theme} ` +
      `maliyet-widget--density-${config.density}`;
    card.setAttribute("aria-live", "polite");
    card.setAttribute("lang", config.locale);

    const children = [];
    if (config.showTitle) {
      children.push(textNode("h3", "maliyet-widget__title", projection.title));
    }
    children.push(
      textNode(
        "p",
        "maliyet-widget__range",
        `${projection.estimateMin}–${projection.estimateMax} ${projection.currency}`,
      ),
    );
    card.replaceChildren(...children);
    element.replaceChildren(card);
  }

  function renderError(element, locale) {
    const message = textNode(
      "p",
      "maliyet-widget__error",
      ERROR_MESSAGES[locale] ?? ERROR_MESSAGES.tr,
    );
    message.setAttribute("role", "status");
    message.setAttribute("lang", locale);
    element.replaceChildren(message);
  }

  function emit(element, eventName, detail) {
    if (typeof CustomEvent === "function" && typeof element.dispatchEvent === "function") {
      element.dispatchEvent(new CustomEvent(eventName, { detail }));
    }
  }

  function responseErrorCode(status) {
    if (status === 403) return "origin_denied";
    if (status === 404) return "not_found";
    if (status === 429) return "quota_exceeded";
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
    if (existing !== undefined) return existing;

    let local;
    try {
      local = localPresentationPreferences(element, options);
    } catch (error) {
      element.setAttribute("data-maliyet-state", "error");
      renderError(element, "tr");
      const code = error instanceof WidgetError ? error.code : "invalid_configuration";
      emit(element, "maliyet:error", Object.freeze({ code }));
      return Object.freeze({ ok: false, code });
    }

    const task = (async () => {
      let errorLocale = local.locale ?? "tr";
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
        if (!response.ok) throw new WidgetError(responseErrorCode(response.status));

        const projection = projectionPayload(await response.json());
        const config = resolvePresentation(local, projection.presentation);
        errorLocale = config.locale;
        applyPublishedBranding(element, projection.presentation);
        renderProjection(element, projection, config);
        element.setAttribute("data-maliyet-state", "ready");
        emit(
          element,
          "maliyet:ready",
          Object.freeze({
            version: SDK_VERSION,
            theme: config.theme,
            locale: config.locale,
            density: config.density,
            publishedBranding: projection.presentation !== null,
          }),
        );
        return Object.freeze({ ok: true });
      } catch (error) {
        mounted.delete(element);
        const code = error instanceof WidgetError ? error.code : "request_failed";
        element.setAttribute("data-maliyet-state", "error");
        renderError(element, errorLocale);
        emit(element, "maliyet:error", Object.freeze({ code }));
        return Object.freeze({ ok: false, code });
      }
    })();

    mounted.set(element, task);
    return task;
  }

  async function mountAll(root = document) {
    if (root === null || typeof root.querySelectorAll !== "function") return [];
    const elements = Array.from(root.querySelectorAll(WIDGET_SELECTOR));
    return Promise.all(elements.map((element) => mount(element)));
  }

  const sdk = Object.freeze({ version: SDK_VERSION, mount, mountAll });
  if (window[GLOBAL_NAME] !== undefined) return;

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
