# ADR 0031 — Persisted Decision Analysis Artifacts

## Durum

Kabul edildi.

## Bağlam

ADR 0029 yatırım/senaryo çekirdeğini, ADR 0030 ise tenant-scoped HTTP API sınırını kurdu. Bu API başlangıçta her isteği hesaplayıp sonucu döndürüyor ancak sonucu kalıcı tarihçe olarak saklamıyordu. Kanonik ürün kapsamı hesaplama geçmişi ve yeniden üretilebilir snapshot gerektirir; yatırım/karar analizi için de geçmiş bir sonucun bugünkü engine davranışına bakmadan denetlenebilmesi gerekir.

Decision analysis, sektör hesaplama `Calculation` / `CalculationVersion` yaşam döngüsünden ayrı bir karar-destek artifact'ıdır. Bu nedenle sırf persistence sağlamak için sahte bir sektör `calculation_type` üretilmeyecek veya mevcut sekiz engine registry anahtarından biri taklit edilmeyecektir.

## Karar

Her başarılı yatırım/senaryo analizi `decision_analysis_artifacts` tablosuna append-only servis akışıyla kaydedilir.

Artifact şu kanonik alanları taşır:

- tenant `organization_id`,
- authenticated `created_by_user_id`,
- exact `engine_version`,
- canonical input snapshot,
- canonical output snapshot,
- input SHA-256,
- output SHA-256,
- immutable creation timestamp.

Snapshot canonicalization ve digest üretimi mevcut `calculation_orchestration.canonicalize_snapshot` sözleşmesini kullanır: JSON key'leri deterministic sıralanır, compact UTF-8 JSON üretilir, unsupported değer ve binary float fail-closed reddedilir. Persist edilen snapshot caller nesnesiyle alias paylaşmaz.

### Tenant ve actor sınırı

`(organization_id, created_by_user_id)` doğrudan `organization_memberships` composite key'ine foreign key ile bağlanır. Caller request body actor/user/role seçemez; actor yalnız geçerli bearer session ve server-side membership çözümünden gelir.

Artifact detail lookup her zaman `(organization_id, artifact_id)` ile yapılır. Başka tenant'a ait artifact ile bulunmayan artifact aynı `404 analysis not found` yüzeyine düşer.

### History ve replay

- `POST /organizations/{organization_id}/decision-analysis/investment-scenarios` başarılı engine execution sonrasında artifact'ı ve audit event'i aynı request transaction'ında yazar.
- `GET .../investment-scenarios` yalnız bounded metadata history döndürür; engine'i yeniden çalıştırmaz.
- `GET .../investment-scenarios/{artifact_id}` stored snapshot'ı current engine state'ine bakmadan döndürür ancak önce input/output digestlerini tekrar hesaplayarak integrity doğrulaması yapar.
- Digest mismatch veya canonical snapshot bozulması `409 analysis integrity check failed` ile fail-closed olur.

Historical read hiçbir current rule, current engine output veya yeni senaryo varsayımı çözmez. Stored output artifact'ın kendisidir.

### Audit

Her başarılı artifact write aynı transaction içinde `decision_analysis.recorded` audit event'i üretir. Audit payload engine version ile input/output digestlerini taşır; raw bearer token veya private credential taşımaz.

## Güvence sınırı

Bu karar fiziksel WORM/immutable storage iddiası değildir. Doğrudan database write yetkisi olan bir operatör artifact row'unu değiştirebilir. Sağlanan güvence:

- normal application akışında append-only write,
- tenant/actor database foreign-key sınırları,
- deterministic SHA-256 tamper detection,
- authenticated audit izi,
- historical read sırasında fail-closed integrity verification.

Retention, KVKK deletion lifecycle, physical WORM storage ve external notarization/signing ayrı governance kararlarıdır.

## Public veri sınırı

Decision-analysis artifact'ları tenant-private kalır. Public calculation projection veya widget endpoint'lerine otomatik olarak bağlanmaz ve input/output snapshot'ları public response'a taşınmaz. Public/widget güvenlik sınırı değişmez.

## Migration

Alembic revision `0009_decision_artifacts`, `0008_widget_branding_profiles` revision'ından devam eder. Migration upgrade/downgrade/upgrade, single-head, metadata drift ve column parity testlerinden geçmek zorundadır.

## Kabul kriterleri

- başarılı analysis exact input/output snapshot ve 64-char SHA-256 digestlerle persist edilir,
- authenticated actor DB row ve audit event'inde server-side identity olur,
- history bounded ve tenant-scoped olur,
- detail stored artifact'ı engine recalculation yapmadan döndürür,
- cross-tenant detail 404 olur,
- doğrudan DB snapshot tamper sonrası detail 409 olur,
- numeric JSON/binary float ve mevcut Decimal validity sınırları değişmeden fail-closed kalır,
- migration full round-trip ve `alembic check` geçer,
- tüm mevcut API/web/widget regression kapıları yeşil kalır.
