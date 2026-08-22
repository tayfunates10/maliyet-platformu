const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const HEX_COLOR_PATTERN = /^#[0-9A-F]{6}$/;
const THEMES = new Set(["auto", "light", "dark"]);
const LOCALES = new Set(["tr", "en"]);
const DENSITIES = new Set(["comfortable", "compact"]);
const FONT_FAMILIES = new Set(["system", "sans", "serif", "monospace"]);
const MANAGEMENT_PREFIX = "/api/management";

export type WidgetTheme = "auto" | "light" | "dark";
export type WidgetLocale = "tr" | "en";
export type WidgetDensity = "comfortable" | "compact";
export type WidgetFontFamily = "system" | "sans" | "serif" | "monospace";

export type OrganizationSummary = Readonly<{
  id: string;
  slug: string;
  legal_name: string;
  role: string;
  primary_sector: string | null;
  country_code: string | null;
  city: string | null;
}>;

export type WidgetBrandingProfileInput = Readonly<{
  name: string;
  theme: WidgetTheme;
  locale: WidgetLocale;
  density: WidgetDensity;
  show_title: boolean;
  light_background_color: string;
  light_text_color: string;
  light_border_color: string;
  dark_background_color: string;
  dark_text_color: string;
  dark_border_color: string;
  error_color: string;
  border_radius_px: number;
  font_family: WidgetFontFamily;
}>;

export type WidgetBrandingProfile = WidgetBrandingProfileInput &
  Readonly<{
    id: string;
    revision: number;
  }>;

export type WidgetPresentationPublishReceipt = Readonly<{
  deployment_id: string;
  branding_profile_id: string;
  profile_revision: number;
  published_at: string;
}>;

export class ManagementApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string) {
    super(code);
    this.name = "ManagementApiError";
    this.status = status;
    this.code = code;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function requireString(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  if (typeof value !== "string") throw new ManagementApiError(502, "invalid_response");
  return value;
}

function requireNullableString(record: Record<string, unknown>, key: string): string | null {
  const value = record[key];
  if (value === null) return null;
  if (typeof value !== "string") throw new ManagementApiError(502, "invalid_response");
  return value;
}

function errorCode(status: number): string {
  if (status === 401) return "authentication_required";
  if (status === 403) return "access_denied";
  if (status === 404) return "not_found";
  if (status === 409) return "conflict";
  if (status === 413) return "request_too_large";
  if (status === 422) return "invalid_request";
  if (status === 429) return "rate_limited";
  return "request_failed";
}

async function requestJson(
  path: string,
  options: Readonly<{
    method?: "GET" | "POST" | "PUT";
    token?: string;
    body?: unknown;
  }> = {},
): Promise<unknown> {
  const headers = new Headers({ Accept: "application/json" });
  if (options.token !== undefined) {
    if (options.token.length < 16 || options.token.length > 512) {
      throw new ManagementApiError(0, "invalid_session");
    }
    headers.set("Authorization", `Bearer ${options.token}`);
  }
  let body: string | undefined;
  if (options.body !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(options.body);
  }

  const response = await fetch(`${MANAGEMENT_PREFIX}${path}`, {
    method: options.method ?? "GET",
    headers,
    body,
    credentials: "omit",
    cache: "no-store",
    redirect: "error",
    referrerPolicy: "no-referrer",
  });
  if (!response.ok) throw new ManagementApiError(response.status, errorCode(response.status));
  try {
    return await response.json();
  } catch {
    throw new ManagementApiError(502, "invalid_response");
  }
}

function parseOrganization(value: unknown): OrganizationSummary {
  if (!isRecord(value)) throw new ManagementApiError(502, "invalid_response");
  const id = requireString(value, "id");
  const slug = requireString(value, "slug");
  const legalName = requireString(value, "legal_name");
  const role = requireString(value, "role");
  if (!UUID_PATTERN.test(id) || slug.length === 0 || legalName.length === 0 || role.length === 0) {
    throw new ManagementApiError(502, "invalid_response");
  }
  return Object.freeze({
    id,
    slug,
    legal_name: legalName,
    role,
    primary_sector: requireNullableString(value, "primary_sector"),
    country_code: requireNullableString(value, "country_code"),
    city: requireNullableString(value, "city"),
  });
}

function parseProfile(value: unknown): WidgetBrandingProfile {
  if (!isRecord(value)) throw new ManagementApiError(502, "invalid_response");
  const id = requireString(value, "id");
  const name = requireString(value, "name");
  const theme = requireString(value, "theme");
  const locale = requireString(value, "locale");
  const density = requireString(value, "density");
  const showTitle = value.show_title;
  const radius = value.border_radius_px;
  const fontFamily = requireString(value, "font_family");
  const revision = value.revision;
  const colors = [
    requireString(value, "light_background_color"),
    requireString(value, "light_text_color"),
    requireString(value, "light_border_color"),
    requireString(value, "dark_background_color"),
    requireString(value, "dark_text_color"),
    requireString(value, "dark_border_color"),
    requireString(value, "error_color"),
  ];
  if (
    !UUID_PATTERN.test(id) ||
    name.length === 0 ||
    !THEMES.has(theme) ||
    !LOCALES.has(locale) ||
    !DENSITIES.has(density) ||
    typeof showTitle !== "boolean" ||
    typeof radius !== "number" ||
    !Number.isInteger(radius) ||
    radius < 0 ||
    radius > 32 ||
    !FONT_FAMILIES.has(fontFamily) ||
    typeof revision !== "number" ||
    !Number.isInteger(revision) ||
    revision < 1 ||
    colors.some((color) => !HEX_COLOR_PATTERN.test(color))
  ) {
    throw new ManagementApiError(502, "invalid_response");
  }
  return Object.freeze({
    id,
    name,
    revision,
    theme: theme as WidgetTheme,
    locale: locale as WidgetLocale,
    density: density as WidgetDensity,
    show_title: showTitle,
    light_background_color: colors[0],
    light_text_color: colors[1],
    light_border_color: colors[2],
    dark_background_color: colors[3],
    dark_text_color: colors[4],
    dark_border_color: colors[5],
    error_color: colors[6],
    border_radius_px: radius,
    font_family: fontFamily as WidgetFontFamily,
  });
}

function parsePublishReceipt(value: unknown): WidgetPresentationPublishReceipt {
  if (!isRecord(value)) throw new ManagementApiError(502, "invalid_response");
  const deploymentId = requireString(value, "deployment_id");
  const profileId = requireString(value, "branding_profile_id");
  const revision = value.profile_revision;
  const publishedAt = requireString(value, "published_at");
  if (
    !UUID_PATTERN.test(deploymentId) ||
    !UUID_PATTERN.test(profileId) ||
    typeof revision !== "number" ||
    !Number.isInteger(revision) ||
    revision < 1 ||
    Number.isNaN(Date.parse(publishedAt))
  ) {
    throw new ManagementApiError(502, "invalid_response");
  }
  return Object.freeze({
    deployment_id: deploymentId,
    branding_profile_id: profileId,
    profile_revision: revision,
    published_at: publishedAt,
  });
}

export function isDeploymentId(value: string): boolean {
  return UUID_PATTERN.test(value.trim());
}

export async function loginManagementSession(
  _apiBaseUrl: string,
  email: string,
  password: string,
): Promise<string> {
  const payload = await requestJson("/auth/login", {
    method: "POST",
    body: { email, password },
  });
  if (!isRecord(payload)) throw new ManagementApiError(502, "invalid_response");
  const token = requireString(payload, "access_token");
  if (token.length < 16 || token.length > 512) {
    throw new ManagementApiError(502, "invalid_response");
  }
  return token;
}

export async function listManagementOrganizations(
  _apiBaseUrl: string,
  token: string,
): Promise<readonly OrganizationSummary[]> {
  const payload = await requestJson("/organizations", { token });
  if (!Array.isArray(payload)) throw new ManagementApiError(502, "invalid_response");
  return Object.freeze(payload.map(parseOrganization));
}

export async function listBrandingProfiles(
  _apiBaseUrl: string,
  token: string,
  organizationId: string,
): Promise<readonly WidgetBrandingProfile[]> {
  if (!UUID_PATTERN.test(organizationId)) throw new ManagementApiError(0, "invalid_organization");
  const payload = await requestJson(
    `/organizations/${encodeURIComponent(organizationId)}/widget-branding-profiles`,
    { token },
  );
  if (!Array.isArray(payload)) throw new ManagementApiError(502, "invalid_response");
  return Object.freeze(payload.map(parseProfile));
}

export async function createBrandingProfile(
  _apiBaseUrl: string,
  token: string,
  organizationId: string,
  profile: WidgetBrandingProfileInput,
): Promise<WidgetBrandingProfile> {
  if (!UUID_PATTERN.test(organizationId)) throw new ManagementApiError(0, "invalid_organization");
  return parseProfile(
    await requestJson(`/organizations/${encodeURIComponent(organizationId)}/widget-branding-profiles`, {
      method: "POST",
      token,
      body: profile,
    }),
  );
}

export async function updateBrandingProfile(
  _apiBaseUrl: string,
  token: string,
  organizationId: string,
  profileId: string,
  profile: WidgetBrandingProfileInput,
): Promise<WidgetBrandingProfile> {
  if (!UUID_PATTERN.test(organizationId) || !UUID_PATTERN.test(profileId)) {
    throw new ManagementApiError(0, "invalid_resource");
  }
  return parseProfile(
    await requestJson(
      `/organizations/${encodeURIComponent(organizationId)}/widget-branding-profiles/${encodeURIComponent(profileId)}`,
      { method: "PUT", token, body: profile },
    ),
  );
}

export async function publishBrandingProfile(
  _apiBaseUrl: string,
  token: string,
  organizationId: string,
  deploymentId: string,
  profileId: string,
): Promise<WidgetPresentationPublishReceipt> {
  if (
    !UUID_PATTERN.test(organizationId) ||
    !UUID_PATTERN.test(deploymentId) ||
    !UUID_PATTERN.test(profileId)
  ) {
    throw new ManagementApiError(0, "invalid_resource");
  }
  return parsePublishReceipt(
    await requestJson(
      `/organizations/${encodeURIComponent(organizationId)}/widget-deployments/${encodeURIComponent(deploymentId)}/presentation`,
      { method: "POST", token, body: { branding_profile_id: profileId } },
    ),
  );
}
