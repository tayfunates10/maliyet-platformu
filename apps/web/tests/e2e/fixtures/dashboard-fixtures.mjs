/**
 * Deterministic dashboard payloads for end-to-end screenshot and state tests.
 *
 * These are test fixtures, not application data. They live outside `app/`,
 * `components/` and `lib/`, so nothing in the production bundle can import
 * them, and `scripts/test-dashboard.mjs` asserts that separation.
 *
 * Every monetary field is a Decimal string exactly as the API would send it,
 * including a unit cost with more precision than a double can hold, so the
 * tests prove the render path never rounds through floating point.
 */

export const ORGANIZATION_ID = "6f1b2c3d-4e5a-4b6c-8d9e-0a1b2c3d4e5f";
export const OTHER_ORGANIZATION_ID = "7a2c3d4e-5f6a-4b7c-8d9e-1a2b3c4d5e6f";

const SOURCES = [
  {
    authority: "Gelir İdaresi Başkanlığı",
    title: "2026 gelir vergisi tarifesi",
    official_reference: "193 sayılı Gelir Vergisi Kanunu md. 103",
    published_on: null,
    retrieved_at: "2026-08-19T09:00:00Z",
    content_sha256: "1939dcb6a0099ec64f17bb474bdab6afc4a8b1b1dd7e679e0c0e69c36ce465db",
  },
  {
    authority: "Sosyal Güvenlik Kurumu",
    title: "2026 prim oranları",
    official_reference: "5510 sayılı Kanun",
    published_on: "2026-01-01",
    retrieved_at: "2026-08-19T09:00:00Z",
    content_sha256: "2a39dcb6a0099ec64f17bb474bdab6afc4a8b1b1dd7e679e0c0e69c36ce465dc",
  },
];

const READY_RULES = [
  {
    code: "TR.INCOME_TAX.WAGE.TARIFF",
    category: "income_tax",
    description: "Ücret gelirleri için gelir vergisi tarifesi",
    state: "effective",
    effective_from: "2026-01-01",
    effective_to: "2027-01-01",
    revision: 1,
  },
  {
    code: "TR.VAT.DEFAULT_RATE",
    category: "vat",
    description: "Genel KDV oranı",
    state: "effective",
    effective_from: "2023-07-10",
    effective_to: null,
    revision: 1,
  },
  {
    code: "TR.SGK.4A.GENERAL.PREMIUM_RATES",
    category: "social_security",
    description: "4/a genel prim oranları",
    state: "effective",
    effective_from: "2026-01-01",
    effective_to: null,
    revision: 1,
  },
];

function organization(id = ORGANIZATION_ID) {
  return {
    id,
    slug: "anadolu-gida",
    legal_name: "Anadolu Gıda Üretim A.Ş.",
    primary_sector: "food_manufacturing",
    city: "Konya",
    role: "owner",
  };
}

/** A tenant with two engines recorded and a fully verified rule base. */
export function loadedDashboard() {
  return {
    organization: organization(),
    generated_at: "2026-08-28T21:30:00Z",
    calculation_count: 2,
    calculations: [
      {
        calculation_id: "11111111-2222-4333-8444-555555555555",
        name: "Tahin Helva 400g Parti Maliyeti",
        calculation_type: "food_manufacturing",
        engine_key: "food_manufacturing",
        engine_title: "Gida uretimi",
        engine_version: "food-manufacturing-v1",
        version_number: 4,
        computed_at: "2026-08-28T21:22:00Z",
        output_sha256: "68aec00d7ac1e47cf3548056266d6d7dad3e0c59b70546ea1281381612a2f4f1",
        // The food engine publishes no grand total and no margin ratio.
        total_cost: null,
        unit_cost: "63.03322847457627118644067797",
        margin_ratio: null,
        cost_categories: [
          {
            key: "food_process_category_costs",
            entries: {
              labor: "148000.00",
              energy: "62500.00",
              packaging: "27300.00",
              cold_chain: "18400.00",
              quality: "9750.00",
            },
          },
        ],
      },
      {
        calculation_id: "22222222-3333-4444-8555-666666666666",
        name: "Konya-Istanbul Sefer Maliyeti",
        calculation_type: "transportation",
        engine_key: "transportation",
        engine_title: "Ulastirma / lojistik",
        engine_version: "transportation-v1",
        version_number: 1,
        computed_at: "2026-08-28T21:22:00Z",
        output_sha256: "78aec00d7ac1e47cf3548056266d6d7dad3e0c59b70546ea1281381612a2f4f2",
        total_cost: "25585.3410",
        unit_cost: "31.58684074074074074074074074",
        margin_ratio: null,
        cost_categories: [
          { key: "consumption_category_costs", entries: { fuel: "11609.3250", adblue: "416.0160" } },
          { key: "route_category_costs", entries: { toll: "1840.00", bridge: "620.00" } },
        ],
      },
    ],
    timeline: [
      timelineEntry(1, "59.17729627118644067796610169", "2026-08-27T02:13:00Z"),
      timelineEntry(2, "60.10272000000000000000000000", "2026-08-28T21:20:00Z"),
      timelineEntry(3, "61.24170305084745762711864407", "2026-08-28T21:21:00Z"),
      timelineEntry(4, "63.03322847457627118644067797", "2026-08-28T21:22:00Z"),
    ],
    regulatory_baseline: {
      status: "ready",
      dataset: "TR-2026-core-baseline",
      dataset_version: 1,
      reviewed_on: "2026-08-19",
      evaluated_at: "2026-08-28",
      source_count: 2,
      rule_count: 3,
      effective_rule_count: 3,
      issues: [],
      sources: SOURCES,
      rules: READY_RULES,
    },
    decision_analysis: {
      artifact_count: 1,
      latest_artifact_id: "33333333-4444-4555-8666-777777777777",
      latest_engine_version: "investment-scenario-v1",
      latest_created_at: "2026-08-27T02:15:22Z",
      latest_output_sha256:
        "fbe3258d51788607b82a9914a786f528ca11a0f865ed84915d5da1089cece7dd",
    },
    widget: {
      deployment_count: 2,
      active_deployment_count: 1,
      branding_profile_count: 1,
      published_presentation_count: 1,
    },
  };
}

function timelineEntry(version, unitCost, computedAt) {
  return {
    calculation_id: "11111111-2222-4333-8444-555555555555",
    calculation_name: "Tahin Helva 400g Parti Maliyeti",
    engine_key: "food_manufacturing",
    version_number: version,
    computed_at: computedAt,
    total_cost: null,
    unit_cost: unitCost,
  };
}

/** A real tenant that has not recorded any calculation yet. */
export function emptyDashboard() {
  const base = loadedDashboard();
  return {
    ...base,
    calculation_count: 0,
    calculations: [],
    timeline: [],
    decision_analysis: {
      artifact_count: 0,
      latest_artifact_id: null,
      latest_engine_version: null,
      latest_created_at: null,
      latest_output_sha256: null,
    },
    widget: {
      deployment_count: 0,
      active_deployment_count: 0,
      branding_profile_count: 0,
      published_presentation_count: 0,
    },
  };
}

/** A rule base that no longer resolves cleanly: readiness must not read clean. */
export function degradedBaselineDashboard() {
  const base = loadedDashboard();
  return {
    ...base,
    regulatory_baseline: {
      ...base.regulatory_baseline,
      status: "degraded",
      effective_rule_count: 1,
      issues: [
        "TR.VAT.DEFAULT_RATE: no effective version at 2026-08-28",
        "TR.SGK.4A.GENERAL.PREMIUM_RATES: ambiguous effective versions at 2026-08-28",
      ],
      rules: [
        READY_RULES[0],
        { ...READY_RULES[1], state: "not_effective", effective_from: null, effective_to: null, revision: null },
        { ...READY_RULES[2], state: "ambiguous", effective_from: null, effective_to: null, revision: null },
      ],
    },
  };
}

/** The rule base could not be verified at all. */
export function unavailableBaselineDashboard() {
  const base = loadedDashboard();
  return {
    ...base,
    regulatory_baseline: {
      status: "unavailable",
      dataset: null,
      dataset_version: null,
      reviewed_on: null,
      evaluated_at: "2026-08-28",
      source_count: 0,
      rule_count: 0,
      effective_rule_count: 0,
      issues: ["baseline manifest unreadable: dosya bulunamadi"],
      sources: [],
      rules: [],
    },
  };
}

/** A projection whose organisation does not match the one that was requested. */
export function mismatchedTenantDashboard() {
  return { ...loadedDashboard(), organization: organization(OTHER_ORGANIZATION_ID) };
}

export const LOGIN_TOKEN = "e2e-fixture-session-token-0123456789";

export const ORGANIZATION_LIST = [
  { id: ORGANIZATION_ID, slug: "anadolu-gida", legal_name: "Anadolu Gıda Üretim A.Ş.", role: "owner" },
];
