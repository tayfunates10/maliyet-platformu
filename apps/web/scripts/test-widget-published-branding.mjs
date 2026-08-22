import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = resolve(webRoot, "../..");
const loaderPath = resolve(webRoot, "public/widget/v1.2.0/loader.js");
const stylesPath = resolve(webRoot, "public/widget/v1.2.0/styles.css");
const v100Loader = readFileSync(resolve(webRoot, "public/widget/v1.0.0/loader.js"));
const v110Loader = readFileSync(resolve(webRoot, "public/widget/v1.1.0/loader.js"));
const v110Styles = readFileSync(resolve(webRoot, "public/widget/v1.1.0/styles.css"));
const loaderSource = readFileSync(loaderPath, "utf8");
const stylesSource = readFileSync(stylesPath, "utf8");
const nextConfig = readFileSync(resolve(webRoot, "next.config.mjs"), "utf8");
const integrationDoc = readFileSync(
  resolve(repositoryRoot, "docs/integrations/widget-v1.2.md"),
  "utf8",
);

function gitBlobSha1(buffer) {
  const header = Buffer.from(`blob ${buffer.length}\0`, "utf8");
  return createHash("sha1").update(header).update(buffer).digest("hex");
}

assert.equal(
  createHash("sha256").update(v100Loader).digest("hex"),
  "3023892986175db123c2b6d232e769b7115ef9896dce88d02a89a6500e135b78",
  "published widget v1.0.0 loader must remain byte-for-byte immutable",
);
assert.equal(
  gitBlobSha1(v110Loader),
  "add0b0167682ba54d9d44416b909432b49629dfa",
  "published widget v1.1.0 loader must remain byte-for-byte immutable",
);
assert.equal(
  gitBlobSha1(v110Styles),
  "325d58b56437672d39cf9c40e2ef2b97f0022147",
  "published widget v1.1.0 stylesheet must remain byte-for-byte immutable",
);

assert.ok(loaderSource.length < 18_000, "widget v1.2 loader must remain a small bootstrap surface");
assert.ok(stylesSource.length < 8_000, "widget v1.2 stylesheet must remain a small presentation surface");
assert.doesNotMatch(loaderSource, /\binnerHTML\b/);
assert.doesNotMatch(loaderSource, /\beval\s*\(/);
assert.doesNotMatch(loaderSource, /new\s+Function\b/);
assert.doesNotMatch(loaderSource, /Authorization/);
assert.doesNotMatch(loaderSource, /X-Api-Key/i);
assert.doesNotMatch(loaderSource, /\bparseFloat\s*\(/);
assert.doesNotMatch(loaderSource, /\bNumber\s*\(/);
assert.doesNotMatch(loaderSource, /\bIntl\.NumberFormat\b/);
assert.doesNotMatch(loaderSource, /createElement\(\s*["']style["']\s*\)/);
assert.doesNotMatch(loaderSource, /setAttribute\(\s*["']style["']/);
assert.match(loaderSource, /\.style\.setProperty\(/);
assert.match(loaderSource, /credentials:\s*"omit"/);
assert.match(loaderSource, /method:\s*"GET"/);
assert.match(loaderSource, /mode:\s*"cors"/);
assert.match(loaderSource, /referrerPolicy:\s*"no-referrer"/);
assert.match(stylesSource, /--maliyet-widget-bg/);
assert.match(stylesSource, /--maliyet-widget-font-family/);
assert.doesNotMatch(stylesSource, /url\s*\(/i);
assert.doesNotMatch(stylesSource, /@import/i);
assert.match(nextConfig, /source:\s*"\/widget\/v1\.2\.0\/loader\.js"/);
assert.match(nextConfig, /source:\s*"\/widget\/v1\.2\.0\/styles\.css"/);
assert.match(integrationDoc, /programmatic mount option.*HTML dataset option.*server-published presentation.*SDK default/s);
assert.match(integrationDoc, /fail-closed/);
assert.match(integrationDoc, /style\.setProperty/);
assert.match(integrationDoc, /script-src/);
assert.match(integrationDoc, /style-src/);
assert.match(integrationDoc, /connect-src/);
assert.doesNotMatch(integrationDoc, /script-src[^\n]*unsafe-eval/);
assert.doesNotMatch(integrationDoc, /style-src[^\n]*unsafe-inline/);

class FakeStyle {
  constructor() {
    this.properties = new Map();
  }
  setProperty(name, value) {
    this.properties.set(String(name), String(value));
  }
  getPropertyValue(name) {
    return this.properties.get(name) ?? "";
  }
}

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
    this.style = new FakeStyle();
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

const basePresentation = Object.freeze({
  theme: "dark",
  locale: "en",
  density: "compact",
  show_title: false,
  light_background_color: "#112233",
  light_text_color: "#F1F2F3",
  light_border_color: "#445566",
  dark_background_color: "#101820",
  dark_text_color: "#FAFAFA",
  dark_border_color: "#778899",
  error_color: "#AA0011",
  border_radius_px: 16,
  font_family: "serif",
  published_at: "2026-08-22T00:00:00Z",
  internal_snapshot_id: "PRIVATE-SNAPSHOT-ID",
});

function publicPayload(presentation = basePresentation) {
  return {
    title: '<img src=x onerror="alert(1)">',
    currency: "TRY",
    estimate_min: "1200.50",
    estimate_max: "1500.7500",
    published_at: "2026-08-22T00:00:00Z",
    presentation,
    private_cost: "PRIVATE-SENTINEL",
  };
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
      return publicPayload();
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
  Number,
  console: { error() {} },
  encodeURIComponent,
  queueMicrotask,
  fetch: (...args) => fetchImpl(...args),
};
vm.runInNewContext(loaderSource, context, { filename: "loader-v1.2.0.js" });

const sdk = window.MaliyetWidget;
assert.equal(sdk.version, "1.2.0");
assert.equal(Object.isFrozen(sdk), true);

const deploymentId = "8e8d7c2b-6a0b-4d2e-9a48-9a3115d6f44b";
const serverElement = new FakeElement();
serverElement.dataset.deploymentId = deploymentId;
const serverResult = await sdk.mount(serverElement);
assert.deepEqual({ ...serverResult }, { ok: true });
assert.equal(requests.length, 1);
assert.equal(serverElement.attributes.get("data-maliyet-state"), "ready");
const serverCard = serverElement.children[0];
assert.match(serverCard.className, /maliyet-widget--theme-dark/);
assert.match(serverCard.className, /maliyet-widget--density-compact/);
assert.equal(serverCard.attributes.get("lang"), "en");
assert.equal(serverCard.children.length, 1, "server show_title=false must hide title");
assert.match(allText(serverElement), /1200\.50–1500\.7500 TRY/);
assert.doesNotMatch(allText(serverElement), /PRIVATE-SENTINEL|PRIVATE-SNAPSHOT-ID/);
assert.doesNotMatch(allText(serverElement), /<img src=x/);
assert.equal(serverElement.style.getPropertyValue("--maliyet-widget-bg"), "#112233");
assert.equal(serverElement.style.getPropertyValue("--maliyet-widget-text"), "#F1F2F3");
assert.equal(serverElement.style.getPropertyValue("--maliyet-widget-border"), "#445566");
assert.equal(serverElement.style.getPropertyValue("--maliyet-widget-bg-dark"), "#101820");
assert.equal(serverElement.style.getPropertyValue("--maliyet-widget-text-dark"), "#FAFAFA");
assert.equal(serverElement.style.getPropertyValue("--maliyet-widget-border-dark"), "#778899");
assert.equal(serverElement.style.getPropertyValue("--maliyet-widget-error"), "#AA0011");
assert.equal(serverElement.style.getPropertyValue("--maliyet-widget-radius"), "16px");
assert.equal(
  serverElement.style.getPropertyValue("--maliyet-widget-font-family"),
  'Georgia, "Times New Roman", serif',
);
assert.deepEqual(
  [...serverElement.style.properties.keys()].sort(),
  [
    "--maliyet-widget-bg",
    "--maliyet-widget-bg-dark",
    "--maliyet-widget-border",
    "--maliyet-widget-border-dark",
    "--maliyet-widget-error",
    "--maliyet-widget-font-family",
    "--maliyet-widget-radius",
    "--maliyet-widget-text",
    "--maliyet-widget-text-dark",
  ].sort(),
  "server payload must not control CSS property names",
);
assert.deepEqual(
  { ...serverElement.events.at(-1).detail },
  {
    version: "1.2.0",
    theme: "dark",
    locale: "en",
    density: "compact",
    publishedBranding: true,
  },
);

const repeated = await sdk.mount(serverElement);
assert.equal(repeated.ok, true);
assert.equal(requests.length, 1, "successful repeated mount must not double-consume quota");

const precedenceElement = new FakeElement();
precedenceElement.dataset.deploymentId = "9fcd44f3-6da8-45bd-a853-135250d4d318";
precedenceElement.dataset.maliyetTheme = "light";
precedenceElement.dataset.maliyetLocale = "en";
precedenceElement.dataset.maliyetShowTitle = "false";
const precedenceResult = await sdk.mount(precedenceElement, {
  theme: "auto",
  locale: "tr",
  showTitle: true,
});
assert.equal(precedenceResult.ok, true);
const precedenceCard = precedenceElement.children[0];
assert.match(precedenceCard.className, /maliyet-widget--theme-auto/);
assert.match(precedenceCard.className, /maliyet-widget--density-compact/);
assert.equal(precedenceCard.attributes.get("lang"), "tr");
assert.equal(precedenceCard.children.length, 2, "programmatic showTitle must override dataset/server");
assert.equal(precedenceElement.style.getPropertyValue("--maliyet-widget-bg"), "#112233");

fetchImpl = async (url, options) => {
  requests.push({ url, options });
  const payload = publicPayload();
  delete payload.presentation;
  return {
    ok: true,
    status: 200,
    async json() {
      return payload;
    },
  };
};
const legacyElement = new FakeElement();
legacyElement.dataset.deploymentId = "a1532031-a1ee-4c6a-8c10-7a8db815ef8b";
const legacyResult = await sdk.mount(legacyElement);
assert.equal(legacyResult.ok, true);
assert.match(legacyElement.children[0].className, /maliyet-widget--theme-auto/);
assert.match(legacyElement.children[0].className, /maliyet-widget--density-comfortable/);
assert.equal(legacyElement.children[0].attributes.get("lang"), "tr");
assert.equal(legacyElement.children[0].children.length, 2);
assert.equal(legacyElement.style.properties.size, 0);
assert.equal(legacyElement.events.at(-1).detail.publishedBranding, false);

const malformedCases = [
  ["theme", "neon"],
  ["locale", "tr-TR"],
  ["density", "dense"],
  ["show_title", "false"],
  ["light_background_color", "#abcdef"],
  ["dark_text_color", "red"],
  ["border_radius_px", 12.5],
  ["border_radius_px", 33],
  ["font_family", "url(https://evil.test/font.woff2)"],
];
let malformedIndex = 0;
for (const [field, invalidValue] of malformedCases) {
  malformedIndex += 1;
  fetchImpl = async (url, options) => {
    requests.push({ url, options });
    return {
      ok: true,
      status: 200,
      async json() {
        return publicPayload({ ...basePresentation, [field]: invalidValue });
      },
    };
  };
  const malformedElement = new FakeElement();
  malformedElement.dataset.deploymentId = `b000000${malformedIndex}-0000-4000-8000-00000000000${malformedIndex}`;
  const malformedResult = await sdk.mount(malformedElement);
  assert.deepEqual(
    { ...malformedResult },
    { ok: false, code: "invalid_response" },
    `malformed server presentation field ${field} must fail closed`,
  );
  assert.equal(malformedElement.style.properties.size, 0);
  assert.equal(malformedElement.attributes.get("data-maliyet-state"), "error");
}

fetchImpl = async (url, options) => {
  requests.push({ url, options });
  return {
    ok: true,
    status: 200,
    async json() {
      return publicPayload({ theme: "dark" });
    },
  };
};
const partialElement = new FakeElement();
partialElement.dataset.deploymentId = "c1532031-a1ee-4c6a-8c10-7a8db815ef8b";
assert.deepEqual(
  { ...(await sdk.mount(partialElement)) },
  { ok: false, code: "invalid_response" },
);

fetchImpl = async (url, options) => {
  requests.push({ url, options });
  return {
    ok: true,
    status: 200,
    async json() {
      return publicPayload(null);
    },
  };
};
const nullPresentationElement = new FakeElement();
nullPresentationElement.dataset.deploymentId = "d1532031-a1ee-4c6a-8c10-7a8db815ef8b";
assert.deepEqual(
  { ...(await sdk.mount(nullPresentationElement)) },
  { ok: false, code: "invalid_response" },
);

const beforeInvalidLocal = requests.length;
const invalidLocalElement = new FakeElement();
invalidLocalElement.dataset.deploymentId = deploymentId;
const invalidLocalResult = await sdk.mount(invalidLocalElement, { theme: null });
assert.deepEqual({ ...invalidLocalResult }, { ok: false, code: "invalid_configuration" });
assert.equal(
  requests.length,
  beforeInvalidLocal,
  "invalid local presentation must fail before network/quota I/O",
);

fetchImpl = async (url, options) => {
  requests.push({ url, options });
  return {
    ok: false,
    status: 429,
    async json() {
      return { private_detail: "DO-NOT-RENDER" };
    },
  };
};
const quotaElement = new FakeElement();
quotaElement.dataset.deploymentId = "e1532031-a1ee-4c6a-8c10-7a8db815ef8b";
quotaElement.dataset.maliyetLocale = "en";
const quotaResult = await sdk.mount(quotaElement);
assert.deepEqual({ ...quotaResult }, { ok: false, code: "quota_exceeded" });
assert.match(allText(quotaElement), /The calculation cannot be displayed right now\./);
assert.doesNotMatch(allText(quotaElement), /DO-NOT-RENDER/);

console.log("Widget v1.2 published branding contract: PASS");
