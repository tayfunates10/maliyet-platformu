"use client";

import type { FormEvent } from "react";
import { useState } from "react";
import {
  type ManagementApiError,
  type OrganizationSummary,
  type WidgetBrandingProfile,
  type WidgetBrandingProfileInput,
  type WidgetDeploymentSummary,
  createBrandingProfile,
  listBrandingProfiles,
  listManagementOrganizations,
  listWidgetDeployments,
  loginManagementSession,
  publishBrandingProfile,
  updateBrandingProfile,
} from "@/lib/widget-branding-management-api";
import styles from "./widget-branding-manager.module.css";

const DEFAULT_PROFILE: WidgetBrandingProfileInput = Object.freeze({
  name: "Yeni marka profili",
  theme: "auto",
  locale: "tr",
  density: "comfortable",
  show_title: true,
  light_background_color: "#FFFFFF",
  light_text_color: "#17202A",
  light_border_color: "#D7DCE3",
  dark_background_color: "#151A21",
  dark_text_color: "#F5F7FA",
  dark_border_color: "#343B46",
  error_color: "#8B1E1E",
  border_radius_px: 12,
  font_family: "system",
});

const MANAGER_ROLES = new Set(["owner", "admin"]);

function profileInput(profile: WidgetBrandingProfile): WidgetBrandingProfileInput {
  return {
    name: profile.name,
    theme: profile.theme,
    locale: profile.locale,
    density: profile.density,
    show_title: profile.show_title,
    light_background_color: profile.light_background_color,
    light_text_color: profile.light_text_color,
    light_border_color: profile.light_border_color,
    dark_background_color: profile.dark_background_color,
    dark_text_color: profile.dark_text_color,
    dark_border_color: profile.dark_border_color,
    error_color: profile.error_color,
    border_radius_px: profile.border_radius_px,
    font_family: profile.font_family,
  };
}

function userMessage(error: unknown): string {
  const code = (error as Partial<ManagementApiError> | null)?.code;
  if (code === "authentication_required") return "Oturum geçersiz veya süresi dolmuş.";
  if (code === "access_denied") return "Bu işlem için owner veya admin yetkisi gerekiyor.";
  if (code === "not_found") return "İstenen kayıt bulunamadı veya artık aktif değil.";
  if (code === "conflict") return "Aynı isimde bir profil veya çakışan kayıt var.";
  if (code === "invalid_request") return "Gönderilen alanlardan biri geçersiz.";
  if (code === "invalid_api_base") return "Yönetim API adresi HTTPS olmalı.";
  if (code === "invalid_response") return "Sunucudan beklenmeyen bir yanıt geldi.";
  return "İşlem tamamlanamadı. Lütfen tekrar deneyin.";
}

export function WidgetBrandingManager({ apiBaseUrl }: Readonly<{ apiBaseUrl: string }>) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [token, setToken] = useState<string | null>(null);
  const [organizations, setOrganizations] = useState<readonly OrganizationSummary[]>([]);
  const [organizationId, setOrganizationId] = useState("");
  const [profiles, setProfiles] = useState<readonly WidgetBrandingProfile[]>([]);
  const [deployments, setDeployments] = useState<readonly WidgetDeploymentSummary[]>([]);
  const [profileId, setProfileId] = useState<string | null>(null);
  const [draft, setDraft] = useState<WidgetBrandingProfileInput>({ ...DEFAULT_PROFILE });
  const [dirty, setDirty] = useState(false);
  const [deploymentId, setDeploymentId] = useState("");
  const [confirmPublish, setConfirmPublish] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const manageableOrganizations = organizations.filter((item) => MANAGER_ROLES.has(item.role));
  const selectedProfile = profiles.find((item) => item.id === profileId) ?? null;
  const selectedDeployment = deployments.find((item) => item.id === deploymentId) ?? null;
  const canPublishToDeployment = selectedDeployment?.publishable === true;

  function clearFeedback() {
    setError("");
    setNotice("");
  }

  function resetEditorState() {
    setProfileId(null);
    setDraft({ ...DEFAULT_PROFILE });
    setDirty(false);
    setDeploymentId("");
    setConfirmPublish(false);
  }

  function updateDraft(patch: Partial<WidgetBrandingProfileInput>) {
    setDraft((current) => ({ ...current, ...patch }));
    setDirty(true);
    setConfirmPublish(false);
    setNotice("");
  }

  async function loadOrganizationWorkspace(
    sessionToken: string,
    nextOrganizationId: string,
  ): Promise<void> {
    const [nextProfiles, nextDeployments] = await Promise.all([
      listBrandingProfiles(apiBaseUrl, sessionToken, nextOrganizationId),
      listWidgetDeployments(apiBaseUrl, sessionToken, nextOrganizationId),
    ]);
    setOrganizationId(nextOrganizationId);
    setProfiles(nextProfiles);
    setDeployments(nextDeployments);
    resetEditorState();
  }

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    clearFeedback();
    setBusy(true);
    try {
      const issuedToken = await loginManagementSession(apiBaseUrl, email.trim(), password);
      const allOrganizations = await listManagementOrganizations(apiBaseUrl, issuedToken);
      const manageable = allOrganizations.filter((item) => MANAGER_ROLES.has(item.role));
      setToken(issuedToken);
      setOrganizations(allOrganizations);
      if (manageable.length > 0) {
        await loadOrganizationWorkspace(issuedToken, manageable[0].id);
      } else {
        setOrganizationId("");
        setProfiles([]);
        setDeployments([]);
        setNotice("Bu hesapta widget branding yönetebilen owner/admin organizasyonu bulunmuyor.");
        resetEditorState();
      }
    } catch (caught) {
      setToken(null);
      setOrganizations([]);
      setOrganizationId("");
      setProfiles([]);
      setDeployments([]);
      resetEditorState();
      setError(userMessage(caught));
    } finally {
      setPassword("");
      setBusy(false);
    }
  }

  async function selectOrganization(nextOrganizationId: string) {
    if (token === null) return;
    clearFeedback();
    setBusy(true);
    try {
      await loadOrganizationWorkspace(token, nextOrganizationId);
    } catch (caught) {
      setError(userMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  function startNewProfile() {
    clearFeedback();
    setProfileId(null);
    setDraft({ ...DEFAULT_PROFILE });
    setDirty(false);
    setConfirmPublish(false);
  }

  function selectProfile(nextProfile: WidgetBrandingProfile) {
    clearFeedback();
    setProfileId(nextProfile.id);
    setDraft(profileInput(nextProfile));
    setDirty(false);
    setConfirmPublish(false);
  }

  async function handleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (token === null || organizationId === "") return;
    clearFeedback();
    if (draft.name.trim().length === 0) {
      setError("Profil adı boş bırakılamaz.");
      return;
    }
    setBusy(true);
    try {
      const payload = { ...draft, name: draft.name.trim() };
      const saved =
        profileId === null
          ? await createBrandingProfile(apiBaseUrl, token, organizationId, payload)
          : await updateBrandingProfile(apiBaseUrl, token, organizationId, profileId, payload);
      const nextProfiles =
        profileId === null
          ? [...profiles, saved]
          : profiles.map((profile) => (profile.id === saved.id ? saved : profile));
      setProfiles(nextProfiles);
      setProfileId(saved.id);
      setDraft(profileInput(saved));
      setDirty(false);
      setConfirmPublish(false);
      setNotice(`Taslak kaydedildi. Revision ${saved.revision}. Canlı widget henüz değişmedi.`);
    } catch (caught) {
      setError(userMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function handlePublish(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (token === null || organizationId === "" || profileId === null) return;
    clearFeedback();
    if (dirty) {
      setError("Yayınlamadan önce taslak değişikliklerini kaydedin.");
      return;
    }
    if (selectedDeployment === null || !selectedDeployment.publishable) {
      setConfirmPublish(false);
      setError("Yalnız aktif ve kaynağı revoke edilmemiş bir widget deployment yayın hedefi olabilir.");
      return;
    }
    if (!confirmPublish) {
      setError("Canlı görünümü değiştireceğinizi onaylamanız gerekiyor.");
      return;
    }
    setBusy(true);
    try {
      const receipt = await publishBrandingProfile(
        apiBaseUrl,
        token,
        organizationId,
        selectedDeployment.id,
        profileId,
      );
      setConfirmPublish(false);
      setNotice(
        `Presentation yayınlandı. Profil revision ${receipt.profile_revision} artık ${selectedDeployment.name} deployment'ı için aktif.`,
      );
    } catch (caught) {
      setConfirmPublish(false);
      setError(userMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  function logout() {
    setToken(null);
    setOrganizations([]);
    setOrganizationId("");
    setProfiles([]);
    setDeployments([]);
    resetEditorState();
    setEmail("");
    setPassword("");
    setError("");
    setNotice("Oturum yalnız bellekte tutuldu ve temizlendi.");
  }

  if (token === null) {
    return (
      <section className={styles.panel} aria-labelledby="management-login-title">
        <div className={styles.panelHeading}>
          <p className={styles.kicker}>Yönetim oturumu</p>
          <h2 id="management-login-title">Branding profillerini yönet</h2>
          <p>
            Bearer oturumu yalnız bu sayfanın belleğinde tutulur; tarayıcı kalıcı depolamasına
            yazılmaz.
          </p>
        </div>
        <form className={styles.form} onSubmit={handleLogin}>
          <label className={styles.field}>
            <span>E-posta</span>
            <input
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </label>
          <label className={styles.field}>
            <span>Parola</span>
            <input
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
          <button className={styles.primaryButton} type="submit" disabled={busy}>
            {busy ? "Bağlanıyor…" : "Güvenli oturum aç"}
          </button>
        </form>
        <Feedback error={error} notice={notice} />
      </section>
    );
  }

  return (
    <section className={styles.workspace} aria-labelledby="branding-workspace-title">
      <div className={styles.toolbar}>
        <div>
          <p className={styles.kicker}>Authenticated management</p>
          <h2 id="branding-workspace-title">Widget branding çalışma alanı</h2>
        </div>
        <button className={styles.secondaryButton} type="button" onClick={logout} disabled={busy}>
          Oturumu kapat
        </button>
      </div>

      <Feedback error={error} notice={notice} />

      {manageableOrganizations.length > 0 ? (
        <>
          <label className={styles.field}>
            <span>Organizasyon</span>
            <select
              value={organizationId}
              onChange={(event) => void selectOrganization(event.target.value)}
              disabled={busy}
            >
              {manageableOrganizations.map((organization) => (
                <option key={organization.id} value={organization.id}>
                  {organization.legal_name} · {organization.role}
                </option>
              ))}
            </select>
          </label>

          <div className={styles.grid}>
            <aside className={styles.profileList} aria-label="Branding profilleri">
              <div className={styles.listHeading}>
                <h3>Profiller</h3>
                <button
                  type="button"
                  className={styles.secondaryButton}
                  onClick={startNewProfile}
                  disabled={busy}
                >
                  Yeni profil
                </button>
              </div>
              {profiles.length === 0 ? (
                <p className={styles.muted}>Henüz kayıtlı branding profili yok.</p>
              ) : (
                <ul>
                  {profiles.map((profile) => (
                    <li key={profile.id}>
                      <button
                        type="button"
                        className={profile.id === profileId ? styles.selectedProfile : styles.profileButton}
                        onClick={() => selectProfile(profile)}
                        disabled={busy}
                      >
                        <strong>{profile.name}</strong>
                        <span>Revision {profile.revision}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </aside>

            <div className={styles.editorColumn}>
              <form className={styles.card} onSubmit={handleSave}>
                <div className={styles.cardHeading}>
                  <div>
                    <p className={styles.kicker}>{profileId === null ? "Yeni taslak" : "Taslak düzenle"}</p>
                    <h3>{profileId === null ? "Branding profili oluştur" : selectedProfile?.name}</h3>
                  </div>
                  {dirty ? <span className={styles.dirtyBadge}>Kaydedilmemiş değişiklik</span> : null}
                </div>

                <div className={styles.formGrid}>
                  <label className={styles.fieldWide}>
                    <span>Profil adı</span>
                    <input
                      type="text"
                      maxLength={160}
                      required
                      value={draft.name}
                      onChange={(event) => updateDraft({ name: event.target.value })}
                    />
                  </label>
                  <SelectField label="Tema" value={draft.theme} options={["auto", "light", "dark"]} onChange={(value) => updateDraft({ theme: value as WidgetBrandingProfileInput["theme"] })} />
                  <SelectField label="Dil" value={draft.locale} options={["tr", "en"]} onChange={(value) => updateDraft({ locale: value as WidgetBrandingProfileInput["locale"] })} />
                  <SelectField label="Yoğunluk" value={draft.density} options={["comfortable", "compact"]} onChange={(value) => updateDraft({ density: value as WidgetBrandingProfileInput["density"] })} />
                  <SelectField label="Font ailesi" value={draft.font_family} options={["system", "sans", "serif", "monospace"]} onChange={(value) => updateDraft({ font_family: value as WidgetBrandingProfileInput["font_family"] })} />
                  <label className={styles.field}>
                    <span>Köşe yarıçapı: {draft.border_radius_px}px</span>
                    <input type="range" min="0" max="32" step="1" value={draft.border_radius_px} onChange={(event) => updateDraft({ border_radius_px: event.target.valueAsNumber })} />
                  </label>
                  <label className={styles.checkboxField}>
                    <input type="checkbox" checked={draft.show_title} onChange={(event) => updateDraft({ show_title: event.target.checked })} />
                    <span>Başlığı göster</span>
                  </label>
                </div>

                <fieldset className={styles.colorSet}>
                  <legend>Açık tema</legend>
                  <ColorField label="Arka plan" value={draft.light_background_color} onChange={(value) => updateDraft({ light_background_color: value })} />
                  <ColorField label="Metin" value={draft.light_text_color} onChange={(value) => updateDraft({ light_text_color: value })} />
                  <ColorField label="Çerçeve" value={draft.light_border_color} onChange={(value) => updateDraft({ light_border_color: value })} />
                </fieldset>

                <fieldset className={styles.colorSet}>
                  <legend>Koyu tema</legend>
                  <ColorField label="Arka plan" value={draft.dark_background_color} onChange={(value) => updateDraft({ dark_background_color: value })} />
                  <ColorField label="Metin" value={draft.dark_text_color} onChange={(value) => updateDraft({ dark_text_color: value })} />
                  <ColorField label="Çerçeve" value={draft.dark_border_color} onChange={(value) => updateDraft({ dark_border_color: value })} />
                </fieldset>

                <fieldset className={styles.colorSet}>
                  <legend>Durum</legend>
                  <ColorField label="Hata rengi" value={draft.error_color} onChange={(value) => updateDraft({ error_color: value })} />
                </fieldset>

                <div className={styles.actions}>
                  <button className={styles.primaryButton} type="submit" disabled={busy}>
                    {profileId === null ? "Taslağı oluştur" : "Taslağı kaydet"}
                  </button>
                  <span className={styles.muted}>Kaydetme işlemi canlı widget'ı değiştirmez.</span>
                </div>
              </form>

              <form className={styles.publishCard} onSubmit={handlePublish}>
                <div className={styles.cardHeading}>
                  <div>
                    <p className={styles.kicker}>Explicit publish</p>
                    <h3>Canlı presentation yayınla</h3>
                  </div>
                  <span className={styles.warningBadge}>Ayrı işlem</span>
                </div>
                <p className={styles.muted}>
                  Yalnız kaydedilmiş revision ve bu organizasyondan keşfedilen aktif deployment
                  yayınlanabilir. Disabled veya kaynağı revoke edilmiş deployment'lar yalnız durum
                  görünürlüğü için listelenir.
                </p>
                <label className={styles.fieldWide}>
                  <span>Widget deployment</span>
                  <select
                    value={deploymentId}
                    onChange={(event) => {
                      setDeploymentId(event.target.value);
                      setConfirmPublish(false);
                    }}
                    disabled={busy || deployments.length === 0}
                  >
                    <option value="">Deployment seçin</option>
                    {deployments.map((deployment) => (
                      <option key={deployment.id} value={deployment.id} disabled={!deployment.publishable}>
                        {deployment.name} · {deployment.publishable ? "aktif" : "yayınlanamaz"}
                      </option>
                    ))}
                  </select>
                </label>
                {deployments.length === 0 ? (
                  <p className={styles.muted}>Bu organizasyonda keşfedilmiş widget deployment bulunmuyor.</p>
                ) : null}
                {selectedDeployment !== null && !selectedDeployment.publishable ? (
                  <p className={styles.muted} role="status">
                    Bu deployment disabled veya kaynak projection revoke edilmiş olduğu için yayın hedefi olamaz.
                  </p>
                ) : null}
                <label className={styles.confirmField}>
                  <input
                    type="checkbox"
                    checked={confirmPublish}
                    onChange={(event) => setConfirmPublish(event.target.checked)}
                    disabled={profileId === null || dirty || !canPublishToDeployment}
                  />
                  <span>Bu işlem seçili kaydedilmiş revision'ı canlı widget görünümüne yayınlar.</span>
                </label>
                <button
                  className={styles.dangerButton}
                  type="submit"
                  disabled={busy || profileId === null || dirty || !canPublishToDeployment || !confirmPublish}
                >
                  Canlı presentation'ı yayınla
                </button>
              </form>
            </div>
          </div>
        </>
      ) : null}
    </section>
  );
}

function Feedback({ error, notice }: Readonly<{ error: string; notice: string }>) {
  if (error !== "") return <p className={styles.errorMessage} role="alert">{error}</p>;
  if (notice !== "") return <p className={styles.noticeMessage} role="status">{notice}</p>;
  return <div className={styles.feedbackSpacer} aria-hidden="true" />;
}

function SelectField({
  label,
  value,
  options,
  onChange,
}: Readonly<{
  label: string;
  value: string;
  options: readonly string[];
  onChange: (value: string) => void;
}>) {
  return (
    <label className={styles.field}>
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </label>
  );
}

function ColorField({
  label,
  value,
  onChange,
}: Readonly<{ label: string; value: string; onChange: (value: string) => void }>) {
  return (
    <label className={styles.colorField}>
      <span>{label}</span>
      <span className={styles.colorControl}>
        <input type="color" value={value} onChange={(event) => onChange(event.target.value)} />
        <code>{value.toUpperCase()}</code>
      </span>
    </label>
  );
}
