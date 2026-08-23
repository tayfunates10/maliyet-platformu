import assert from "node:assert/strict";

const originalNodeEnv = process.env.NODE_ENV;
const originalApiBase = process.env.NEXT_PUBLIC_API_BASE_URL;
let importCounter = 0;

async function loadRuntimeConfig() {
  importCounter += 1;
  return import(`../lib/runtime-config.ts?runtime-test=${importCounter}`);
}

async function resolveApiBase({ nodeEnv, apiBase }) {
  if (nodeEnv === undefined) {
    delete process.env.NODE_ENV;
  } else {
    process.env.NODE_ENV = nodeEnv;
  }
  if (apiBase === undefined) {
    delete process.env.NEXT_PUBLIC_API_BASE_URL;
  } else {
    process.env.NEXT_PUBLIC_API_BASE_URL = apiBase;
  }

  const { getPublicApiBaseUrl } = await loadRuntimeConfig();
  return getPublicApiBaseUrl();
}

try {
  await assert.rejects(
    () => resolveApiBase({ nodeEnv: "production", apiBase: undefined }),
    /NEXT_PUBLIC_API_BASE_URL is required in production/,
  );
  await assert.rejects(
    () => resolveApiBase({ nodeEnv: "production", apiBase: "http://api.example.com" }),
    /must use HTTPS/,
  );
  await assert.rejects(
    () => resolveApiBase({ nodeEnv: "production", apiBase: "https://user:pass@api.example.com" }),
    /must not contain credentials/,
  );
  await assert.rejects(
    () => resolveApiBase({ nodeEnv: "production", apiBase: "https://api.example.com/v1" }),
    /must not contain a path/,
  );
  await assert.rejects(
    () => resolveApiBase({ nodeEnv: "production", apiBase: "https://api.example.com?debug=1" }),
    /must not contain credentials, query parameters, or fragments/,
  );

  assert.equal(
    await resolveApiBase({ nodeEnv: "production", apiBase: "https://api.example.com/" }),
    "https://api.example.com",
  );
  assert.equal(await resolveApiBase({ nodeEnv: "development", apiBase: undefined }), "http://localhost:8000");
  assert.equal(
    await resolveApiBase({ nodeEnv: "development", apiBase: "http://127.0.0.1:8000" }),
    "http://127.0.0.1:8000",
  );
  await assert.rejects(
    () => resolveApiBase({ nodeEnv: "development", apiBase: "http://192.168.1.10:8000" }),
    /must use HTTPS/,
  );

  console.log("Runtime config contract: PASS");
} finally {
  if (originalNodeEnv === undefined) {
    delete process.env.NODE_ENV;
  } else {
    process.env.NODE_ENV = originalNodeEnv;
  }
  if (originalApiBase === undefined) {
    delete process.env.NEXT_PUBLIC_API_BASE_URL;
  } else {
    process.env.NEXT_PUBLIC_API_BASE_URL = originalApiBase;
  }
}
