import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = resolve(webRoot, "../..");
const loaderPath = resolve(webRoot, "public/widget/v1.1.0/loader.js");
const stylesPath = resolve(webRoot, "public/widget/v1.1.0/styles.css");
const previousLoaderPath = resolve(webRoot, "public/widget/v1.0.0/loader.js");
const loaderSource = readFileSync(loaderPath, "utf8");
const stylesSource = readFileSync(stylesPath, "utf8");
const previousLoader = readFileSync(previousLoaderPath);
const nextConfig = readFileSync(resolve(webRoot, "next.config.mjs"), "utf8");
const integrationDoc = readFileSync(
  resolve(repositoryRoot, "docs/integrations/widget-v1.1.md"),
  "utf8",
);

assert.equal(
  createHash("sha256").update(previousLoader).digest("hex"),
  "3023892986175db123c2b6d232e769b7115ef9896dce88d02a89a6500e135b78",
  "published widget v1.0.0 loader must remain byte-for-byte immutable",
);
assert.ok(loaderSource.length < 12_000, "widget v1.1 loader must remain a small bootstrap surface");
assert.ok(stylesSource.length < 8_000, "widget stylesheet must remain a small presentation surface");
assert.doesNotMatch(loaderSource, /\binnerHTML\b/);
assert.doesNotMatch(loaderSource, /\beval\s*\(/);
assert.doesNotMatch(loaderSource, /new\s+Function\b/);
assert.doesNotMatch(loaderSource, /Authorization/);
assert.doesNotMatch(loaderSource, /X-Api-Key/i);
assert.doesNotMatch(loaderSource, /\bparseFloat\s*\(/);
assert.doesNotMatch(loaderSource, /\bNumber\s*\(/);
assert.doesNotMatch(loaderSource, /\bIntl\.NumberFormat\b/);
assert.match(loaderSource, /credentials:\s*"omit"/);
assert.match(loaderSource, /method:\s*"GET"/);
assert.match(loaderSource, /mode:\s*"cors"/);
assert.match(loaderSource, /referrerPolicy:\s*"no-referrer"/);
assert.match(stylesSource, /--maliyet-widget-bg/);
assert.match(stylesSource, /--maliyet-widget-font-family/);
assert.doesNotMatch(stylesSource, /url\s*\(/i);
assert.doesNotMatch(stylesSource, /@import/i);
assert.match(nextConfig, /source:\s*"\/widget\/v1\.1\.0\/loader\.js"/);
assert.match(nextConfig, /source:\s*"\/widget\/v1\.1\.0\/styles\.css"/);
assert.match(integrationDoc, /theme.*auto.*light.*dark/s);
assert.match(integrationDoc, /locale.*tr.*en/s);
assert.match(integrationDoc, /density.*comfortable.*compact/s);
assert.match(integrationDoc, /showTitle/);
assert.match(integrationDoc, /CSS custom propert/i);
assert.match(integrationDoc, /script-src/);
assert.match(integrationDoc, /style-src/);
assert.match(integrationDoc, /connect-src/);
assert.doesNotMatch(integrationDoc, /script-src[^\n]*unsafe-eval/);
assert.doesNotMatch(integrationDoc, /style-src[^\n]*unsafe-inline/);

class FakeElement {
  constructor(tagName = "div") {
    this.tagName = tagName;
    this.nodeType = 1;
    this.dataset = {};
    this.attributes = new Map();
    this.children = [];
    this.className = "";
    this.textContent = "";
    this.events = [];
  }
  setAttribute(name, value) {
    this.attributes.set(name, String(value));
  }
  replaceChildren(...children) {
    this.children = children;
  }
  dispatchEvent(event) {
    this.events.push(event);
    return true;
  }
}

class FakeCustomEvent {
  constructor(type, init = {}) {
    this.type = type;
    this.detail = init.detail;
  }
}

function allText(node) {
  return [node.textContent, ...node.children.flatMap((child) => allText(child))].join(" ");
}

const scriptElement = new FakeElement("script");
scriptElement.dataset.maliyetApiBase = "https://api.example.test";
const selectorMap = new Map();
const document = {
  currentScript: scriptElement,
  readyState: "loading",
  querySelector(selector) {
    return selectorMap.get(selector) ?? null;
  },
  querySelectorAll() {
    return [];
  },
  createElement(tagName) {
    return new FakeElement(tagName);
  },
  addEventListener() {},
};

const requests = [];
let fetchImpl = async (url, options) => {
  requests.push({ url, options });
  return {
    ok: true,
    status: 200,
    async json() {
      return {
        title: '<img src=x onerror="alert(1)">',
        currency: "TRY",
        estimate_min: "1200.50",
        estimate_max: "1500.7500",
        published_at: "2026-08-22T00:00:00Z",
        private_cost: "PRIVATE-SENTINEL",
      };
    },
  };
};

const window = {};
const context = {
  window,
  document,
  CustomEvent: FakeCustomEvent,
  URL,
  WeakMap,
  Set,
  Object,
  Array,
  Promise,
  Error,
  console: { error() {} },
  encodeURIComponent,
  queueMicrotask,
  fetch: (...args) => fetchImpl(...args),
};
vm.runInNewContext(loaderSource, context, { filename: "loader-v1.1.0.js" });

const sdk = window.MaliyetWidget;
assert.equal(sdk.version, "1.1.0");
assert.equal(Object.isFrozen(sdk), true);

const deploymentId = "8e8d7c2b-6a0b-4d2e-9a48-9a3115d6f44b";
const element = new FakeElement();
element.dataset.deploymentId = deploymentId;
const result = await sdk.mount(element, {
  theme: "dark",
  locale: "en",
  density: "compact",
  showTitle: false,
});
assert.equal(result.ok, true);
assert.equal(requests.length, 1);
assert.equal(element.attributes.get("data-maliyet-state"), "ready");
const card = element.children[0];
assert.match(card.className, /maliyet-widget--theme-dark/);
assert.match(card.className, /maliyet-widget--density-compact/);
assert.equal(card.attributes.get("lang"), "en");
assert.doesNotMatch(allText(element), /<img src=x/);
assert.match(allText(element), /1200\.50–1500\.7500 TRY/);
assert.doesNotMatch(allText(element), /PRIVATE-SENTINEL/);
assert.deepEqual(
  { ...element.events.at(-1).detail },
  { version: "1.1.0", theme: "dark", locale: "en", density: "compact" },
);

const second = await sdk.mount(element);
assert.equal(second.ok, true);
assert.equal(requests.length, 1, "successful repeated mount must not double-consume quota");

const datasetElement = new FakeElement();
datasetElement.dataset.deploymentId = "9fcd44f3-6da8-45bd-a853-135250d4d318";
datasetElement.dataset.maliyetTheme = "light";
datasetElement.dataset.maliyetLocale = "tr";
datasetElement.dataset.maliyetDensity = "comfortable";
datasetElement.dataset.maliyetShowTitle = "true";
const datasetResult = await sdk.mount(datasetElement);
assert.equal(datasetResult.ok, true);
assert.match(allText(datasetElement), /<img src=x onerror="alert\(1\)">/);
assert.equal(datasetElement.children[0].attributes.get("lang"), "tr");

const invalidElement = new FakeElement();
invalidElement.dataset.deploymentId = deploymentId;
const beforeInvalid = requests.length;
const invalid = await sdk.mount(invalidElement, { theme: "dark; background:url(https://evil.test)" });
assert.deepEqual({ ...invalid }, { ok: false, code: "invalid_configuration" });
assert.equal(requests.length, beforeInvalid, "invalid presentation config must fail before quota/network I/O");

const invalidLocaleElement = new FakeElement();
invalidLocaleElement.dataset.deploymentId = deploymentId;
const beforeInvalidLocale = requests.length;
const invalidLocale = await sdk.mount(invalidLocaleElement, { locale: "tr-TR" });
assert.deepEqual({ ...invalidLocale }, { ok: false, code: "invalid_configuration" });
assert.equal(requests.length, beforeInvalidLocale);

for (const optionName of ["theme", "locale", "density", "showTitle"]) {
  const explicitNullElement = new FakeElement();
  explicitNullElement.dataset.deploymentId = deploymentId;
  explicitNullElement.dataset.maliyetTheme = "dark";
  explicitNullElement.dataset.maliyetLocale = "en";
  explicitNullElement.dataset.maliyetDensity = "compact";
  explicitNullElement.dataset.maliyetShowTitle = "false";
  const beforeExplicitNull = requests.length;
  const explicitNullResult = await sdk.mount(explicitNullElement, { [optionName]: null });
  assert.deepEqual(
    { ...explicitNullResult },
    { ok: false, code: "invalid_configuration" },
    `explicit null ${optionName} must be rejected`,
  );
  assert.equal(
    requests.length,
    beforeExplicitNull,
    `explicit null ${optionName} must fail before network/quota I/O`,
  );
}

fetchImpl = async () => ({
  ok: false,
  status: 429,
  async json() {
    return { private_detail: "DO-NOT-RENDER" };
  },
});
const quotaElement = new FakeElement();
quotaElement.dataset.deploymentId = "a1532031-a1ee-4c6a-8c10-7a8db815ef8b";
quotaElement.dataset.maliyetLocale = "en";
const quotaResult = await sdk.mount(quotaElement);
assert.deepEqual({ ...quotaResult }, { ok: false, code: "quota_exceeded" });
assert.match(allText(quotaElement), /The calculation cannot be displayed right now\./);
assert.doesNotMatch(allText(quotaElement), /DO-NOT-RENDER/);

console.log("Widget v1.1 safe theme/config contract: PASS");
