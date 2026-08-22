import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = resolve(webRoot, "../..");
const loaderPath = resolve(webRoot, "public/widget/v1.0.0/loader.js");
const loaderSource = readFileSync(loaderPath, "utf8");
const nextConfig = readFileSync(resolve(webRoot, "next.config.mjs"), "utf8");
const integrationDoc = readFileSync(
  resolve(repositoryRoot, "docs/integrations/widget-v1.md"),
  "utf8",
);

assert.ok(loaderSource.length < 12_000, "widget loader must remain a small bootstrap surface");
assert.doesNotMatch(loaderSource, /\binnerHTML\b/);
assert.doesNotMatch(loaderSource, /\beval\s*\(/);
assert.doesNotMatch(loaderSource, /new\s+Function\b/);
assert.doesNotMatch(loaderSource, /Authorization/);
assert.doesNotMatch(loaderSource, /X-Api-Key/i);
assert.match(loaderSource, /credentials:\s*"omit"/);
assert.match(loaderSource, /method:\s*"GET"/);
assert.match(loaderSource, /mode:\s*"cors"/);
assert.match(loaderSource, /referrerPolicy:\s*"no-referrer"/);
assert.match(nextConfig, /source:\s*"\/widget\/v1\.0\.0\/loader\.js"/);
assert.match(nextConfig, /Access-Control-Allow-Origin/);
assert.match(nextConfig, /Cross-Origin-Resource-Policy/);
assert.match(nextConfig, /max-age=31536000, immutable/);
assert.match(integrationDoc, /script-src/);
assert.match(integrationDoc, /connect-src/);
assert.doesNotMatch(integrationDoc, /unsafe-eval/);
assert.doesNotMatch(integrationDoc, /unsafe-inline/);

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
        estimate_max: "1500.75",
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
  Object,
  Array,
  Promise,
  Error,
  console: { error() {} },
  encodeURIComponent,
  queueMicrotask,
  fetch: (...args) => fetchImpl(...args),
};
vm.runInNewContext(loaderSource, context, { filename: "loader.js" });

const sdk = window.MaliyetWidget;
assert.equal(sdk.version, "1.0.0");
assert.equal(Object.isFrozen(sdk), true);

const deploymentId = "8e8d7c2b-6a0b-4d2e-9a48-9a3115d6f44b";
const element = new FakeElement();
element.dataset.deploymentId = deploymentId;
const firstResult = await sdk.mount(element);
assert.equal(firstResult.ok, true);
assert.equal(element.attributes.get("data-maliyet-state"), "ready");
assert.equal(requests.length, 1);
assert.equal(
  requests[0].url,
  `https://api.example.test/organizations/widget/deployments/${deploymentId}/projection`,
);
assert.equal(requests[0].options.method, "GET");
assert.equal(requests[0].options.mode, "cors");
assert.equal(requests[0].options.credentials, "omit");
assert.equal(requests[0].options.cache, "no-store");
assert.equal(requests[0].options.redirect, "error");
assert.equal(requests[0].options.referrerPolicy, "no-referrer");
assert.equal(Object.hasOwn(requests[0].options, "headers"), false);
assert.equal(Object.hasOwn(requests[0].options, "body"), false);
assert.match(allText(element), /<img src=x onerror="alert\(1\)">/);
assert.doesNotMatch(allText(element), /PRIVATE-SENTINEL/);
assert.equal(element.events.at(-1).type, "maliyet:ready");

const secondResult = await sdk.mount(element);
assert.equal(secondResult.ok, true);
assert.equal(requests.length, 1, "repeated mount must not double-consume quota");

const invalidApiElement = new FakeElement();
invalidApiElement.dataset.deploymentId = deploymentId;
const beforeInvalidApi = requests.length;
const invalidApi = await sdk.mount(invalidApiElement, { apiBase: "http://api.example.test" });
assert.deepEqual({ ...invalidApi }, { ok: false, code: "invalid_configuration" });
assert.equal(requests.length, beforeInvalidApi, "invalid API base must fail before network I/O");
assert.equal(invalidApiElement.attributes.get("data-maliyet-state"), "error");

const invalidIdElement = new FakeElement();
invalidIdElement.dataset.deploymentId = "not-a-uuid";
const beforeInvalidId = requests.length;
const invalidId = await sdk.mount(invalidIdElement);
assert.deepEqual({ ...invalidId }, { ok: false, code: "invalid_configuration" });
assert.equal(requests.length, beforeInvalidId, "invalid deployment ID must fail before network I/O");

fetchImpl = async () => ({
  ok: false,
  status: 429,
  async json() {
    return { private_detail: "DO-NOT-RENDER" };
  },
});
const quotaElement = new FakeElement();
quotaElement.dataset.deploymentId = "9fcd44f3-6da8-45bd-a853-135250d4d318";
const quotaResult = await sdk.mount(quotaElement);
assert.deepEqual({ ...quotaResult }, { ok: false, code: "quota_exceeded" });
assert.doesNotMatch(allText(quotaElement), /DO-NOT-RENDER/);
assert.match(allText(quotaElement), /Hesaplama şu anda gösterilemiyor\./);
assert.equal(quotaElement.events.at(-1).type, "maliyet:error");
assert.deepEqual({ ...quotaElement.events.at(-1).detail }, { code: "quota_exceeded" });

console.log("Widget SDK integration contract: PASS");
