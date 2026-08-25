const els = {
  form: document.getElementById("crawlForm"),
  taskTopic: document.getElementById("taskTopic"),
  keywords: document.getElementById("keywords"),
  region: document.getElementById("region"),
  minRealResults: document.getElementById("minRealResults"),
  timeRange: document.getElementById("timeRange"),
  customDateRange: document.getElementById("customDateRange"),
  startDate: document.getElementById("startDate"),
  endDate: document.getElementById("endDate"),
  collectLevel: document.getElementById("collectLevel"),
  stableSources: document.getElementById("stableSources"),
  socialPlatforms: document.getElementById("socialPlatforms"),
  siteSessionCard: document.getElementById("siteSessionCard"),
  siteLoginUrl: document.getElementById("siteLoginUrl"),
  siteSessionBadge: document.getElementById("siteSessionBadge"),
  siteSessionStatus: document.getElementById("siteSessionStatus"),
  openSiteLoginBtn: document.getElementById("openSiteLoginBtn"),
  saveSiteSessionBtn: document.getElementById("saveSiteSessionBtn"),
  closeSiteLoginBtn: document.getElementById("closeSiteLoginBtn"),
  clearSiteSessionBtn: document.getElementById("clearSiteSessionBtn"),
  accountGrid: document.getElementById("accountGrid"),
  toggleAccounts: document.getElementById("toggleAccounts"),
  testAllAccountsBtn: document.getElementById("testAllAccountsBtn"),
  useSystemProxy: document.getElementById("useSystemProxy"),
  saveDiagnostics: document.getElementById("saveDiagnostics"),
  crawlBtn: document.getElementById("crawlBtn"),
  monitorInterval: document.getElementById("monitorInterval"),
  monitorBtn: document.getElementById("monitorBtn"),
  monitorRefreshBtn: document.getElementById("monitorRefreshBtn"),
  monitorPlanList: document.getElementById("monitorPlanList"),
  monitorDetail: document.getElementById("monitorDetail"),
  monitorPlanCount: document.getElementById("monitorPlanCount"),
  monitorNewCount: document.getElementById("monitorNewCount"),
  monitorAttentionCount: document.getElementById("monitorAttentionCount"),
  navMonitorCount: document.getElementById("navMonitorCount"),
  refreshBtn: document.getElementById("refreshBtn"),
  currentUser: document.getElementById("currentUser"),
  accountSecurityBtn: document.getElementById("accountSecurityBtn"),
  logoutBtn: document.getElementById("logoutBtn"),
  reportPreviewBtn: document.getElementById("reportPreviewBtn"),
  reportBtn: document.getElementById("reportBtn"),
  selectAllRows: document.getElementById("selectAllRows"),
  invertRows: document.getElementById("invertRows"),
  saveReviewBtn: document.getElementById("saveReviewBtn"),
  reviewSourceFilter: document.getElementById("reviewSourceFilter"),
  reviewCategoryFilter: document.getElementById("reviewCategoryFilter"),
  reviewSentimentFilter: document.getElementById("reviewSentimentFilter"),
  clearReviewFilters: document.getElementById("clearReviewFilters"),
  reviewVisibleCount: document.getElementById("reviewVisibleCount"),
  summarySourceBtn: document.getElementById("summarySourceBtn"),
  summaryFilteredBtn: document.getElementById("summaryFilteredBtn"),
  summaryResult: document.getElementById("summaryResult"),
  templateSelect: document.getElementById("templateSelect"),
  reportPreview: document.getElementById("reportPreview"),
  reportDownload: document.getElementById("reportDownload"),
  reportScopeSummary: document.getElementById("reportScopeSummary"),
  reportScopeDetail: document.getElementById("reportScopeDetail"),
  aiReportPanel: document.getElementById("aiReportPanel"),
  aiProviderState: document.getElementById("aiProviderState"),
  aiProviderModel: document.getElementById("aiProviderModel"),
  aiExternalScope: document.getElementById("aiExternalScope"),
  aiExternalFields: document.getElementById("aiExternalFields"),
  aiExternalSendConfirm: document.getElementById("aiExternalSendConfirm"),
  aiGenerateBtn: document.getElementById("aiGenerateBtn"),
  aiApplyBtn: document.getElementById("aiApplyBtn"),
  aiDiscardBtn: document.getElementById("aiDiscardBtn"),
  aiDraftStatus: document.getElementById("aiDraftStatus"),
  aiDraftEditor: document.getElementById("aiDraftEditor"),
  aiUsage: document.getElementById("aiUsage"),
  dataDownload: document.getElementById("dataDownload"),
  serverStatus: document.getElementById("serverStatus"),
  globalOperationsDock: document.getElementById("globalOperationsDock"),
  globalOperationsToggle: document.getElementById("globalOperationsToggle"),
  globalOperationsBody: document.getElementById("globalOperationsBody"),
  globalOperationsToggleCopy: document.getElementById("globalOperationsToggleCopy"),
  globalRunHeadline: document.getElementById("globalRunHeadline"),
  globalMiniProgress: document.getElementById("globalMiniProgress"),
  globalMiniProgressBar: document.getElementById("globalMiniProgressBar"),
  globalLatestLog: document.getElementById("globalLatestLog"),
  globalLogCount: document.getElementById("globalLogCount"),
  logBox: document.getElementById("logBox"),
  resultBody: document.getElementById("resultBody"),
  realCount: document.getElementById("realCount"),
  stableCount: document.getElementById("stableCount"),
  publicNewsCount: document.getElementById("publicNewsCount"),
  socialCount: document.getElementById("socialCount"),
  qualityStatus: document.getElementById("qualityStatus"),
  qualityChecklist: document.getElementById("qualityChecklist"),
  heatIndex: document.getElementById("heatIndex"),
  qualityNote: document.getElementById("qualityNote"),
  dataPath: document.getElementById("dataPath"),
  complianceNotice: document.getElementById("complianceNotice"),
  taskNote: document.getElementById("taskNote"),
  taskIdLabel: document.getElementById("taskIdLabel"),
  progressBar: document.getElementById("progressBar"),
  eventList: document.getElementById("eventList"),
  sourceHealth: document.getElementById("sourceHealth"),
  taskHistory: document.getElementById("taskHistory"),
  toggleHistoryBtn: document.getElementById("toggleHistoryBtn"),
  historyDetail: document.getElementById("historyDetail"),
  historyDetailTitle: document.getElementById("historyDetailTitle"),
  historyDetailContent: document.getElementById("historyDetailContent"),
  closeHistoryDetail: document.getElementById("closeHistoryDetail"),
  historyArchiveSummary: document.getElementById("historyArchiveSummary"),
  historyArchivePreview: document.getElementById("historyArchivePreview"),
  loadHistoryBtn: document.getElementById("loadHistoryBtn"),
  reuseHistoryBtn: document.getElementById("reuseHistoryBtn"),
  deleteHistoryBtn: document.getElementById("deleteHistoryBtn"),
  createHistoryBackupBtn: document.getElementById("createHistoryBackupBtn"),
  restoreHistoryBackupBtn: document.getElementById("restoreHistoryBackupBtn"),
  historyTrashCount: document.getElementById("historyTrashCount"),
  historyTrashList: document.getElementById("historyTrashList"),
  historyBackupDialog: document.getElementById("historyBackupDialog"),
  historyBackupForm: document.getElementById("historyBackupForm"),
  historyBackupPassphrase: document.getElementById("historyBackupPassphrase"),
  historyBackupPassphraseConfirm: document.getElementById("historyBackupPassphraseConfirm"),
  confirmHistoryBackupBtn: document.getElementById("confirmHistoryBackupBtn"),
  historyRestoreDialog: document.getElementById("historyRestoreDialog"),
  historyRestoreForm: document.getElementById("historyRestoreForm"),
  historyRestoreFile: document.getElementById("historyRestoreFile"),
  historyRestorePassphrase: document.getElementById("historyRestorePassphrase"),
  confirmHistoryRestoreBtn: document.getElementById("confirmHistoryRestoreBtn"),
  accountSecurityDialog: document.getElementById("accountSecurityDialog"),
  accountSecurityUsername: document.getElementById("accountSecurityUsername"),
  accountRecoveryStatus: document.getElementById("accountRecoveryStatus"),
  changePasswordForm: document.getElementById("changePasswordForm"),
  currentPassword: document.getElementById("currentPassword"),
  newPassword: document.getElementById("newPassword"),
  newPasswordConfirm: document.getElementById("newPasswordConfirm"),
  changePasswordMessage: document.getElementById("changePasswordMessage"),
  changePasswordBtn: document.getElementById("changePasswordBtn"),
  recoveryCodeForm: document.getElementById("recoveryCodeForm"),
  recoveryCurrentPassword: document.getElementById("recoveryCurrentPassword"),
  recoveryCodeMessage: document.getElementById("recoveryCodeMessage"),
  recoveryCodeBtn: document.getElementById("recoveryCodeBtn"),
  accountRecoveryResult: document.getElementById("accountRecoveryResult"),
  accountRecoveryCode: document.getElementById("accountRecoveryCode"),
  copyAccountRecoveryCode: document.getElementById("copyAccountRecoveryCode"),
  viewTitle: document.getElementById("viewTitle"),
  viewHint: document.getElementById("viewHint"),
  selectedSourceSummary: document.getElementById("selectedSourceSummary"),
  navResultCount: document.getElementById("navResultCount"),
  navAccountCount: document.getElementById("navAccountCount"),
  sourceLogBox: document.getElementById("sourceLogBox"),
  sourceLogState: document.getElementById("sourceLogState"),
  clearSourceLogBtn: document.getElementById("clearSourceLogBtn"),
};

const state = {
  options: null,
  latest: null,
  taskId: null,
  taskPoll: null,
  monitorPlans: [],
  selectedMonitorId: null,
  monitorPoll: null,
  savedAccounts: {},
  siteSessions: {},
  reportDraft: null,
  aiDisclosure: null,
  aiDraft: null,
  aiRequestPending: false,
  appliedAiReportScopeToken: "",
  summaryDraft: null,
  activeView: "task",
  historyItems: [],
  historyTrash: [],
  historySummary: {},
  historyExpanded: false,
  selectedHistoryId: null,
  selectedHistoryDetail: null,
  globalOperationsExpanded: false,
  globalLogCount: 0,
  authIdentity: null,
  recoveryConfigured: false,
};

const COLLECT_LEVEL_COPY = {
  最小采集: { label: "最多 10 条 · 功能测试", maximum: 10, automaticMinimum: 10 },
  快速采集: { label: "最多 20 条 · 快速查看", maximum: 20, automaticMinimum: 20 },
  标准采集: { label: "最多 50 条 · 日常任务", maximum: 50, automaticMinimum: 30 },
  深度采集: { label: "最多 100 条 · 较大范围", maximum: 100, automaticMinimum: 50 },
};

const VIEW_COPY = {
  task: ["新建采集任务", "填写任务主题、关键词和检索范围"],
  overview: ["运行态势", "查看采集检查、来源健康和任务历史"],
  review: ["数据审核", "筛选并修订可进入报告的记录"],
  sources: ["来源与账号", "管理采集范围、登录会话和访问边界"],
  monitor: ["持续监测", "查看新增线索、计划运行状态和需要人工处理的问题"],
  report: ["报告中心", "核对采集与证据检查后生成 Word 通报"],
};

const TASK_STATUS_COPY = {
  done: "已完成",
  error: "失败",
  blocked: "访问受阻",
  not_met: "结果不足",
  queued: "等待开始",
  running: "采集中",
};

const SOURCE_STRATEGY_COPY = {
  all: "全部独立采集",
  stable_first: "全部独立采集（旧任务）",
  hybrid: "全部独立采集（旧任务）",
  stable: "只查政府官网",
  public_news: "只查公开新闻",
  social: "只查社交平台",
};

function activateView(name, updateHash = true) {
  const target = VIEW_COPY[name] ? name : "task";
  state.activeView = target;
  document.querySelectorAll("[data-view-panel]").forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.viewPanel === target);
  });
  document.querySelectorAll("[data-view-target]").forEach((button) => {
    const active = button.dataset.viewTarget === target;
    button.classList.toggle("active", active);
    if (button.classList.contains("nav-item")) {
      button.setAttribute("aria-current", active ? "page" : "false");
    }
  });
  const [title, hint] = VIEW_COPY[target];
  if (els.viewTitle) els.viewTitle.textContent = title;
  if (els.viewHint) els.viewHint.textContent = hint;
  if (updateHash) history.replaceState(null, "", `#${target}`);
  if (target === "monitor" && state.options) {
    loadMonitors().catch((error) => addLog(`监测状态刷新失败：${error.message}`));
  }
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function setStatus(text, type = "ready") {
  const indicator = document.createElement("span");
  indicator.className = "status-indicator";
  indicator.setAttribute("aria-hidden", "true");
  const label = document.createElement("span");
  label.textContent = text;
  els.serverStatus.replaceChildren(indicator, label);
  els.serverStatus.classList.toggle("busy", type === "busy");
  els.serverStatus.classList.toggle("error", type === "error");
  els.globalRunHeadline.textContent = text;
  els.globalOperationsDock.classList.toggle("busy", type === "busy");
  els.globalOperationsDock.classList.toggle("error", type === "error");
}

function addLog(message) {
  els.logBox.querySelector(".log-placeholder")?.remove();
  const line = document.createElement("div");
  line.className = "log-line";
  const time = new Date().toLocaleTimeString("zh-CN", { hour12: false });
  line.textContent = `[${time}] ${message}`;
  els.logBox.prepend(line);
  state.globalLogCount += 1;
  els.globalLatestLog.textContent = message;
  els.globalLatestLog.title = message;
  els.globalLogCount.textContent = `${state.globalLogCount} 条日志`;
}

function setTaskProgress(percent) {
  const normalized = Math.max(0, Math.min(100, Number(percent) || 0));
  els.progressBar.style.width = `${normalized}%`;
  els.globalMiniProgressBar.style.width = `${normalized}%`;
  els.globalMiniProgress.setAttribute("aria-valuenow", String(normalized));
}

function setGlobalOperationsExpanded(expanded) {
  state.globalOperationsExpanded = Boolean(expanded);
  els.globalOperationsDock.classList.toggle("expanded", state.globalOperationsExpanded);
  els.globalOperationsToggle.setAttribute("aria-expanded", String(state.globalOperationsExpanded));
  els.globalOperationsBody.hidden = !state.globalOperationsExpanded;
  els.globalOperationsToggleCopy.textContent = state.globalOperationsExpanded ? "收起" : "展开";
}

function addSourceLog(message, tone = "info") {
  addLog(message);
  if (!els.sourceLogBox || !els.sourceLogState) return;

  els.sourceLogBox.querySelector(".source-log-empty")?.remove();
  const labels = {
    success: "成功",
    error: "失败",
    warning: "注意",
    info: "信息",
  };
  const line = document.createElement("div");
  line.className = `source-log-line ${tone}`;

  const meta = document.createElement("div");
  meta.className = "source-log-meta";
  const badge = document.createElement("span");
  badge.className = "source-log-badge";
  badge.textContent = labels[tone] || labels.info;
  const time = document.createElement("time");
  time.dateTime = new Date().toISOString();
  time.textContent = new Date().toLocaleTimeString("zh-CN", { hour12: false });
  meta.append(badge, time);

  const text = document.createElement("p");
  text.textContent = message;
  line.append(meta, text);
  els.sourceLogBox.prepend(line);

  [...els.sourceLogBox.querySelectorAll(".source-log-line")].slice(40).forEach((item) => item.remove());
  els.sourceLogState.className = `source-log-state ${tone}`;
  els.sourceLogState.lastElementChild.textContent =
    tone === "success" ? "最近操作成功" : tone === "error" ? "最近操作失败" : tone === "warning" ? "需要注意" : "正在处理";
}

function clearSourceLog() {
  if (!els.sourceLogBox || !els.sourceLogState) return;
  els.sourceLogBox.innerHTML = '<div class="source-log-empty">日志已清空，后续操作结果会继续显示在这里。</div>';
  els.sourceLogState.className = "source-log-state";
  els.sourceLogState.lastElementChild.textContent = "等待操作";
}

async function requestJson(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json();
  if (response.status === 401 && payload.code === "authentication_required") {
    location.replace("/login");
    throw new Error("系统登录已失效，请重新登录");
  }
  if (!response.ok || payload.ok === false) {
    throw new Error(payload.message || `请求失败: ${response.status}`);
  }
  return payload;
}

async function loadIdentity() {
  const status = await requestJson("/api/auth/status");
  if (!status.authenticated || !status.user) {
    location.replace("/login");
    throw new Error("请先登录系统账号");
  }
  state.authIdentity = status.user;
  state.recoveryConfigured = Boolean(status.recovery_configured);
  els.currentUser.textContent = `${status.user.username} · ${status.user.role}`;
}

async function logoutSystem() {
  els.logoutBtn.disabled = true;
  try {
    await requestJson("/api/auth/logout", { method: "POST", body: "{}" });
  } finally {
    location.replace("/login");
  }
}

function renderAccountSecurityStatus() {
  els.accountSecurityUsername.textContent = state.authIdentity?.username || "—";
  els.accountRecoveryStatus.textContent = state.recoveryConfigured ? "恢复码已设置" : "尚未设置恢复码";
}

function openAccountSecurity() {
  els.changePasswordForm.reset();
  els.recoveryCodeForm.reset();
  els.changePasswordMessage.textContent = "";
  els.recoveryCodeMessage.textContent = "";
  els.accountRecoveryCode.textContent = "";
  els.accountRecoveryResult.classList.add("hidden");
  renderAccountSecurityStatus();
  openHistoryDialog(els.accountSecurityDialog);
  els.currentPassword.focus();
}

async function changeSystemPassword(event) {
  event.preventDefault();
  els.newPasswordConfirm.setCustomValidity("");
  if (els.newPassword.value !== els.newPasswordConfirm.value) {
    els.newPasswordConfirm.setCustomValidity("两次输入的新密码不一致");
    els.newPasswordConfirm.reportValidity();
    return;
  }
  els.changePasswordBtn.disabled = true;
  els.changePasswordMessage.textContent = "正在修改密码…";
  try {
    const result = await requestJson("/api/auth/change-password", {
      method: "POST",
      body: JSON.stringify({
        current_password: els.currentPassword.value,
        new_password: els.newPassword.value,
        password_confirmation: els.newPasswordConfirm.value,
      }),
    });
    els.changePasswordMessage.textContent = result.message;
    window.setTimeout(() => location.replace("/login"), 650);
  } catch (error) {
    els.changePasswordMessage.textContent = error.message;
    els.changePasswordBtn.disabled = false;
  }
}

async function rotateSystemRecoveryCode(event) {
  event.preventDefault();
  els.recoveryCodeBtn.disabled = true;
  els.recoveryCodeMessage.textContent = "正在生成新的恢复码…";
  els.accountRecoveryResult.classList.add("hidden");
  try {
    const result = await requestJson("/api/auth/recovery-code", {
      method: "POST",
      body: JSON.stringify({ current_password: els.recoveryCurrentPassword.value }),
    });
    state.recoveryConfigured = true;
    renderAccountSecurityStatus();
    els.recoveryCodeMessage.textContent = result.message;
    els.accountRecoveryCode.textContent = result.recovery_code;
    els.accountRecoveryResult.classList.remove("hidden");
    els.recoveryCurrentPassword.value = "";
  } catch (error) {
    els.recoveryCodeMessage.textContent = error.message;
  } finally {
    els.recoveryCodeBtn.disabled = false;
  }
}

async function copySystemRecoveryCode() {
  const recoveryCode = els.accountRecoveryCode.textContent.trim();
  if (!recoveryCode) return;
  try {
    await navigator.clipboard.writeText(recoveryCode);
  } catch (_error) {
    const input = document.createElement("textarea");
    input.value = recoveryCode;
    input.setAttribute("readonly", "");
    input.style.position = "fixed";
    input.style.opacity = "0";
    document.body.appendChild(input);
    input.select();
    document.execCommand("copy");
    input.remove();
  }
  els.copyAccountRecoveryCode.textContent = "已复制";
  window.setTimeout(() => {
    els.copyAccountRecoveryCode.textContent = "复制恢复码";
  }, 1200);
}

function fillSelect(select, values, preferred) {
  select.innerHTML = "";
  values.forEach((value) => {
    const option = document.createElement("option");
    option.value = value.id || value;
    option.textContent = value.name ? `${value.name}` : value;
    if ((value.id || value) === preferred) option.selected = true;
    select.appendChild(option);
  });
}

function renderChecks(container, values, checkedCount) {
  container.innerHTML = "";
  values.forEach((value, index) => {
    const label = document.createElement("label");
    const input = document.createElement("input");
    input.type = "checkbox";
    input.value = value;
    input.checked = index < checkedCount;
    input.addEventListener("change", () => {
      updateSelectButtons();
      updateSourceSummary();
      if (state.options) {
        const groupName = container === els.stableSources ? "政府官网" : "社交平台";
        addSourceLog(`${groupName}已更新：当前选择 ${checkedValues(container).length} 个来源`, "info");
      }
    });
    const text = document.createElement("span");
    text.textContent = value;
    label.append(input, text);
    container.appendChild(label);
  });
  updateSourceSummary();
}

function renderAccounts(platforms, savedAccounts = {}) {
  els.accountGrid.innerHTML = "";
  platforms.forEach((platform) => {
    const saved = savedAccounts[platform] || {};
    const card = document.createElement("div");
    card.className = "account-card";
    card.dataset.platform = platform;

    const header = document.createElement("div");
    header.className = "account-card-header";
    const title = document.createElement("h3");
    title.textContent = platform;
    const status = document.createElement("span");
    status.className = `account-badge ${saved.saved ? "saved" : ""}`;
    status.dataset.role = "account-status-badge";
    header.append(title, status);

    const fields = document.createElement("div");
    fields.className = "account-fields";

    const username = document.createElement("input");
    username.type = "text";
    username.placeholder = saved.username_saved ? `${saved.username_hint}，重新填写可覆盖` : "用户名 / 账号备注";
    username.dataset.field = "username";

    const password = document.createElement("input");
    password.type = "password";
    password.placeholder = saved.password_saved ? "已保存密码，重新填写可覆盖" : "密码（保留，不自动登录）";
    password.dataset.field = "password";

    const note = document.createElement("input");
    note.type = "text";
    note.placeholder = saved.note_saved ? "已保存备注，重新填写可覆盖" : "备注（可选）";
    note.dataset.field = "note";

    fields.append(username, password, note);

    const cookie = document.createElement("textarea");
    cookie.placeholder = saved.cookie_saved ? `${saved.cookie_hint}；重新粘贴可覆盖` : "Cookie（用于登录确认和平台采集）";
    cookie.dataset.field = "cookie";

    const detail = document.createElement("div");
    detail.className = "account-status-detail";
    detail.dataset.role = "account-status-detail";

    const actions = document.createElement("div");
    actions.className = "account-actions";
    const openLoginButton = document.createElement("button");
    openLoginButton.className = "secondary-btn";
    openLoginButton.type = "button";
    openLoginButton.dataset.action = "open-login";
    openLoginButton.textContent = "打开辅助登录";

    const saveBrowserButton = document.createElement("button");
    saveBrowserButton.className = "secondary-btn";
    saveBrowserButton.type = "button";
    saveBrowserButton.dataset.action = "save-browser-session";
    saveBrowserButton.textContent = "保存会话";

    const closeBrowserButton = document.createElement("button");
    closeBrowserButton.className = "ghost-btn";
    closeBrowserButton.type = "button";
    closeBrowserButton.dataset.action = "close-browser-session";
    closeBrowserButton.textContent = "关闭窗口";

    const saveButton = document.createElement("button");
    saveButton.className = "secondary-btn";
    saveButton.type = "button";
    saveButton.dataset.action = "save-account";
    saveButton.textContent = "保存授权";

    const testButton = document.createElement("button");
    testButton.className = "secondary-btn";
    testButton.type = "button";
    testButton.dataset.action = "test-account";
    testButton.textContent = "测试授权";

    const clearButton = document.createElement("button");
    clearButton.className = "ghost-btn";
    clearButton.type = "button";
    clearButton.dataset.action = "clear-account";
    clearButton.textContent = "清除";
    actions.append(openLoginButton, saveBrowserButton, closeBrowserButton, saveButton, testButton, clearButton);

    card.append(header, detail, fields, cookie, actions);
    els.accountGrid.appendChild(card);
    updateAccountCardStatus(card, saved);
  });
  updateAccountSummary(savedAccounts);
}

function updateAccountSummary(accounts = state.savedAccounts) {
  if (!els.navAccountCount) return;
  const socialCount = Object.values(accounts).filter((account) => account && account.saved).length;
  const siteCount = Object.values(state.siteSessions).filter((session) => session && session.saved).length;
  els.navAccountCount.textContent = String(socialCount + siteCount);
}

function normalizedSiteDomain(value) {
  try {
    const parsed = new URL(value);
    if (parsed.protocol !== "https:") return "";
    return parsed.hostname.toLowerCase().replace(/\.$/, "");
  } catch (_) {
    return "";
  }
}

function renderSiteSessionStatus(preferredDomain = "") {
  if (!els.siteSessionStatus) return;
  const domain = preferredDomain || normalizedSiteDomain(els.siteLoginUrl.value.trim());
  const saved = domain ? state.siteSessions[domain] || {} : {};
  const isSaved = !!saved.saved;
  const needsRelogin = saved.needs_relogin === true;
  els.siteSessionBadge.textContent = needsRelogin ? "需要重新登录" : (isSaved ? "已保存" : "未保存");
  els.siteSessionBadge.classList.toggle("saved", isSaved && !needsRelogin);
  els.siteSessionBadge.classList.toggle("needs-login", needsRelogin);
  if (needsRelogin) {
    els.siteSessionStatus.textContent = `${domain}：保存的会话已经失效，需要重新打开辅助登录并保存新会话。`;
  } else if (isSaved) {
    const evidence = [
      saved.browser_cookie_count ? `${saved.browser_cookie_count} 个 Cookie` : "",
      saved.browser_has_local_storage ? "含网页本地会话" : "",
    ].filter(Boolean).join("，");
    els.siteSessionStatus.textContent = `${domain}：会话已加密保存${evidence ? `（${evidence}）` : ""}。同一域名再次保存会覆盖原会话。`;
  } else if (domain) {
    els.siteSessionStatus.textContent = `${domain}：尚未保存会话。同一域名再次保存会覆盖原会话。`;
  } else {
    els.siteSessionStatus.textContent = "填写网站登录页地址；同一域名再次保存会覆盖原会话。";
  }
  updateAccountSummary();
}

function requiredSiteUrl() {
  const siteUrl = els.siteLoginUrl.value.trim();
  els.siteLoginUrl.setCustomValidity("");
  if (!siteUrl || !els.siteLoginUrl.checkValidity() || !normalizedSiteDomain(siteUrl)) {
    els.siteLoginUrl.setCustomValidity("请输入完整的 HTTPS 网站登录页地址");
    els.siteLoginUrl.reportValidity();
    return "";
  }
  return siteUrl;
}

function applySiteSessionResponse(result, siteUrl) {
  state.siteSessions = result.site_sessions || state.siteSessions;
  const domain = result.saved?.domain || result.session?.domain || normalizedSiteDomain(siteUrl);
  renderSiteSessionStatus(domain);
}

async function openSiteLogin() {
  const siteUrl = requiredSiteUrl();
  if (!siteUrl) return;
  els.openSiteLoginBtn.disabled = true;
  try {
    const result = await requestJson("/api/browser-login/start", {
      method: "POST",
      body: JSON.stringify({ site_url: siteUrl, use_system_proxy: els.useSystemProxy.checked }),
    });
    applySiteSessionResponse(result, siteUrl);
    addSourceLog(`${normalizedSiteDomain(siteUrl)}: 辅助登录浏览器已打开，请人工完成登录后保存会话`, "success");
  } catch (error) {
    addSourceLog(`网站辅助登录打开失败：${error.message}`, "error");
  } finally {
    els.openSiteLoginBtn.disabled = false;
  }
}

async function saveSiteSession() {
  const siteUrl = requiredSiteUrl();
  if (!siteUrl) return;
  els.saveSiteSessionBtn.disabled = true;
  els.saveSiteSessionBtn.textContent = "保存中";
  try {
    const result = await requestJson("/api/browser-login/save", {
      method: "POST",
      body: JSON.stringify({ site_url: siteUrl }),
    });
    applySiteSessionResponse(result, siteUrl);
    addSourceLog(`${normalizedSiteDomain(siteUrl)}: 登录会话已加密保存，同域名旧会话已覆盖`, "success");
  } catch (error) {
    addSourceLog(`网站会话保存失败：${error.message}`, "error");
  } finally {
    els.saveSiteSessionBtn.disabled = false;
    els.saveSiteSessionBtn.textContent = "保存会话";
  }
}

async function closeSiteLogin() {
  const siteUrl = requiredSiteUrl();
  if (!siteUrl) return;
  els.closeSiteLoginBtn.disabled = true;
  try {
    const result = await requestJson("/api/browser-login/close", {
      method: "POST",
      body: JSON.stringify({ site_url: siteUrl }),
    });
    applySiteSessionResponse(result, siteUrl);
    addSourceLog(`${normalizedSiteDomain(siteUrl)}: ${result.message || "辅助登录浏览器已关闭"}`, "success");
  } catch (error) {
    addSourceLog(`网站辅助登录窗口关闭失败：${error.message}`, "error");
  } finally {
    els.closeSiteLoginBtn.disabled = false;
  }
}

async function clearSiteSession() {
  const siteUrl = requiredSiteUrl();
  if (!siteUrl) return;
  els.clearSiteSessionBtn.disabled = true;
  try {
    const result = await requestJson("/api/accounts/clear", {
      method: "POST",
      body: JSON.stringify({ site_url: siteUrl }),
    });
    applySiteSessionResponse(result, siteUrl);
    addSourceLog(`${normalizedSiteDomain(siteUrl)}: 登录会话已清除`, "success");
  } catch (error) {
    addSourceLog(`网站会话清除失败：${error.message}`, "error");
  } finally {
    els.clearSiteSessionBtn.disabled = false;
  }
}

function updateAccountCardStatus(card, saved = {}) {
  const badge = card.querySelector("[data-role='account-status-badge']");
  const detail = card.querySelector("[data-role='account-status-detail']");
  const last = saved.last_test || {};
  const parts = [];
  if (saved.cookie_saved) parts.push("Cookie 已保存");
  if (saved.browser_session_saved) {
    parts.push(`浏览器会话已保存${saved.browser_cookie_count ? `(${saved.browser_cookie_count} Cookie)` : ""}`);
  }
  if (saved.password_saved) parts.push("密码已保存");
  if (saved.username_saved) parts.push("账号名已保存");
  if (!parts.length) parts.push("未保存授权");

  badge.textContent = saved.saved ? "已保存" : "未保存";
  badge.classList.toggle("saved", !!saved.saved);

  const testState = platformTestState(last);
  const testText = last.tested_at
    ? `最近测试: 登录${testState.loginPassed ? "通过" : "未通过"} · 采集${testState.readPassed ? `通过（${testState.count} 条）` : "未通过"} · 结论${testState.passed ? "完全通过" : "未通过"}${last.error ? `，原因: ${last.error}` : ""}`
    : "尚未测试";
  detail.textContent = `${parts.join(" / ")}。${testText}`;
}

function platformTestState(result = {}) {
  const loginPassed = result.login_passed === true || result.login_confirmed === true;
  const count = Number(result.parsed_count || 0);
  const readPassed = result.read_passed === true || count > 0;
  return {
    loginPassed,
    readPassed,
    passed: loginPassed && readPassed,
    count,
  };
}

function describeLoginStatus(result = {}) {
  if (result.login_confirmed === true) return "当前登录通过";
  if (result.login_confirmed === false) return "当前登录未通过";
  return "当前登录未确认";
}

function updateSelectButtons() {
  document.querySelectorAll("[data-select]").forEach((button) => {
    const target = button.dataset.select === "stable" ? els.stableSources : els.socialPlatforms;
    const inputs = [...target.querySelectorAll("input")];
    const allChecked = inputs.length > 0 && inputs.every((input) => input.checked);
    button.textContent = allChecked ? "取消" : "全选";
  });
}

function updateSourceSummary() {
  if (!els.selectedSourceSummary || !els.stableSources || !els.socialPlatforms) return;
  const stable = checkedValues(els.stableSources);
  const social = checkedValues(els.socialPlatforms);
  const publicNews = state.options?.public_news_sources?.length || 0;
  const strategy = selectedStrategy();
  const parts = [];
  if (strategy === "all" || strategy === "stable") parts.push(`政府官网 ${stable.length} 个`);
  if (strategy === "all" || strategy === "public_news") parts.push(`公开新闻 ${publicNews} 个`);
  if (strategy === "all" || strategy === "social") parts.push(`社交平台 ${social.length} 个`);
  els.selectedSourceSummary.textContent = parts.join(" · ") || "尚未选择采集来源";
}

function checkedValues(container) {
  return [...container.querySelectorAll("input:checked")].map((input) => input.value);
}

function collectAccounts() {
  const accounts = {};
  els.accountGrid.querySelectorAll(".account-card").forEach((card) => {
    const platform = card.dataset.platform;
    const { username, password, cookie, note } = accountFromCard(card);
    if (username || password || cookie || note) {
      accounts[platform] = { username, password, cookie, note };
    }
  });
  return accounts;
}

function accountFromCard(card) {
  return {
    username: card.querySelector("[data-field='username']").value.trim(),
    password: card.querySelector("[data-field='password']").value,
    cookie: card.querySelector("[data-field='cookie']").value.trim(),
    note: card.querySelector("[data-field='note']").value.trim(),
  };
}

function selectedStrategy() {
  const input = document.querySelector("input[name='sourceStrategy']:checked");
  return input ? input.value : "all";
}

function toDateInputValue(date) {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 10);
}

function updateCustomDateRange() {
  const isCustom = els.timeRange.value === "自定义";
  els.customDateRange.classList.toggle("hidden", !isCustom);
  els.startDate.required = isCustom;
  els.endDate.required = isCustom;
  els.endDate.setCustomValidity("");
  if (!isCustom) return;

  const now = new Date();
  if (!els.endDate.value) els.endDate.value = toDateInputValue(now);
  if (!els.startDate.value) {
    const sevenDaysAgo = new Date(now);
    sevenDaysAgo.setDate(now.getDate() - 7);
    els.startDate.value = toDateInputValue(sevenDaysAgo);
  }
}

function selectedTimeRange() {
  if (els.timeRange.value !== "自定义") return els.timeRange.value;
  return `${els.startDate.value} 至 ${els.endDate.value}`;
}

function validateTaskForm() {
  els.endDate.setCustomValidity("");
  els.minRealResults.setCustomValidity("");
  if (
    els.timeRange.value === "自定义" &&
    els.startDate.value &&
    els.endDate.value &&
    els.startDate.value > els.endDate.value
  ) {
    els.endDate.setCustomValidity("结束日期不能早于开始日期");
  }
  const level = COLLECT_LEVEL_COPY[els.collectLevel.value];
  if (
    level &&
    els.minRealResults.value &&
    Number(els.minRealResults.value) > level.maximum
  ) {
    els.minRealResults.setCustomValidity(`不能超过整个任务的 ${level.maximum} 条上限`);
  }
  return els.form.reportValidity();
}

function updateCollectionLimitCopy() {
  const level = COLLECT_LEVEL_COPY[els.collectLevel.value];
  if (!level) return;
  els.minRealResults.max = String(level.maximum);
  els.minRealResults.placeholder = `自动：${level.automaticMinimum} 条`;
  els.minRealResults.setCustomValidity("");
}

function collectPayload(overrides = {}) {
  const minReal = els.minRealResults.value.trim();
  return {
    topic: els.taskTopic.value.trim(),
    keywords: els.keywords.value,
    region: els.region.value.trim(),
    time_range: selectedTimeRange(),
    collect_level: els.collectLevel.value,
    source_strategy: selectedStrategy(),
    stable_sources: checkedValues(els.stableSources),
    social_platforms: checkedValues(els.socialPlatforms),
    accounts: collectAccounts(),
    use_system_proxy: els.useSystemProxy.checked,
    enable_debug_snapshots: els.saveDiagnostics.checked,
    min_real_results: minReal ? Number(minReal) : null,
    ...overrides,
  };
}

function setBusy(isBusy) {
  els.crawlBtn.disabled = isBusy;
  els.reportBtn.disabled = isBusy;
  els.refreshBtn.disabled = isBusy;
  els.saveReviewBtn.disabled = isBusy;
}

function updateMetrics(latest) {
  const meta = latest.meta || {};
  const summary = meta.summary || {};
  const heat = latest.heat || {};
  const quality = latest.quality || {};

  els.realCount.textContent = summary.real_count ?? 0;
  els.stableCount.textContent = summary.stable_real_count ?? 0;
  els.publicNewsCount.textContent = summary.public_news_real_count ?? 0;
  els.socialCount.textContent = summary.social_real_count ?? 0;
  const assessment = quality.status_code ? quality : (meta.quality_assessment || {});
  els.qualityStatus.textContent = assessment.status_label || "未检查";
  els.qualityStatus.dataset.status = assessment.status_code || "unchecked";
  els.heatIndex.textContent = heat.heat_index ?? 0;
  els.dataPath.textContent = latest.data_path || "data/latest_news.json";
  if (els.navResultCount) els.navResultCount.textContent = String(summary.real_count ?? 0);

  if (latest.total === 0) {
    els.qualityNote.textContent = "暂无采集数据";
  } else {
    els.qualityNote.textContent = assessment.status_detail || "检查结果暂不可用，请刷新页面。";
  }
  renderQualityChecklist(els.qualityChecklist, assessment.checks || []);

  if (latest.data_path) {
    els.dataDownload.href = `/download?path=${encodeURIComponent(latest.data_path)}`;
  }
}

function renderQualityChecklist(root, checks = []) {
  if (!root) return;
  root.innerHTML = "";
  if (!checks.length) {
    const empty = document.createElement("div");
    empty.className = "quality-check-empty";
    empty.textContent = "暂无检查结果";
    root.appendChild(empty);
    return;
  }
  checks.forEach((check) => {
    const item = document.createElement("div");
    item.className = `quality-check-item ${check.status || "warning"}`;

    const marker = document.createElement("span");
    marker.className = "quality-check-marker";
    marker.textContent = check.status === "pass" ? "✓" : check.status === "fail" ? "×" : "!";

    const body = document.createElement("div");
    body.className = "quality-check-body";
    const heading = document.createElement("div");
    heading.className = "quality-check-heading";
    const label = document.createElement("strong");
    label.textContent = check.label || "检查项";
    const value = document.createElement("span");
    value.textContent = `${check.status_label || "需复核"} · ${check.value || "-"}`;
    heading.append(label, value);

    const detail = document.createElement("small");
    detail.textContent = check.detail || "";
    body.append(heading, detail);
    item.append(marker, body);
    root.appendChild(item);
  });
}

function renderSourceHealth(meta = {}) {
  const health = meta.source_health || [];
  els.sourceHealth.innerHTML = "";
  if (health.length === 0) {
    els.sourceHealth.innerHTML = '<div class="compact-item"><span>暂无源健康数据</span></div>';
    return;
  }
  health.slice(0, 10).forEach((item) => {
    const node = document.createElement("div");
    node.className = `compact-item ${item.status === "failed" ? "failed" : item.status === "ok" ? "ok" : ""}`;
    node.innerHTML = `<strong>${item.channel}</strong><span>${item.status} · 成功 ${item.success_count || 0} · 失败 ${item.failure_count || 0}${item.last_error ? ` · ${item.last_error}` : ""}</span>`;
    els.sourceHealth.appendChild(node);
  });
}

function historyTaskTitle(item = {}) {
  const payload = item.payload || {};
  return payload.topic || (payload.keywords || []).join("、") || "未命名采集任务";
}

function formatHistoryTime(value) {
  if (!value) return "时间未记录";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value).replace("T", " ").slice(0, 19);
  return parsed.toLocaleString("zh-CN", { hour12: false });
}

function formatBytes(value) {
  const bytes = Number(value) || 0;
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function closeHistoryDetail() {
  state.selectedHistoryId = null;
  state.selectedHistoryDetail = null;
  els.historyDetail.classList.add("hidden");
  els.historyDetail.parentElement.classList.remove("detail-open");
  els.historyArchivePreview.innerHTML = "";
  els.taskHistory.querySelectorAll(".history-item").forEach((item) => {
    item.classList.remove("selected");
  });
}

function appendHistoryDetailRow(root, labelText, valueText, wide = false) {
  const row = document.createElement("div");
  row.className = `history-detail-row${wide ? " wide" : ""}`;
  const label = document.createElement("span");
  label.textContent = labelText;
  const value = document.createElement("strong");
  value.textContent = valueText || "未记录";
  row.append(label, value);
  root.appendChild(row);
}

function renderHistoryArchivePreview(detail) {
  els.historyArchivePreview.innerHTML = "";
  if (!detail) return;

  const records = Array.isArray(detail.records) ? detail.records : [];
  const reports = Array.isArray(detail.reports) ? detail.reports : [];
  const recordBlock = document.createElement("section");
  recordBlock.className = "history-archive-block";
  const recordHeading = document.createElement("h5");
  recordHeading.textContent = `历史正文与审核结果（${records.length} 条）`;
  recordBlock.appendChild(recordHeading);
  if (!records.length) {
    const empty = document.createElement("span");
    empty.className = "history-empty";
    empty.textContent = "该任务没有保存正文记录";
    recordBlock.appendChild(empty);
  } else {
    records.slice(0, 8).forEach((record) => {
      const url = safeExternalUrl(record.url);
      const node = document.createElement(url ? "a" : "div");
      node.className = "history-archive-record";
      if (url) {
        node.href = url;
        node.target = "_blank";
        node.rel = "noopener noreferrer";
      }
      const title = document.createElement("strong");
      title.textContent = record.title || "未命名线索";
      const excerpt = document.createElement("span");
      const content = record.content || record.summary || record.description || "";
      excerpt.textContent = content ? String(content).slice(0, 160) : "没有可显示的正文摘要";
      node.append(title, excerpt);
      recordBlock.appendChild(node);
    });
    if (records.length > 8) {
      const more = document.createElement("span");
      more.className = "history-empty";
      more.textContent = `这里只预览前 8 条；载入任务后可审核全部 ${records.length} 条。`;
      recordBlock.appendChild(more);
    }
  }
  els.historyArchivePreview.appendChild(recordBlock);

  const reportBlock = document.createElement("section");
  reportBlock.className = "history-archive-block";
  const reportHeading = document.createElement("h5");
  reportHeading.textContent = `已归档报告（${reports.length} 份）`;
  reportBlock.appendChild(reportHeading);
  if (!reports.length) {
    const empty = document.createElement("span");
    empty.className = "history-empty";
    empty.textContent = "该任务尚未生成并归档报告";
    reportBlock.appendChild(empty);
  } else {
    reports.forEach((report) => {
      const link = document.createElement("a");
      link.className = "history-report-link";
      link.href = report.download_url || "#";
      const title = document.createElement("strong");
      title.textContent = report.filename || "历史报告";
      const meta = document.createElement("span");
      meta.textContent = `${formatHistoryTime(report.created_at)} · ${formatBytes(report.size)}`;
      link.append(title, meta);
      reportBlock.appendChild(link);
    });
  }
  els.historyArchivePreview.appendChild(reportBlock);
}

async function loadHistoryDetail(taskId) {
  els.historyArchivePreview.innerHTML = '<div class="history-empty">正在读取历史正文与报告</div>';
  try {
    const detail = await requestJson(`/api/task-history/detail?id=${encodeURIComponent(taskId)}`);
    if (state.selectedHistoryId !== taskId) return;
    state.selectedHistoryDetail = detail;
    renderHistoryArchivePreview(detail);
  } catch (error) {
    if (state.selectedHistoryId !== taskId) return;
    els.historyArchivePreview.innerHTML = "";
    const message = document.createElement("div");
    message.className = "history-empty";
    message.textContent = `历史正文读取失败：${error.message}`;
    els.historyArchivePreview.appendChild(message);
  }
}

function showHistoryDetail(item) {
  const payload = item.payload || {};
  const summary = item.summary || {};
  state.selectedHistoryId = item.task_id;
  state.selectedHistoryDetail = null;
  els.historyDetailTitle.textContent = historyTaskTitle(item);
  els.historyDetailContent.innerHTML = "";
  appendHistoryDetailRow(
    els.historyDetailContent,
    "状态",
    TASK_STATUS_COPY[item.status] || item.status || "未记录",
  );
  appendHistoryDetailRow(
    els.historyDetailContent,
    "完成时间",
    formatHistoryTime(item.completed_at || item.created_at),
  );
  appendHistoryDetailRow(
    els.historyDetailContent,
    "结果数量",
    `真实 ${summary.real_count || 0} / 总计 ${summary.total || summary.real_count || 0} 条`,
  );
  appendHistoryDetailRow(
    els.historyDetailContent,
    "来源结果",
    `政府官网 ${summary.stable_real_count || 0} 条 · 公开新闻 ${summary.public_news_real_count || 0} 条 · 社交平台 ${summary.social_real_count || 0} 条`,
  );
  appendHistoryDetailRow(
    els.historyDetailContent,
    "历史保存",
    item.archive_state === "full" ? "正文与审核结果已归档" : "仅保存任务信息",
  );
  appendHistoryDetailRow(els.historyDetailContent, "归档报告", `${item.report_count || 0} 份`);
  appendHistoryDetailRow(els.historyDetailContent, "关键词", (payload.keywords || []).join("、"), true);
  appendHistoryDetailRow(els.historyDetailContent, "地区", payload.region || "全国");
  appendHistoryDetailRow(els.historyDetailContent, "时间范围", payload.time_range || "近一周");
  appendHistoryDetailRow(els.historyDetailContent, "采集数量", payload.collect_level || "最小采集");
  appendHistoryDetailRow(
    els.historyDetailContent,
    "来源方式",
    SOURCE_STRATEGY_COPY[payload.source_strategy] || payload.source_strategy,
  );
  appendHistoryDetailRow(
    els.historyDetailContent,
    "结果不足提醒线",
    payload.min_real_results == null ? "自动" : `${payload.min_real_results} 条`,
  );
  appendHistoryDetailRow(
    els.historyDetailContent,
    "政府官网",
    (payload.stable_sources || []).join("、") || "未选择",
    true,
  );
  appendHistoryDetailRow(
    els.historyDetailContent,
    "社交平台",
    (payload.social_platforms || []).join("、") || "未选择",
    true,
  );
  if (item.message) {
    appendHistoryDetailRow(els.historyDetailContent, "任务说明", item.message, true);
  }
  els.loadHistoryBtn.disabled = item.archive_state !== "full";
  els.loadHistoryBtn.title = item.archive_state === "full" ? "" : "旧任务没有可载入的正文归档";
  els.historyArchivePreview.innerHTML = "";
  if (item.archive_state === "full") {
    loadHistoryDetail(item.task_id);
  } else {
    const message = document.createElement("div");
    message.className = "history-empty";
    message.textContent = "这是旧版任务记录，只能复用采集条件；历史正文在原版本中没有保存。";
    els.historyArchivePreview.appendChild(message);
  }
  els.historyDetail.classList.remove("hidden");
  els.historyDetail.parentElement.classList.add("detail-open");
  renderHistory(state.historyItems);
}

function renderHistorySummary(summary = {}) {
  state.historySummary = summary || {};
  els.historyArchiveSummary.textContent = [
    `完整归档 ${summary.full_archives || 0}`,
    `仅任务信息 ${summary.metadata_only || 0}`,
    `已归档报告 ${summary.report_count || 0}`,
    `回收站 ${summary.trash_count || 0}`,
  ].join(" · ");
}

async function runTrashAction(action, item) {
  if (!item?.trash_id) return;
  if (action === "purge") {
    const accepted = window.confirm(
      `将永久删除“${historyTaskTitle(item)}”的正文、审核结果和归档报告。此操作无法从回收站撤销，是否继续？`,
    );
    if (!accepted) return;
  }
  setStatus(action === "restore" ? "恢复历史任务中" : "永久删除中", "busy");
  try {
    const result = await requestJson("/api/task-history/trash-action", {
      method: "POST",
      body: JSON.stringify({
        trash_id: item.trash_id,
        action,
        confirm_trash_id: action === "purge" ? item.trash_id : "",
      }),
    });
    applyHistoryCatalog(result);
    setStatus(action === "restore" ? "历史任务已恢复" : "已永久删除");
    addLog(result.message);
  } catch (error) {
    setStatus(action === "restore" ? "恢复失败" : "永久删除失败", "error");
    addLog(error.message);
  }
}

function renderHistoryTrash(trash = []) {
  state.historyTrash = Array.isArray(trash) ? trash : [];
  els.historyTrashCount.textContent = String(state.historyTrash.length);
  els.historyTrashList.innerHTML = "";
  if (!state.historyTrash.length) {
    const empty = document.createElement("div");
    empty.className = "history-empty";
    empty.textContent = "回收站为空";
    els.historyTrashList.appendChild(empty);
    return;
  }
  state.historyTrash.forEach((item) => {
    const node = document.createElement("div");
    node.className = "history-trash-item";
    const info = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = historyTaskTitle(item);
    const meta = document.createElement("span");
    meta.textContent = `删除于 ${formatHistoryTime(item.deleted_at)} · 正文 ${item.records_count || 0} 条 · 报告 ${item.report_count || 0} 份`;
    info.append(title, meta);
    const actions = document.createElement("div");
    actions.className = "history-trash-actions";
    const restore = document.createElement("button");
    restore.type = "button";
    restore.className = "text-btn";
    restore.textContent = "恢复";
    restore.addEventListener("click", () => runTrashAction("restore", item));
    const purge = document.createElement("button");
    purge.type = "button";
    purge.className = "text-btn danger-text";
    purge.textContent = "永久删除";
    purge.addEventListener("click", () => runTrashAction("purge", item));
    actions.append(restore, purge);
    node.append(info, actions);
    els.historyTrashList.appendChild(node);
  });
}

function applyHistoryCatalog(catalog = {}) {
  const selectedHistoryId = state.selectedHistoryId;
  renderHistory(catalog.history || []);
  renderHistoryTrash(catalog.trash || []);
  renderHistorySummary(catalog.summary || {});
  if (!selectedHistoryId) return;
  const refreshedItem = state.historyItems.find((item) => item.task_id === selectedHistoryId);
  if (refreshedItem) {
    showHistoryDetail(refreshedItem);
  } else {
    closeHistoryDetail();
  }
}

function renderHistory(history = []) {
  state.historyItems = Array.isArray(history) ? history : [];
  els.taskHistory.innerHTML = "";
  if (!state.historyItems.length) {
    const empty = document.createElement("div");
    empty.className = "history-empty";
    empty.textContent = "暂无任务历史";
    els.taskHistory.appendChild(empty);
    els.toggleHistoryBtn.classList.add("hidden");
    closeHistoryDetail();
    return;
  }

  const visibleHistory = state.historyExpanded ? state.historyItems : state.historyItems.slice(0, 8);
  visibleHistory.forEach((item) => {
    const summary = item.summary || {};
    const node = document.createElement("button");
    node.type = "button";
    node.className = "history-item";
    node.classList.toggle("selected", state.selectedHistoryId === item.task_id);
    node.addEventListener("click", () => showHistoryDetail(item));

    const header = document.createElement("span");
    header.className = "history-item-header";
    const title = document.createElement("strong");
    title.textContent = historyTaskTitle(item);
    const status = document.createElement("span");
    status.className = `history-status ${item.status || "unknown"}`;
    status.textContent = TASK_STATUS_COPY[item.status] || item.status || "未记录";
    header.append(title, status);

    const detail = document.createElement("span");
    detail.className = "history-item-meta";
    const archiveLabel = item.archive_state === "full" ? "正文已归档" : "仅任务信息";
    detail.textContent = `真实 ${summary.real_count || 0} 条 · ${archiveLabel} · 报告 ${item.report_count || 0} 份`;
    const time = document.createElement("time");
    time.textContent = formatHistoryTime(item.completed_at || item.created_at);
    node.append(header, detail, time);
    els.taskHistory.appendChild(node);
  });

  els.toggleHistoryBtn.classList.toggle("hidden", state.historyItems.length <= 8 && !state.historyExpanded);
  els.toggleHistoryBtn.textContent = state.historyExpanded ? "收起" : "查看全部";
}

async function toggleTaskHistory() {
  if (state.historyExpanded) {
    state.historyExpanded = false;
    renderHistory(state.historyItems);
    return;
  }
  els.toggleHistoryBtn.disabled = true;
  try {
    const result = await requestJson("/api/task-history");
    state.historyExpanded = true;
    applyHistoryCatalog(result);
  } catch (error) {
    setStatus("历史加载失败", "error");
    addLog(error.message);
  } finally {
    els.toggleHistoryBtn.disabled = false;
  }
}

function applyHistoryChecks(container, selectedValues = []) {
  const selected = new Set(selectedValues);
  let matched = 0;
  container.querySelectorAll("input").forEach((input) => {
    input.checked = selected.has(input.value);
    if (input.checked) matched += 1;
  });
  return Math.max(0, selected.size - matched);
}

function reuseHistoryConditions() {
  const item = state.historyItems.find((entry) => entry.task_id === state.selectedHistoryId);
  if (!item) return;
  const payload = item.payload || {};
  els.taskTopic.value = payload.topic || "";
  els.keywords.value = (payload.keywords || []).join("\n");
  els.region.value = payload.region === "全国" ? "" : payload.region || "";
  els.minRealResults.value = payload.min_real_results == null ? "" : String(payload.min_real_results);

  const levelOptions = [...els.collectLevel.options].map((option) => option.value);
  els.collectLevel.value = levelOptions.includes(payload.collect_level) ? payload.collect_level : "最小采集";
  updateCollectionLimitCopy();

  const rangeOptions = [...els.timeRange.options].map((option) => option.value);
  const customMatch = String(payload.time_range || "").match(
    /^(\d{4}-\d{2}-\d{2})\s+至\s+(\d{4}-\d{2}-\d{2})$/,
  );
  if (rangeOptions.includes(payload.time_range)) {
    els.timeRange.value = payload.time_range;
    els.startDate.value = "";
    els.endDate.value = "";
  } else if (customMatch && rangeOptions.includes("自定义")) {
    els.timeRange.value = "自定义";
    els.startDate.value = customMatch[1];
    els.endDate.value = customMatch[2];
  } else {
    els.timeRange.value = "近一周";
    els.startDate.value = "";
    els.endDate.value = "";
  }
  updateCustomDateRange();

  const strategies = [...document.querySelectorAll("input[name='sourceStrategy']")];
  const requestedStrategy = ["stable_first", "hybrid"].includes(payload.source_strategy)
    ? "all"
    : payload.source_strategy;
  const strategy = strategies.find((input) => input.value === requestedStrategy)
    || strategies.find((input) => input.value === "all");
  if (strategy) strategy.checked = true;
  const missingStable = applyHistoryChecks(els.stableSources, payload.stable_sources || []);
  const missingSocial = applyHistoryChecks(els.socialPlatforms, payload.social_platforms || []);
  els.useSystemProxy.checked = Boolean(payload.use_system_proxy);
  els.saveDiagnostics.checked = Boolean(payload.enable_debug_snapshots);
  updateSelectButtons();
  updateSourceSummary();
  activateView("task");
  const missingTotal = missingStable + missingSocial;
  addLog(
    `已载入历史任务条件，请确认后开始采集${missingTotal ? `；${missingTotal} 个旧来源当前不可用，已忽略` : ""}`,
  );
  els.taskTopic.focus({ preventScroll: true });
}

async function loadHistoryTask() {
  const item = state.historyItems.find((entry) => entry.task_id === state.selectedHistoryId);
  if (!item || item.archive_state !== "full") return;
  const accepted = window.confirm(
    `载入“${historyTaskTitle(item)}”会替换当前工作区显示的数据，但不会删除当前任务的历史归档。是否继续？`,
  );
  if (!accepted) return;
  els.loadHistoryBtn.disabled = true;
  setStatus("载入历史任务中", "busy");
  try {
    const result = await requestJson("/api/task-history/load", {
      method: "POST",
      body: JSON.stringify({ task_id: item.task_id }),
    });
    renderLatest(result.latest);
    applyHistoryCatalog(result);
    renderReportPreview(null);
    els.reportDownload.classList.add("hidden");
    activateView("review");
    setStatus("历史任务已载入");
    addLog(result.message);
  } catch (error) {
    setStatus("历史任务载入失败", "error");
    addLog(error.message);
  } finally {
    els.loadHistoryBtn.disabled = false;
  }
}

async function deleteHistoryTask() {
  const item = state.historyItems.find((entry) => entry.task_id === state.selectedHistoryId);
  if (!item) return;
  const fullArchive = item.archive_state === "full";
  const warning = fullArchive
    ? "任务会先进入回收站，可在永久删除前恢复；已下载的加密备份不受影响。"
    : "这条旧记录只有任务信息，删除后无法从回收站恢复。";
  if (!window.confirm(`确定删除“${historyTaskTitle(item)}”吗？\n\n${warning}`)) return;
  els.deleteHistoryBtn.disabled = true;
  setStatus("删除历史任务中", "busy");
  try {
    const result = await requestJson("/api/task-history/delete", {
      method: "POST",
      body: JSON.stringify({ task_id: item.task_id, confirm_task_id: item.task_id }),
    });
    closeHistoryDetail();
    renderLatest(result.latest);
    applyHistoryCatalog(result);
    setStatus(fullArchive ? "任务已移入回收站" : "旧任务信息已删除");
    addLog(result.message);
  } catch (error) {
    setStatus("历史任务删除失败", "error");
    addLog(error.message);
  } finally {
    els.deleteHistoryBtn.disabled = false;
  }
}

function openHistoryDialog(dialog, form = null) {
  if (form) form.reset();
  if (typeof dialog.showModal === "function") dialog.showModal();
  else dialog.setAttribute("open", "");
}

function closeHistoryDialog(dialog) {
  if (typeof dialog.close === "function") dialog.close();
  else dialog.removeAttribute("open");
}

function triggerDownload(url, filename = "") {
  const link = document.createElement("a");
  link.href = url;
  if (filename) link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
}

async function createHistoryBackup(event) {
  event.preventDefault();
  const passphrase = els.historyBackupPassphrase.value;
  if (passphrase.length < 8) {
    els.historyBackupPassphrase.setCustomValidity("备份口令至少需要8个字符");
    els.historyBackupPassphrase.reportValidity();
    return;
  }
  if (passphrase !== els.historyBackupPassphraseConfirm.value) {
    els.historyBackupPassphraseConfirm.setCustomValidity("两次输入的备份口令不一致");
    els.historyBackupPassphraseConfirm.reportValidity();
    return;
  }
  els.historyBackupPassphrase.setCustomValidity("");
  els.historyBackupPassphraseConfirm.setCustomValidity("");
  els.confirmHistoryBackupBtn.disabled = true;
  setStatus("创建加密备份中", "busy");
  try {
    const result = await requestJson("/api/task-history/backup", {
      method: "POST",
      body: JSON.stringify({ passphrase }),
    });
    closeHistoryDialog(els.historyBackupDialog);
    triggerDownload(result.backup.download_url, result.backup.filename);
    setStatus("加密备份已创建");
    addLog(`${result.message}，文件大小 ${formatBytes(result.backup.size)}`);
  } catch (error) {
    setStatus("创建备份失败", "error");
    addLog(error.message);
  } finally {
    els.confirmHistoryBackupBtn.disabled = false;
    els.historyBackupPassphrase.value = "";
    els.historyBackupPassphraseConfirm.value = "";
  }
}

function readFileAsBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || "").split(",", 2)[1] || "");
    reader.onerror = () => reject(new Error("无法读取所选备份文件"));
    reader.readAsDataURL(file);
  });
}

async function restoreHistoryBackup(event) {
  event.preventDefault();
  const file = els.historyRestoreFile.files?.[0];
  const passphrase = els.historyRestorePassphrase.value;
  if (!file) {
    els.historyRestoreFile.reportValidity();
    return;
  }
  if (file.size > 70 * 1024 * 1024) {
    els.historyRestoreFile.setCustomValidity("备份文件超过当前允许的大小");
    els.historyRestoreFile.reportValidity();
    return;
  }
  els.historyRestoreFile.setCustomValidity("");
  els.confirmHistoryRestoreBtn.disabled = true;
  setStatus("校验并恢复备份中", "busy");
  try {
    const backupBase64 = await readFileAsBase64(file);
    const result = await requestJson("/api/task-history/restore", {
      method: "POST",
      body: JSON.stringify({ backup_base64: backupBase64, passphrase }),
    });
    closeHistoryDialog(els.historyRestoreDialog);
    applyHistoryCatalog(result);
    setStatus("备份恢复完成");
    addLog(result.message);
    if (result.restore?.conflict_task_ids?.length) {
      addLog(`以下同编号任务内容不同，已保留当前版本且未覆盖：${result.restore.conflict_task_ids.join("、")}`);
    }
  } catch (error) {
    setStatus("备份恢复失败", "error");
    addLog(error.message);
  } finally {
    els.confirmHistoryRestoreBtn.disabled = false;
    els.historyRestorePassphrase.value = "";
  }
}

function renderEvents(events = []) {
  els.eventList.innerHTML = "";
  if (!events.length) {
    els.eventList.innerHTML = '<div class="compact-item"><span>暂无进度事件</span></div>';
    return;
  }
  events.slice(-8).reverse().forEach((event) => {
    const node = document.createElement("div");
    node.className = `compact-item ${event.type === "source_failure" ? "failed" : event.type === "source_success" ? "ok" : ""}`;
    const diagnostic = event.debug_snapshot
      ? ` · 诊断：${event.debug_snapshot}（清除该平台授权可一并删除）`
      : "";
    node.innerHTML = `<strong>${event.channel || event.type || "事件"}</strong><span>${event.message || ""}${diagnostic}</span>`;
    els.eventList.appendChild(node);
  });
}

function renderTable(data) {
  els.resultBody.innerHTML = "";
  clearEvidenceSummary();
  if (!data || data.length === 0) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 4;
    cell.className = "empty";
    cell.textContent = "暂无数据";
    row.appendChild(cell);
    els.resultBody.appendChild(row);
    refreshReviewFilterOptions([]);
    applyReviewFilters();
    return;
  }

  data.forEach((item, index) => {
    const row = document.createElement("tr");
    row.dataset.index = String(index);
    row.dataset.platform = item.platform || item.source || "未知";
    row.dataset.category = item.content_category || "其他";
    row.dataset.sentiment = item.sentiment_label || "中性";
    const keep = document.createElement("td");
    const title = document.createElement("td");
    const source = document.createElement("td");
    const decision = document.createElement("td");

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.className = "review-check";
    checkbox.checked = true;
    keep.appendChild(checkbox);

    title.className = "title-cell";
    const titleText = item.title || "(无标题)";
    const originalUrl = safeExternalUrl(item.url);
    if (originalUrl) {
      const titleLink = document.createElement("a");
      titleLink.className = "source-title-link";
      titleLink.href = originalUrl;
      titleLink.target = "_blank";
      titleLink.rel = "noopener noreferrer";
      titleLink.title = "在新标签页打开原内容";

      const linkText = document.createElement("span");
      linkText.textContent = titleText;
      const externalMark = document.createElement("span");
      externalMark.className = "external-mark";
      externalMark.setAttribute("aria-hidden", "true");
      externalMark.textContent = "↗";
      titleLink.append(linkText, externalMark);
      title.appendChild(titleLink);
    } else {
      const titleLabel = document.createElement("span");
      titleLabel.className = "source-title-text";
      titleLabel.textContent = titleText;
      const unavailable = document.createElement("small");
      unavailable.className = "source-link-unavailable";
      unavailable.textContent = "无可用原文链接";
      title.append(titleLabel, unavailable);
    }

    const contentExcerpt = document.createElement("small");
    contentExcerpt.className = "review-content-excerpt";
    contentExcerpt.textContent = String(item.content || "无正文摘要").replace(/\s+/g, " ").slice(0, 140);
    title.appendChild(contentExcerpt);

    const rowActions = document.createElement("div");
    rowActions.className = "review-row-actions";
    const summarizeButton = document.createElement("button");
    summarizeButton.className = "text-btn row-summary-btn";
    summarizeButton.type = "button";
    summarizeButton.textContent = "生成这条摘要";
    summarizeButton.addEventListener("click", () => {
      generateEvidenceSummary("record", index, summarizeButton);
    });
    rowActions.appendChild(summarizeButton);
    title.appendChild(rowActions);

    const noteWrap = document.createElement("label");
    noteWrap.className = "review-note-wrap";
    const noteLabel = document.createElement("span");
    noteLabel.textContent = "人工备注";
    const noteInput = document.createElement("input");
    noteInput.className = "review-note";
    noteInput.type = "text";
    noteInput.maxLength = 500;
    noteInput.placeholder = "可选：记录判断依据";
    noteInput.value = item.human_review?.note || "";
    noteWrap.append(noteLabel, noteInput);
    title.appendChild(noteWrap);

    source.className = "review-source-cell";
    const platformName = document.createElement("strong");
    platformName.textContent = item.platform || item.source || "-";
    const sourceName = document.createElement("small");
    sourceName.textContent = item.source || "-";
    source.append(platformName, sourceName);

    const tag = document.createElement("span");
    tag.className = `tag ${item.data_type === "mock" ? "mock" : ""}`;
    const capability = [item.source_access_type, item.source_support_level].filter(Boolean).join("/");
    tag.textContent = item.data_type === "mock"
      ? "mock"
      : [capability, item.source_type || "real"].filter(Boolean).join(" · ");
    tag.title = [
      item.source_rule_id ? `规则：${item.source_rule_id}` : "",
      item.platform_rule_status ? `平台规则：${item.platform_rule_status}` : "",
      item.robots_status ? `robots：${item.robots_status}` : "",
    ].filter(Boolean).join("\n");
    source.appendChild(tag);
    const sourceTime = document.createElement("small");
    sourceTime.className = "review-time";
    sourceTime.textContent = `发布时间：${formatPublicationTime(item)}`;
    source.appendChild(sourceTime);

    decision.className = "review-decision-cell";
    const categoryGroup = document.createElement("div");
    categoryGroup.className = "review-decision-group";
    const categoryLabel = document.createElement("strong");
    categoryLabel.textContent = "内容分类";

    const categorySelect = buildReviewSelect(
      state.options?.content_categories || ["其他"],
      item.content_category || "其他",
      "review-category",
      "内容分类",
    );
    const categoryHint = document.createElement("small");
    categoryHint.className = "review-machine-hint";
    categoryHint.textContent = reviewHint(
      item.content_category_source,
      item.machine_content_category || item.content_category || "其他",
    );
    categorySelect.addEventListener("change", () => {
      row.dataset.category = categorySelect.value;
      categoryHint.textContent = `待保存 · 机器初判：${item.machine_content_category || "其他"}`;
      categoryHint.classList.add("pending");
      applyReviewFilters();
    });
    categoryGroup.append(categoryLabel, categorySelect, categoryHint);

    const sentimentGroup = document.createElement("div");
    sentimentGroup.className = "review-decision-group";
    const sentimentLabel = document.createElement("strong");
    sentimentLabel.textContent = "情感参考";
    const sentimentSelect = buildReviewSelect(
      state.options?.sentiment_labels || ["正面", "中性", "负面"],
      item.sentiment_label || "中性",
      "review-sentiment",
      "情感参考",
    );
    const sentimentHint = document.createElement("small");
    sentimentHint.className = "review-machine-hint";
    sentimentHint.textContent = reviewHint(
      item.sentiment_source,
      item.machine_sentiment_label || item.sentiment_label || "中性",
    );
    sentimentSelect.addEventListener("change", () => {
      row.dataset.sentiment = sentimentSelect.value;
      sentimentHint.textContent = `待保存 · 机器初判：${item.machine_sentiment_label || "中性"}`;
      sentimentHint.classList.add("pending");
      applyReviewFilters();
    });
    sentimentGroup.append(sentimentLabel, sentimentSelect, sentimentHint);
    decision.append(categoryGroup, sentimentGroup);

    row.append(keep, title, source, decision);
    els.resultBody.appendChild(row);
  });
  refreshReviewFilterOptions(data);
  applyReviewFilters();
}

function buildReviewSelect(options, selectedValue, className, label) {
  const select = document.createElement("select");
  select.className = `review-field ${className}`;
  select.setAttribute("aria-label", label);
  options.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    option.selected = value === selectedValue;
    select.appendChild(option);
  });
  return select;
}

function reviewHint(source, machineValue) {
  return source === "human_review"
    ? `已人工确认 · 机器初判：${machineValue}`
    : `机器初判：${machineValue} · 仅供参考`;
}

function setFilterOptions(select, placeholder, values) {
  if (!select) return;
  const current = select.value;
  select.replaceChildren();
  const first = document.createElement("option");
  first.value = "";
  first.textContent = placeholder;
  select.appendChild(first);
  values.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    select.appendChild(option);
  });
  select.value = values.includes(current) ? current : "";
}

function refreshReviewFilterOptions(data) {
  const sources = [...new Set((data || []).map((item) => item.platform || item.source || "未知"))].sort();
  setFilterOptions(els.reviewSourceFilter, "全部来源", sources);
  setFilterOptions(
    els.reviewCategoryFilter,
    "全部分类",
    state.options?.content_categories || [],
  );
  setFilterOptions(
    els.reviewSentimentFilter,
    "全部情感",
    state.options?.sentiment_labels || [],
  );
}

function applyReviewFilters() {
  const rows = [...els.resultBody.querySelectorAll("tr[data-index]")];
  const source = els.reviewSourceFilter?.value || "";
  const category = els.reviewCategoryFilter?.value || "";
  const sentiment = els.reviewSentimentFilter?.value || "";
  let visible = 0;
  rows.forEach((row) => {
    const matches = (!source || row.dataset.platform === source)
      && (!category || row.dataset.category === category)
      && (!sentiment || row.dataset.sentiment === sentiment);
    row.hidden = !matches;
    if (matches) visible += 1;
  });
  if (els.reviewVisibleCount) {
    els.reviewVisibleCount.textContent = rows.length ? `显示 ${visible} / ${rows.length} 条` : "暂无数据";
  }
  updateReportScopeSummary(visible, rows.length);
  updateSummaryControls();
}

function updateSummaryControls() {
  if (!els.summarySourceBtn) return;
  const source = els.reviewSourceFilter?.value || "";
  els.summarySourceBtn.disabled = !source;
  els.summarySourceBtn.title = source
    ? `汇总来源“${source}”的全部线索`
    : "请先选择一个来源平台";
}

function clearEvidenceSummary() {
  state.summaryDraft = null;
  if (!els.summaryResult) return;
  els.summaryResult.replaceChildren();
  const empty = document.createElement("div");
  empty.className = "summary-empty";
  empty.textContent = "选择一种摘要方式；若刚修改了保留、分类或情感，请先保存审核结果。";
  els.summaryResult.appendChild(empty);
}

function appendSummaryCitations(container, ids, evidenceById) {
  (ids || []).forEach((id) => {
    const evidence = evidenceById.get(id) || {};
    const url = safeExternalUrl(evidence.url);
    const citation = document.createElement(url ? "a" : "span");
    citation.className = "summary-citation";
    citation.textContent = `[${id}]`;
    citation.title = evidence.title || "关联线索";
    if (url) {
      citation.href = url;
      citation.target = "_blank";
      citation.rel = "noopener noreferrer";
    }
    container.appendChild(citation);
  });
}

function renderEvidenceSummary(summary) {
  if (!els.summaryResult) return;
  state.summaryDraft = summary;
  els.summaryResult.replaceChildren();
  const scope = summary.scope || {};
  const evidence = summary.evidence || [];
  const evidenceById = new Map(evidence.map((item) => [item.reference_id, item]));

  const heading = document.createElement("div");
  heading.className = "summary-result-heading";
  const title = document.createElement("strong");
  title.textContent = `${scope.label || "摘要"} · ${scope.record_count || 0} 条`;
  const review = document.createElement("span");
  review.textContent = summary.review?.labels_confirmed_for_all
    ? "分类与情感均已人工确认"
    : `人工确认 ${summary.review?.reviewed_count || 0}/${summary.review?.record_count || 0} 条`;
  heading.append(title, review);
  els.summaryResult.appendChild(heading);

  const notice = document.createElement("p");
  notice.className = "summary-notice";
  notice.textContent = summary.notice || "机器生成草稿，请结合原文复核。";
  els.summaryResult.appendChild(notice);

  const overview = document.createElement("p");
  overview.className = "summary-overview";
  overview.textContent = summary.overview || "暂无概述";
  els.summaryResult.appendChild(overview);

  const points = document.createElement("ol");
  points.className = "summary-points";
  (summary.key_points || []).forEach((point) => {
    const item = document.createElement("li");
    const pointText = document.createElement("span");
    pointText.textContent = point.text || "";
    item.appendChild(pointText);
    appendSummaryCitations(item, point.evidence_ids || [], evidenceById);
    points.appendChild(item);
  });
  els.summaryResult.appendChild(points);

  if ((summary.keywords || []).length) {
    const keywords = document.createElement("div");
    keywords.className = "summary-keywords";
    const label = document.createElement("strong");
    label.textContent = "关键词";
    keywords.appendChild(label);
    (summary.keywords || []).forEach((value) => {
      const tag = document.createElement("span");
      tag.textContent = value;
      keywords.appendChild(tag);
    });
    els.summaryResult.appendChild(keywords);
  }

  const evidenceTitle = document.createElement("strong");
  evidenceTitle.className = "summary-evidence-title";
  evidenceTitle.textContent = "原文追溯";
  els.summaryResult.appendChild(evidenceTitle);
  const evidenceList = document.createElement("div");
  evidenceList.className = "summary-evidence-list";
  evidence.forEach((item) => {
    const card = document.createElement("div");
    card.className = "summary-evidence-item";
    const url = safeExternalUrl(item.url);
    const evidenceLink = document.createElement(url ? "a" : "strong");
    evidenceLink.textContent = `${item.reference_id || "-"} · ${item.title || "(无标题)"}`;
    if (url) {
      evidenceLink.href = url;
      evidenceLink.target = "_blank";
      evidenceLink.rel = "noopener noreferrer";
      evidenceLink.title = "打开原内容";
    }
    const meta = document.createElement("span");
    meta.textContent = `${item.platform || "-"} · ${item.source || "-"} · ${item.pub_time || "时间未知"}`;
    card.append(evidenceLink, meta);
    evidenceList.appendChild(card);
  });
  els.summaryResult.appendChild(evidenceList);
}

async function generateEvidenceSummary(scopeType, recordIndex = null, triggerButton = null) {
  const source = els.reviewSourceFilter?.value || "";
  if (scopeType === "source" && !source) {
    setStatus("请选择来源", "error");
    addLog("请先在“来源平台”中选择一个来源，再汇总当前来源");
    return;
  }
  if (triggerButton) triggerButton.disabled = true;
  setStatus("生成摘要中", "busy");
  try {
    const result = await requestJson("/api/summary", {
      method: "POST",
      body: JSON.stringify({
        scope_type: scopeType,
        record_index: recordIndex,
        source,
        report_filter: currentReportFilter(),
      }),
    });
    renderEvidenceSummary(result.summary);
    els.summaryResult.scrollIntoView({ behavior: "smooth", block: "nearest" });
    setStatus("摘要完成");
    addLog(result.message || "摘要已生成");
  } catch (error) {
    setStatus("摘要失败", "error");
    addLog(error.message);
  } finally {
    if (triggerButton) triggerButton.disabled = false;
    updateSummaryControls();
  }
}

function currentReportFilter() {
  return {
    source: els.reviewSourceFilter?.value || "",
    category: els.reviewCategoryFilter?.value || "",
    sentiment: els.reviewSentimentFilter?.value || "",
  };
}

function reportFilterDescription(reportFilter = currentReportFilter()) {
  return [
    reportFilter.source ? `来源：${reportFilter.source}` : "",
    reportFilter.category ? `分类：${reportFilter.category}` : "",
    reportFilter.sentiment ? `情感：${reportFilter.sentiment}` : "",
  ].filter(Boolean);
}

function updateReportScopeSummary(matchedTotal, originalTotal) {
  if (!els.reportScopeSummary || !els.reportScopeDetail) return;
  const parts = reportFilterDescription();
  if (parts.length) {
    els.reportScopeSummary.textContent = `使用 ${matchedTotal} / ${originalTotal} 条已审核数据`;
    els.reportScopeDetail.textContent = parts.join(" · ");
  } else {
    els.reportScopeSummary.textContent = `使用全部 ${originalTotal} 条已审核数据`;
    els.reportScopeDetail.textContent = "未设置来源、分类或情感条件。";
  }
}

function invalidateReportForScopeChange() {
  if (state.reportDraft) {
    renderReportPreview(null);
    addLog("报告数据范围已更改，请重新生成预览");
  }
  els.reportDownload.classList.add("hidden");
}

function safeExternalUrl(value) {
  try {
    const url = new URL(String(value || "").trim());
    return ["http:", "https:"].includes(url.protocol) ? url.href : "";
  } catch {
    return "";
  }
}

function formatPublicationTime(item) {
  const value = (item.pub_time || "").trim();
  if (!value) return "-";
  if (item.time_basis === "published_date" || /^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return value.slice(0, 10);
  }
  return value.replace("T", " ").slice(0, 16);
}

function renderLatest(latest) {
  state.latest = latest;
  updateMetrics(latest);
  renderSourceHealth((latest || {}).meta || {});
  renderHistory((latest || {}).history || []);
  renderTable(latest.data || []);
}

const AI_FIELD_COPY = {
  reference_id: "证据编号",
  title: "标题",
  content: "正文",
  source: "来源",
  platform: "来源平台",
  source_type: "来源类型",
  pub_time: "发布时间",
  content_category: "人工确认分类",
  sentiment_label: "人工确认情感",
};

function resetAiDraft() {
  state.aiDraft = null;
  els.aiDraftEditor.classList.add("hidden");
  els.aiDraftEditor.querySelectorAll("[data-ai-section]").forEach((editor) => {
    editor.value = "";
  });
  els.aiApplyBtn.disabled = true;
  els.aiDiscardBtn.disabled = true;
  els.aiUsage.textContent = "尚无本次调用用量。";
}

function updateAiGenerateAvailability() {
  const hasConfirmation = Boolean(state.aiDisclosure?.confirmation_id);
  const canGenerate = Boolean(
    state.reportDraft
      && state.aiDisclosure?.can_generate
      && hasConfirmation
      && !state.aiRequestPending
      && els.aiExternalSendConfirm.checked,
  );
  els.aiGenerateBtn.disabled = !canGenerate;
  els.aiExternalSendConfirm.disabled = !hasConfirmation || state.aiRequestPending;
}

function renderAiAssistance(disclosure) {
  resetAiDraft();
  state.aiDisclosure = disclosure || null;
  state.aiRequestPending = false;
  els.aiExternalSendConfirm.checked = false;
  if (!disclosure) {
    els.aiReportPanel.classList.add("hidden");
    els.aiDraftStatus.textContent = "AI 功能默认关闭，普通预览和 Word 导出不会产生调用费用。";
    updateAiGenerateAvailability();
    return;
  }

  els.aiReportPanel.classList.remove("hidden");
  const outputBudget = Number(disclosure.max_output_tokens || 0).toLocaleString("zh-CN");
  const providerMaximum = Number(disclosure.provider_max_output_tokens || 0).toLocaleString("zh-CN");
  const inputBudget = Number(disclosure.input_budget_tokens || 0).toLocaleString("zh-CN");
  const estimatedInput = Number(disclosure.estimated_input_tokens || 0).toLocaleString("zh-CN");
  els.aiProviderModel.textContent = [
    `${disclosure.provider || "DeepSeek"} · ${disclosure.model || "未配置模型"}`,
    "质量优先",
    `深度思考 ${disclosure.reasoning_effort || "max"}`,
    `本次输出预算 ${outputBudget} tokens（可配置至服务商最大 ${providerMaximum}）`,
    `保守预计输入 ${estimatedInput} / ${inputBudget} tokens`,
  ].join(" · ");
  els.aiProviderState.textContent = disclosure.configured ? "服务端已配置" : "服务端未配置";
  els.aiProviderState.dataset.status = disclosure.configured ? "ready" : "blocked";
  els.aiExternalScope.textContent = [
    `已审核候选 ${disclosure.eligible_record_count || 0} 条`,
    `证据目录 ${disclosure.candidate_evidence_count || 0} 条`,
    `实际发送 ${disclosure.evidence_count || 0} 条`,
    `因预算省略 ${disclosure.omitted_due_input_budget_count || 0} 条`,
    `正文截取 ${disclosure.truncated_evidence_count || 0} 条`,
    `其中登录/非匿名访问 ${disclosure.login_record_count || 0} 条`,
  ].join(" · ");
  els.aiExternalFields.textContent = (disclosure.fields || [])
    .map((field) => AI_FIELD_COPY[field] || field)
    .join("、");

  if (disclosure.configuration_error) {
    els.aiDraftStatus.textContent = disclosure.configuration_error;
  } else if (!disclosure.configured) {
    els.aiDraftStatus.textContent = "服务端尚未配置 DEEPSEEK_API_KEY，规则报告仍可正常使用。";
  } else if (!disclosure.evidence_count) {
    els.aiDraftStatus.textContent = "当前范围没有可装入本次预算的已审核证据；未审核数据不会发送。";
  } else {
    els.aiDraftStatus.textContent = "请按甲方内部规则核对范围并勾选确认，随后才会发起一次收费请求。";
  }
  updateAiGenerateAvailability();
}

function renderAiDraft(draft) {
  const sections = draft?.sections || {};
  els.aiDraftEditor.querySelectorAll("[data-ai-section]").forEach((editor) => {
    editor.value = sections[editor.dataset.aiSection] || "";
  });
  const usage = draft?.usage || {};
  els.aiUsage.textContent = usage.total_tokens == null
    ? "服务商未返回本次 token 用量。"
    : `本次用量：输入 ${usage.prompt_tokens ?? "-"} · 输出 ${usage.completion_tokens ?? "-"} · 合计 ${usage.total_tokens} tokens`;
  els.aiDraftEditor.classList.remove("hidden");
  els.aiApplyBtn.disabled = false;
  els.aiDiscardBtn.disabled = false;
}

async function generateAiReportDraft() {
  if (!state.reportDraft) {
    els.aiDraftStatus.textContent = "请先生成规则报告预览。";
    return;
  }
  if (!els.aiExternalSendConfirm.checked) {
    els.aiDraftStatus.textContent = "请先按甲方内部规则核对并确认本次发送范围。";
    return;
  }
  const confirmationId = state.aiDisclosure?.confirmation_id;
  if (!confirmationId) {
    els.aiDraftStatus.textContent = "本次确认已失效，请重新生成报告预览并再次确认。";
    return;
  }

  state.aiRequestPending = true;
  delete state.aiDisclosure.confirmation_id;
  els.aiGenerateBtn.disabled = true;
  els.aiExternalSendConfirm.checked = false;
  els.aiExternalSendConfirm.disabled = true;
  els.aiDraftStatus.textContent = "正在请求 DeepSeek；本次只发送上方披露的实际证据范围。";
  addLog("用户已按甲方规则确认本次发送范围，开始生成 DeepSeek 分析草稿");
  try {
    const result = await requestJson("/api/report-ai-draft", {
      method: "POST",
      body: JSON.stringify({
        template_id: els.templateSelect.value,
        region: els.region.value.trim(),
        time_range: selectedTimeRange(),
        report_filter: currentReportFilter(),
        confirmed_external_send: true,
        confirmed_scope_token: state.aiDisclosure.scope_token,
        confirmation_id: confirmationId,
      }),
    });
    state.aiDraft = result.draft;
    renderAiDraft(result.draft);
    els.aiDraftStatus.textContent = "AI 草稿已返回，但尚未采用到报告；请逐段核对。";
    addLog(result.message || "DeepSeek 分析草稿已生成");
  } catch (error) {
    els.aiDraftStatus.textContent = `${error.message}；本次确认已使用，请重新生成报告预览并再次确认。现有规则报告和草稿未改变。`;
    addLog(error.message);
  } finally {
    state.aiRequestPending = false;
    updateAiGenerateAvailability();
  }
}

function applyAiDraftToPreview() {
  if (!state.aiDraft) return;
  const reportScopeToken = String(state.aiDraft.report_export_scope_token || "").trim();
  if (!/^[0-9a-f]{64}$/.test(reportScopeToken)) {
    els.aiDraftStatus.textContent = "AI 草稿缺少有效的证据范围，请重新生成报告预览和 AI 草稿。";
    return;
  }
  const aiSections = {};
  els.aiDraftEditor.querySelectorAll("[data-ai-section]").forEach((editor) => {
    aiSections[editor.dataset.aiSection] = editor.value.trim();
  });
  if (Object.values(aiSections).some((value) => !value)) {
    els.aiDraftStatus.textContent = "AI 草稿章节不能为空；请补充或舍弃后再采用。";
    return;
  }

  const reportEditors = new Map(
    [...els.reportPreview.querySelectorAll(".report-section-editor")]
      .map((editor) => [editor.dataset.sectionId, editor]),
  );
  const summaryEditor = reportEditors.get("summary");
  const analysisEditor = reportEditors.get("analysis");
  const recommendationsEditor = reportEditors.get("recommendations");
  if (!summaryEditor || !analysisEditor || !recommendationsEditor) {
    els.aiDraftStatus.textContent = "当前模板缺少可采用的分析章节，请保留规则报告。";
    return;
  }

  summaryEditor.value = aiSections.summary;
  analysisEditor.value = `${aiSections.analysis}\n\n风险提示：\n${aiSections.risks}`;
  recommendationsEditor.value = aiSections.recommendations;
  state.aiDraft.sections = aiSections;
  state.aiDraft.applied = true;
  state.appliedAiReportScopeToken = reportScopeToken;
  els.aiDraftStatus.textContent = "AI 草稿已采用到报告预览；仍可继续人工修改，导出前请再次核对。";
  addLog("已人工选择采用 DeepSeek 草稿到分析性章节；事实边界、时间线和证据清单未改动");
  summaryEditor.focus();
}

function discardAiReportDraft() {
  resetAiDraft();
  els.aiDraftStatus.textContent = "AI 草稿已舍弃，当前规则报告和人工修改未改变。";
  addLog("已舍弃 DeepSeek 分析草稿");
}

function renderReportPreview(preview) {
  const root = els.reportPreview;
  root.innerHTML = "";
  state.appliedAiReportScopeToken = "";
  if (!preview) {
    state.reportDraft = null;
    renderAiAssistance(null);
    root.classList.add("hidden");
    return;
  }
  state.reportDraft = preview;
  renderAiAssistance(preview.ai_assistance || null);
  root.classList.remove("hidden");

  const quality = preview.quality || {};
  const analysis = preview.analysis || {};
  const grounding = preview.grounding || {};
  const scope = preview.scope || {};
  const summary = document.createElement("div");
  summary.className = "report-preview-summary";
  [
    ["模板", preview.template_name || preview.template_id || "-"],
    ["事件", analysis.event_keyword || "-"],
    ["当前状态", quality.status_label || "未检查"],
    ["报告范围", `${scope.matched_total ?? quality.real_count ?? 0} / ${scope.original_total ?? quality.real_count ?? 0} 条`],
    ["数据", `真实 ${quality.real_count || 0} · 稳定源 ${quality.stable_count || 0} · 社交 ${quality.social_count || 0}`],
    [
      "证据",
      `正文引用 ${grounding.citation_count || 0} 次 · 样本 ${grounding.cited_sample_count || 0}/${grounding.available_sample_count || 0}`,
    ],
  ].forEach(([label, value]) => {
    const item = document.createElement("div");
    item.className = "report-preview-metric";
    const small = document.createElement("span");
    small.textContent = label;
    const strong = document.createElement("strong");
    strong.textContent = value;
    item.append(small, strong);
    summary.appendChild(item);
  });
  root.appendChild(summary);

  const statusBox = document.createElement("div");
  statusBox.className = `report-status-box ${quality.status_code || "needs_attention"}`;
  statusBox.textContent = `${quality.status_label || "未检查"}：${quality.status_detail || "暂无状态说明"}`;
  root.appendChild(statusBox);

  const checklistTitle = document.createElement("h3");
  checklistTitle.textContent = "采集与报告检查清单";
  root.appendChild(checklistTitle);
  const checklist = document.createElement("div");
  checklist.className = "quality-checklist report-quality-checklist";
  renderQualityChecklist(checklist, quality.checks || []);
  root.appendChild(checklist);

  const timeline = preview.timeline || [];
  if (timeline.length) {
    const timelineTitle = document.createElement("h3");
    timelineTitle.textContent = "事件时间线";
    root.appendChild(timelineTitle);
    const timelineList = document.createElement("div");
    timelineList.className = "timeline-list";
    timeline.slice(0, 8).forEach((event) => {
      const item = document.createElement("div");
      item.className = "timeline-item";
      const time = document.createElement("strong");
      time.textContent = event.display_time || event.time || "-";
      const body = document.createElement("span");
      body.textContent = `${event.platform || "-"} · ${event.source || "-"} · ${event.title || "(无标题)"}`;
      item.append(time, body);
      timelineList.appendChild(item);
    });
    root.appendChild(timelineList);
  }

  const sections = document.createElement("div");
  sections.className = "report-preview-sections";
  const editingNote = document.createElement("div");
  editingNote.className = "report-editing-note";
  editingNote.textContent = "以下内容可直接修改；生成 Word 时将使用当前文字。请保留用于追溯的 [S编号]。";
  root.appendChild(editingNote);
  (preview.sections || []).forEach((section) => {
    const card = document.createElement("div");
    card.className = `report-section-preview ${section.is_title ? "title-section" : ""}`;
    const title = document.createElement("h3");
    title.textContent = section.name || section.id;
    const body = document.createElement("textarea");
    body.className = "report-section-editor";
    body.dataset.sectionId = section.id || "";
    body.value = section.content || "";
    body.rows = section.is_title ? 2 : Math.min(16, Math.max(6, body.value.split("\n").length + 3));
    body.setAttribute("aria-label", `${title.textContent}内容`);
    card.append(title, body);
    if (section.require_manual_review) {
      const badge = document.createElement("span");
      badge.className = "review-badge";
      badge.textContent = "建议人工审定";
      card.appendChild(badge);
    }
    sections.appendChild(card);
  });
  root.appendChild(sections);

  const samples = preview.key_samples || [];
  if (samples.length) {
    const sampleTitle = document.createElement("h3");
    sampleTitle.textContent = "重点样本与来源追溯";
    root.appendChild(sampleTitle);
    const list = document.createElement("div");
    list.className = "sample-list";
    samples.slice(0, 6).forEach((sample) => {
      const item = document.createElement("div");
      item.className = "sample-item";
      const title = document.createElement("strong");
      title.textContent = `${sample.reference_id || "-"} · ${sample.title || "(无标题)"}`;
      const meta = document.createElement("span");
      meta.textContent = `${sample.platform || "-"} · ${sample.source || "-"} · ${sample.pub_time || "-"}`;
      item.append(title, meta);
      list.appendChild(item);
    });
    root.appendChild(list);
  }
}

async function refreshLatest() {
  setStatus("刷新中", "busy");
  const latest = await requestJson("/api/latest");
  renderLatest(latest);
  setStatus("待命");
  addLog("已刷新本地最新采集结果");
}

async function previewReport() {
  const review = state.latest?.meta?.review || {};
  const reviewedCurrentData = review.reviewed_at
    && review.labels_confirmed
    && Number(review.kept_total) === Number(state.latest?.total || 0);
  if (!reviewedCurrentData) {
    activateView("review");
    setStatus("等待人工审核", "error");
    addLog("请先逐条核对原文、内容分类和情感标签并保存审核结果，再生成报告预览");
    return;
  }
  setBusy(true);
  setStatus("生成预览中", "busy");
  addLog("开始生成报告预览");
  try {
    const result = await requestJson("/api/report-preview", {
      method: "POST",
      body: JSON.stringify({
        template_id: els.templateSelect.value,
        region: els.region.value.trim(),
        time_range: selectedTimeRange(),
        report_filter: currentReportFilter(),
      }),
    });
    renderReportPreview(result.preview);
    setStatus("预览完成");
    addLog(result.message || "报告预览已生成");
  } catch (error) {
    setStatus("预览失败", "error");
    addLog(error.message);
  } finally {
    setBusy(false);
  }
}

async function loadOptions() {
  setStatus("加载中", "busy");
  const options = await requestJson("/api/options");
  state.options = options;
  state.savedAccounts = options.saved_accounts || {};
  state.siteSessions = options.site_sessions || {};
  if (!els.siteLoginUrl.value && Object.keys(state.siteSessions).length === 1) {
    els.siteLoginUrl.value = Object.values(state.siteSessions)[0].site_url || "";
  }
  fillSelect(els.timeRange, options.time_ranges || [], "近一周");
  updateCustomDateRange();
  fillSelect(
    els.collectLevel,
    (options.collect_levels || []).map((value) => ({
      id: value,
      name: COLLECT_LEVEL_COPY[value]?.label || value,
    })),
    "最小采集",
  );
  updateCollectionLimitCopy();
  fillSelect(els.templateSelect, options.templates || [], "event_report");
  renderChecks(els.stableSources, options.stable_sources || [], (options.stable_sources || []).length);
  renderChecks(els.socialPlatforms, options.social_platforms || [], 5);
  renderAccounts(options.social_platforms || [], state.savedAccounts);
  renderSiteSessionStatus();
  els.complianceNotice.textContent = options.compliance_notice || els.complianceNotice.textContent;
  updateSelectButtons();
  renderLatest(options.latest);
  applyHistoryCatalog(options.history_catalog || { history: options.task_history || [] });
  await loadMonitors();
  if (!state.monitorPoll) {
    state.monitorPoll = setInterval(() => {
      if (state.activeView === "monitor") {
        loadMonitors().catch((error) => addLog(`监测状态刷新失败：${error.message}`));
      }
    }, 5000);
  }
  setStatus("待命");
  addLog("浏览器界面已就绪");
  addSourceLog("来源配置与账号状态加载完成", "success");
}

async function runCrawl(payload) {
  activateView("task");
  setBusy(true);
  setStatus("采集中", "busy");
  els.reportDownload.classList.add("hidden");
  renderReportPreview(null);
  addLog(`开始采集：${payload.topic || payload.keywords}`);
  try {
    const result = await requestJson("/api/crawl", {
      method: "POST",
      body: JSON.stringify({ ...payload, async: true }),
    });
    state.taskId = result.task_id;
    els.taskIdLabel.textContent = result.task_id;
    els.taskNote.textContent = "采集任务已启动";
    setTaskProgress(8);
    addLog(result.message || "采集任务已启动");
    startTaskPolling(result.task_id);
  } catch (error) {
    setStatus("采集失败", "error");
    addLog(error.message);
    setBusy(false);
  }
}

function startTaskPolling(taskId) {
  if (state.taskPoll) {
    clearInterval(state.taskPoll);
  }
  const tick = async () => {
    try {
      const result = await requestJson(`/api/task?id=${encodeURIComponent(taskId)}`);
      renderTask(result.task);
      if (["done", "blocked", "not_met", "error"].includes(result.task.status)) {
        clearInterval(state.taskPoll);
        state.taskPoll = null;
        setBusy(false);
        try {
          await refreshAccountStatuses();
        } catch (error) {
          addSourceLog(`网站会话状态刷新失败：${error.message}`, "warning");
        }
        const isSourceAcceptance = Boolean(result.task.payload?.source_acceptance);
        if (result.task.status === "done") {
          if (isSourceAcceptance) {
            renderSourceHealth((result.task.latest || {}).meta || {});
          } else {
            renderLatest(result.task.latest);
          }
          setStatus(isSourceAcceptance ? "验收通过" : "采集完成");
          addLog(result.task.message || "采集完成");
        } else if (result.task.status === "blocked") {
          if (isSourceAcceptance) {
            renderSourceHealth((result.task.latest || {}).meta || {});
          } else {
            renderLatest(result.task.latest);
          }
          setStatus("采集受阻", "error");
          addLog(result.task.message || "所有来源均被访问策略阻止");
        } else if (result.task.status === "not_met") {
          if (isSourceAcceptance) {
            renderSourceHealth((result.task.latest || {}).meta || {});
          } else {
            renderLatest(result.task.latest);
          }
          setStatus("验收未通过", "error");
          addLog(result.task.message || "验收未达到最低结果数");
        } else {
          setStatus("采集失败", "error");
          addLog(result.task.message || "采集失败");
        }
      }
    } catch (error) {
      clearInterval(state.taskPoll);
      state.taskPoll = null;
      setBusy(false);
      setStatus("轮询失败", "error");
      addLog(error.message);
    }
  };
  tick();
  state.taskPoll = setInterval(tick, 1200);
}

function renderTask(task) {
  const events = task.events || [];
  const sourceStarts = events.filter((event) => event.type === "source_start").length;
  const sourceDone = events.filter((event) => event.type === "source_success" || event.type === "source_failure").length;
  const terminal = ["done", "blocked", "not_met", "error"].includes(task.status);
  let percent = terminal ? 100 : 8;
  if (sourceStarts) {
    percent = Math.max(8, Math.min(96, Math.round((sourceDone / sourceStarts) * 100)));
  }
  setTaskProgress(percent);
  els.taskIdLabel.textContent = task.task_id || "无任务";
  els.taskNote.textContent = task.message || task.last_event || "任务运行中";
  renderEvents(events);
}

async function refreshAccountStatuses() {
  const result = await requestJson("/api/accounts");
  state.savedAccounts = result.accounts || {};
  state.siteSessions = result.site_sessions || {};
  renderAccounts((state.options || {}).social_platforms || [], state.savedAccounts);
  renderSiteSessionStatus();
  return state.savedAccounts;
}

async function openLoginPage(card) {
  const platform = card.dataset.platform;
  const button = card.querySelector("[data-action='open-login']");
  button.disabled = true;
  try {
    const result = await requestJson("/api/browser-login/start", {
      method: "POST",
      body: JSON.stringify({ platform }),
    });
    const loginUrl = result.url || "";
    const opened = loginUrl ? window.open(loginUrl, "_blank") : null;
    if (opened) {
      addSourceLog(`${platform}: 辅助登录浏览器已打开，登录完成后回到本页保存会话`, "success");
    } else {
      addSourceLog(
        `${platform}: ${result.message || "网页登录地址已生成"} ${loginUrl ? `请手动打开：${loginUrl}` : ""}`,
        "warning",
      );
    }
  } catch (error) {
    addSourceLog(`${platform}: 打开网页登录失败，${error.message}`, "error");
  } finally {
    button.disabled = false;
  }
}

async function saveBrowserSession(card) {
  const platform = card.dataset.platform;
  const button = card.querySelector("[data-action='save-browser-session']");
  button.disabled = true;
  button.textContent = "保存中";
  try {
    const result = await requestJson("/api/browser-login/save", {
      method: "POST",
      body: JSON.stringify({ platform, profile: "Default" }),
    });
    state.savedAccounts = result.accounts || {};
    renderAccounts((state.options || {}).social_platforms || [], state.savedAccounts);
    const imported = result.saved || {};
    addSourceLog(`${platform}: 浏览器会话已保存，Cookie ${imported.cookie_count || 0} 个，已加密保存`, "success");
  } catch (error) {
    addSourceLog(`${platform}: 保存浏览器会话失败，${error.message}`, "error");
  } finally {
    button.disabled = false;
    button.textContent = "保存会话";
  }
}

async function closeBrowserSession(card) {
  const platform = card.dataset.platform;
  const button = card.querySelector("[data-action='close-browser-session']");
  button.disabled = true;
  try {
    const result = await requestJson("/api/browser-login/close", {
      method: "POST",
      body: JSON.stringify({ platform }),
    });
    state.savedAccounts = result.accounts || {};
    renderAccounts((state.options || {}).social_platforms || [], state.savedAccounts);
    addSourceLog(`${platform}: ${result.message || "辅助登录浏览器已关闭"}`, "success");
  } catch (error) {
    addSourceLog(`${platform}: 关闭辅助登录浏览器失败，${error.message}`, "error");
  } finally {
    button.disabled = false;
  }
}

async function saveAccount(card) {
  const platform = card.dataset.platform;
  const button = card.querySelector("[data-action='save-account']");
  button.disabled = true;
  button.textContent = "保存中";
  try {
    const result = await requestJson("/api/accounts/save", {
      method: "POST",
      body: JSON.stringify({ platform, account: accountFromCard(card) }),
    });
    state.savedAccounts = result.accounts || {};
    renderAccounts((state.options || {}).social_platforms || [], state.savedAccounts);
    addSourceLog(`${platform}: 授权信息已加密保存`, "success");
  } catch (error) {
    addSourceLog(`${platform}: 保存失败，${error.message}`, "error");
  } finally {
    button.disabled = false;
    button.textContent = "保存授权";
  }
}

async function clearAccount(card) {
  const platform = card.dataset.platform;
  const button = card.querySelector("[data-action='clear-account']");
  button.disabled = true;
  try {
    const result = await requestJson("/api/accounts/clear", {
      method: "POST",
      body: JSON.stringify({ platform }),
    });
    state.savedAccounts = result.accounts || {};
    renderAccounts((state.options || {}).social_platforms || [], state.savedAccounts);
    addSourceLog(`${platform}: 授权信息已清除`, "success");
  } catch (error) {
    addSourceLog(`${platform}: 清除失败，${error.message}`, "error");
  } finally {
    button.disabled = false;
  }
}

async function testAccount(card, refreshStatuses = true) {
  const platform = card.dataset.platform;
  const account = accountFromCard(card);
  const button = card.querySelector("[data-action='test-account']");
  button.disabled = true;
  button.textContent = "测试中";
  addSourceLog(`正在测试 ${platform} 授权`, "info");
  try {
    const result = await requestJson("/api/test-account", {
      method: "POST",
      body: JSON.stringify({
        platform,
        account,
        keyword: els.keywords.value.split(/[，,]/)[0] || "警方通报",
        use_system_proxy: els.useSystemProxy.checked,
        enable_debug_snapshots: els.saveDiagnostics.checked,
      }),
    });
    const testState = platformTestState(result);
    button.textContent = testState.passed
      ? "完全通过"
      : (testState.readPassed ? "登录未通过" : (testState.loginPassed ? "采集未通过" : "测试未通过"));
    const loginText = describeLoginStatus(result);
    const readText = testState.readPassed
      ? `真实采集通过（${testState.count} 条有效结果）`
      : "真实采集未通过";
    addSourceLog(
      `${platform}: ${loginText}；${readText}；结论：${testState.passed ? "完全通过" : "未通过"}。证据: ${result.evidence || "无"}`,
      testState.passed ? "success" : "warning",
    );
    if (refreshStatuses) await refreshAccountStatuses();
    return result;
  } catch (error) {
    button.textContent = "测试未通过";
    addSourceLog(`${platform}: ${error.message}`, "error");
    return null;
  } finally {
    button.disabled = false;
  }
}

async function testAllAccounts() {
  const targetPlatforms = ["微博", "B站", "小红书", "抖音", "百度贴吧"];
  const cards = [...els.accountGrid.querySelectorAll(".account-card")].filter((card) =>
    targetPlatforms.includes(card.dataset.platform),
  );
  if (!cards.length) return;

  els.testAllAccountsBtn.disabled = true;
  addSourceLog("开始批量实测五个核心社交平台", "info");
  let loginPassed = 0;
  let readPassed = 0;
  let fullyPassed = 0;
  try {
    for (let index = 0; index < cards.length; index += 1) {
      const card = cards[index];
      els.testAllAccountsBtn.textContent = `正在测试 ${index + 1}/${cards.length}`;
      const result = await testAccount(card, false);
      const testState = platformTestState(result || {});
      if (testState.loginPassed) loginPassed += 1;
      if (testState.readPassed) readPassed += 1;
      if (testState.passed) fullyPassed += 1;
    }
    await refreshAccountStatuses();
    addSourceLog(
      `批量实测完成：登录 ${loginPassed}/${cards.length} · 采集 ${readPassed}/${cards.length} · 完全通过 ${fullyPassed}/${cards.length}`,
      fullyPassed === cards.length ? "success" : "warning",
    );
  } finally {
    els.testAllAccountsBtn.disabled = false;
    els.testAllAccountsBtn.textContent = "批量实测五个平台";
  }
}

async function generateReport() {
  const review = state.latest?.meta?.review || {};
  const reviewedCurrentData = review.reviewed_at
    && review.labels_confirmed
    && Number(review.kept_total) === Number(state.latest?.total || 0);
  if (!reviewedCurrentData) {
    activateView("review");
    setStatus("等待人工审核", "error");
    addLog("请先逐条核对数据并点击“保存审核结果”，再生成 Word 报告");
    return;
  }
  if (!state.reportDraft) {
    activateView("report");
    setStatus("等待报告预览", "error");
    addLog("请先生成报告预览，检查并修改正文后再生成 Word 报告");
    return;
  }
  const previewFilter = state.reportDraft.scope?.filters || {};
  if (JSON.stringify(previewFilter) !== JSON.stringify(currentReportFilter())) {
    setStatus("报告范围已变化", "error");
    addLog("当前筛选条件与报告预览不一致，请重新生成预览");
    return;
  }
  const sectionOverrides = {};
  els.reportPreview.querySelectorAll(".report-section-editor").forEach((editor) => {
    if (editor.dataset.sectionId && editor.value.trim()) {
      sectionOverrides[editor.dataset.sectionId] = editor.value.trim();
    }
  });
  setBusy(true);
  setStatus("生成报告中", "busy");
  addLog("开始生成 Word 报告");
  try {
    const result = await requestJson("/api/report", {
      method: "POST",
      body: JSON.stringify({
        template_id: els.templateSelect.value,
        region: els.region.value.trim(),
        time_range: selectedTimeRange(),
        section_overrides: sectionOverrides,
        report_filter: currentReportFilter(),
        ai_report_scope_token: state.appliedAiReportScopeToken,
      }),
    });
    els.reportDownload.href = result.download_url;
    els.reportDownload.textContent = "下载报告";
    els.reportDownload.classList.remove("hidden");
    if (result.history_catalog) {
      applyHistoryCatalog(result.history_catalog);
    }
    setStatus("报告完成");
    addLog(`${result.message}: ${result.output_path}`);
  } catch (error) {
    setStatus("报告失败", "error");
    addLog(error.message);
  } finally {
    setBusy(false);
  }
}

async function saveReview() {
  const rows = [...els.resultBody.querySelectorAll("tr[data-index]")];
  if (!rows.length) {
    setStatus("没有可审核数据", "error");
    addLog("请先完成采集，再保存审核结果");
    return;
  }
  const reviews = rows.map((row) => ({
    index: Number(row.dataset.index),
    keep: Boolean(row.querySelector(".review-check")?.checked),
    content_category: row.querySelector(".review-category")?.value || "其他",
    sentiment_label: row.querySelector(".review-sentiment")?.value || "中性",
    note: row.querySelector(".review-note")?.value || "",
  }));
  const keptCount = reviews.filter((item) => item.keep).length;
  setBusy(true);
  setStatus("保存审核中", "busy");
  try {
    const result = await requestJson("/api/review-save", {
      method: "POST",
      body: JSON.stringify({ reviews }),
    });
    renderLatest(result.latest);
    renderReportPreview(null);
    els.reportDownload.classList.add("hidden");
    setStatus("审核已保存");
    const summary = result.latest?.meta?.review || {};
    addLog(
      `审核已保存，保留 ${keptCount} 条；修改分类 ${summary.category_changed_count || 0} 条，`
      + `修改情感 ${summary.sentiment_changed_count || 0} 条`,
    );
  } catch (error) {
    setStatus("审核失败", "error");
    addLog(error.message);
  } finally {
    setBusy(false);
  }
}

function setRowChecks(mode) {
  const checks = [...els.resultBody.querySelectorAll("tr[data-index]:not([hidden]) .review-check")];
  checks.forEach((check) => {
    check.checked = mode === "invert" ? !check.checked : true;
  });
}

function monitorStatusInfo(plan = {}) {
  if (plan.status === "paused") return { label: "已暂停", tone: "paused" };
  if (plan.status === "stopped") return { label: "已停止", tone: "stopped" };
  const mapping = {
    waiting: { label: "等待运行", tone: "waiting" },
    running: { label: "正在采集", tone: "running" },
    normal: { label: "运行正常", tone: "normal" },
    warning: { label: "出现失败", tone: "warning" },
    late: { label: "执行延迟", tone: "warning" },
    needs_attention: { label: "需要人工处理", tone: "attention" },
  };
  return mapping[plan.runtime_status] || mapping.waiting;
}

function formatMonitorTime(value) {
  if (!value) return "尚未运行";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value).replace("T", " ").slice(0, 19);
  return parsed.toLocaleString("zh-CN", { hour12: false });
}

function monitorTitle(plan = {}) {
  const payload = plan.payload || {};
  return payload.topic || (payload.keywords || []).join("、") || "未命名监测";
}

function monitorMetaText(plan = {}) {
  const payload = plan.payload || {};
  const strategy = ["stable_first", "hybrid"].includes(payload.source_strategy)
    ? "all"
    : (payload.source_strategy || "all");
  const sourceCount =
    ((strategy === "all" || strategy === "stable") ? (payload.stable_sources || []).length : 0)
    + ((strategy === "all" || strategy === "public_news") ? 1 : 0)
    + ((strategy === "all" || strategy === "social") ? (payload.social_platforms || []).length : 0);
  return `每 ${plan.interval_minutes || "-"} 分钟 · ${sourceCount} 个来源 · 累计新增 ${plan.total_new || 0} 条`;
}

function renderMonitorMetrics(plans = []) {
  const active = plans.filter((plan) => plan.status === "active").length;
  const newCount = plans.reduce((sum, plan) => sum + Number(plan.total_new || 0), 0);
  const attention = plans.filter((plan) => plan.runtime_status === "needs_attention").length;
  els.monitorPlanCount.textContent = String(active);
  els.monitorNewCount.textContent = String(newCount);
  els.monitorAttentionCount.textContent = String(attention);
  els.navMonitorCount.textContent = String(active);
}

function renderMonitorPlans(plans = []) {
  els.monitorPlanList.innerHTML = "";
  if (!plans.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    const title = document.createElement("strong");
    title.textContent = "尚未创建监测计划";
    const hint = document.createElement("span");
    hint.textContent = "在“新建任务”中填写主题、关键词和来源，再选择监测间隔。";
    empty.append(title, hint);
    els.monitorPlanList.appendChild(empty);
    return;
  }
  plans.forEach((plan) => {
    const status = monitorStatusInfo(plan);
    const button = document.createElement("button");
    button.type = "button";
    button.className = `monitor-plan-card${state.selectedMonitorId === plan.id ? " selected" : ""}`;
    button.dataset.monitorId = plan.id;

    const header = document.createElement("span");
    header.className = "monitor-plan-card-header";
    const title = document.createElement("strong");
    title.textContent = monitorTitle(plan);
    const badge = document.createElement("span");
    badge.className = `monitor-status ${status.tone}`;
    badge.textContent = status.label;
    header.append(title, badge);

    const meta = document.createElement("span");
    meta.className = "monitor-plan-meta";
    meta.textContent = monitorMetaText(plan);
    const message = document.createElement("span");
    message.className = "monitor-plan-message";
    message.textContent = plan.last_message || "等待首次运行";
    button.append(header, meta, message);
    els.monitorPlanList.appendChild(button);
  });
}

function appendMonitorFact(root, labelText, valueText) {
  const item = document.createElement("div");
  item.className = "monitor-fact";
  const label = document.createElement("span");
  label.textContent = labelText;
  const value = document.createElement("strong");
  value.textContent = valueText || "-";
  item.append(label, value);
  root.appendChild(item);
}

function buildMonitorActions(plan) {
  const actions = document.createElement("div");
  actions.className = "monitor-actions";
  if (plan.status !== "stopped") {
    const run = document.createElement("button");
    run.type = "button";
    run.className = "secondary-btn";
    run.dataset.monitorAction = "run_now";
    run.textContent = "立即运行";
    actions.appendChild(run);
  }
  if (plan.status === "active") {
    const pause = document.createElement("button");
    pause.type = "button";
    pause.className = "quiet-btn";
    pause.dataset.monitorAction = "pause";
    pause.textContent = "暂停";
    actions.appendChild(pause);
  } else {
    const resume = document.createElement("button");
    resume.type = "button";
    resume.className = "quiet-btn";
    resume.dataset.monitorAction = "resume";
    resume.textContent = plan.status === "stopped" ? "重新启动" : "继续";
    actions.appendChild(resume);
  }
  if (plan.status !== "stopped") {
    const stop = document.createElement("button");
    stop.type = "button";
    stop.className = "text-btn danger";
    stop.dataset.monitorAction = "stop";
    stop.textContent = "停止";
    actions.appendChild(stop);
  }
  return actions;
}

function renderMonitorClues(root, clues = []) {
  const section = document.createElement("section");
  section.className = "monitor-detail-section";
  const heading = document.createElement("div");
  heading.className = "monitor-subheading";
  const title = document.createElement("h4");
  title.textContent = "新增线索";
  const count = document.createElement("span");
  count.textContent = `${clues.length} 条已保留`;
  heading.append(title, count);
  section.appendChild(heading);
  if (!clues.length) {
    const empty = document.createElement("p");
    empty.className = "monitor-empty-copy";
    empty.textContent = "暂未发现基线之后的新线索。";
    section.appendChild(empty);
  } else {
    const list = document.createElement("div");
    list.className = "monitor-clue-list";
    clues.slice(0, 100).forEach((clue) => {
      const item = document.createElement("article");
      item.className = "monitor-clue";
      const link = document.createElement(clue.url ? "a" : "strong");
      link.textContent = clue.title || "（无标题线索）";
      if (clue.url) {
        link.href = clue.url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.title = "打开原内容";
      }
      const meta = document.createElement("span");
      meta.textContent = `${clue.platform || clue.source || "未知来源"} · ${clue.pub_time || "时间未知"} · 首次发现 ${formatMonitorTime(clue.first_seen_at)}`;
      const excerpt = document.createElement("p");
      excerpt.textContent = clue.content_excerpt || "无正文摘录，请打开原内容核对。";
      item.append(link, meta, excerpt);
      list.appendChild(item);
    });
    section.appendChild(list);
  }
  root.appendChild(section);
}

function renderMonitorRuns(root, runs = []) {
  const section = document.createElement("section");
  section.className = "monitor-detail-section";
  const heading = document.createElement("div");
  heading.className = "monitor-subheading";
  const title = document.createElement("h4");
  title.textContent = "最近运行记录";
  const hint = document.createElement("span");
  hint.textContent = "最多显示 50 次";
  heading.append(title, hint);
  section.appendChild(heading);
  if (!runs.length) {
    const empty = document.createElement("p");
    empty.className = "monitor-empty-copy";
    empty.textContent = "计划尚未完成首次运行。";
    section.appendChild(empty);
  } else {
    const list = document.createElement("div");
    list.className = "monitor-run-list";
    const statusLabels = {
      baseline: "建立基线",
      success: "成功",
      warning: "部分来源失败",
      failure: "失败",
    };
    runs.forEach((run) => {
      const item = document.createElement("div");
      item.className = `monitor-run ${run.status || ""}`;
      const marker = document.createElement("span");
      marker.className = "monitor-run-marker";
      marker.textContent = statusLabels[run.status] || run.status || "运行";
      const body = document.createElement("span");
      body.className = "monitor-run-body";
      const message = document.createElement("strong");
      message.textContent = run.message || "运行完成";
      const meta = document.createElement("small");
      meta.textContent = `${formatMonitorTime(run.completed_at)} · 取得 ${run.records_found || 0} 条 · 新增 ${run.new_count || 0} 条`;
      body.append(message, meta);
      item.append(marker, body);
      list.appendChild(item);
    });
    section.appendChild(list);
  }
  root.appendChild(section);
}

function renderMonitorDetail(plan) {
  els.monitorDetail.innerHTML = "";
  if (!plan) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    const title = document.createElement("strong");
    title.textContent = "选择一个监测计划";
    const hint = document.createElement("span");
    hint.textContent = "这里会显示计划状态、新增线索和最近运行记录。";
    empty.append(title, hint);
    els.monitorDetail.appendChild(empty);
    return;
  }
  const status = monitorStatusInfo(plan);
  const header = document.createElement("div");
  header.className = "monitor-detail-header";
  const copy = document.createElement("div");
  const kicker = document.createElement("span");
  kicker.className = "section-kicker";
  kicker.textContent = `每 ${plan.interval_minutes} 分钟`;
  const title = document.createElement("h3");
  title.textContent = monitorTitle(plan);
  const message = document.createElement("p");
  message.textContent = plan.last_message || "等待运行";
  copy.append(kicker, title, message);
  const badge = document.createElement("span");
  badge.className = `monitor-status large ${status.tone}`;
  badge.textContent = status.label;
  header.append(copy, badge);
  els.monitorDetail.append(header, buildMonitorActions(plan));

  const facts = document.createElement("div");
  facts.className = "monitor-facts";
  appendMonitorFact(facts, "上次完成", formatMonitorTime(plan.last_completed_at));
  appendMonitorFact(facts, "下次运行", plan.status === "active" ? formatMonitorTime(plan.next_run_at) : "不会自动运行");
  appendMonitorFact(facts, "连续失败", `${plan.consecutive_failures || 0} 次`);
  appendMonitorFact(facts, "基线记录", `${plan.known_fingerprint_count || 0} 条`);
  els.monitorDetail.appendChild(facts);

  const payload = plan.payload || {};
  const conditions = document.createElement("p");
  conditions.className = "monitor-conditions";
  conditions.textContent = `关键词：${(payload.keywords || []).join("、") || "未填写"}；范围：${payload.time_range || "-"}；来源：${[...(payload.stable_sources || []), ...(payload.social_platforms || [])].join("、") || "未选择"}`;
  els.monitorDetail.appendChild(conditions);
  renderMonitorClues(els.monitorDetail, plan.new_items || []);
  renderMonitorRuns(els.monitorDetail, plan.runs || []);
}

async function loadMonitors(preferredId = state.selectedMonitorId) {
  const query = preferredId ? `?id=${encodeURIComponent(preferredId)}` : "";
  let result;
  try {
    result = await requestJson(`/api/monitors${query}`);
  } catch (error) {
    if (!preferredId) throw error;
    state.selectedMonitorId = null;
    result = await requestJson("/api/monitors");
  }
  state.monitorPlans = result.plans || [];
  state.selectedMonitorId = result.selected?.id || null;
  renderMonitorMetrics(state.monitorPlans);
  renderMonitorPlans(state.monitorPlans);
  renderMonitorDetail(result.selected || null);
  return result;
}

async function createMonitorPlan() {
  if (!validateTaskForm()) return;
  const interval = Number(els.monitorInterval.value || 0);
  if (![15, 30, 60].includes(interval)) {
    setStatus("请选择监测间隔", "error");
    addLog("创建监测计划前，请选择每 15、30 或 60 分钟运行");
    els.monitorInterval.focus();
    return;
  }
  els.monitorBtn.disabled = true;
  els.monitorBtn.textContent = "创建中";
  setStatus("创建监测计划中", "busy");
  try {
    const result = await requestJson("/api/monitors/create", {
      method: "POST",
      body: JSON.stringify({ interval_minutes: interval, payload: collectPayload() }),
    });
    state.selectedMonitorId = result.plan?.id || null;
    await loadMonitors(state.selectedMonitorId);
    activateView("monitor");
    setStatus("监测计划已创建");
    addLog(result.message || "监测计划已创建");
  } catch (error) {
    setStatus("创建监测失败", "error");
    addLog(error.message);
  } finally {
    els.monitorBtn.disabled = false;
    els.monitorBtn.textContent = "创建监测计划";
  }
}

async function runMonitorAction(action) {
  if (!state.selectedMonitorId) return;
  setStatus("更新监测计划中", "busy");
  try {
    const result = await requestJson("/api/monitors/action", {
      method: "POST",
      body: JSON.stringify({ monitor_id: state.selectedMonitorId, action }),
    });
    await loadMonitors(state.selectedMonitorId);
    setStatus("监测计划已更新");
    addLog(result.message || "监测计划已更新");
  } catch (error) {
    setStatus("监测操作失败", "error");
    addLog(error.message);
  }
}

els.form.addEventListener("submit", (event) => {
  event.preventDefault();
  if (!validateTaskForm()) return;
  runCrawl(collectPayload());
});

els.timeRange.addEventListener("change", updateCustomDateRange);
els.collectLevel.addEventListener("change", updateCollectionLimitCopy);
els.templateSelect.addEventListener("change", () => {
  renderReportPreview(null);
  els.reportDownload.classList.add("hidden");
  addLog("报告模板已更改，请重新生成预览");
});
els.startDate.addEventListener("change", () => els.endDate.setCustomValidity(""));
els.endDate.addEventListener("change", () => els.endDate.setCustomValidity(""));

els.refreshBtn.addEventListener("click", () => {
  refreshLatest().catch((error) => {
    setStatus("刷新失败", "error");
    addLog(error.message);
  });
});
els.logoutBtn.addEventListener("click", logoutSystem);
els.accountSecurityBtn.addEventListener("click", openAccountSecurity);
els.changePasswordForm.addEventListener("submit", changeSystemPassword);
els.recoveryCodeForm.addEventListener("submit", rotateSystemRecoveryCode);
els.copyAccountRecoveryCode.addEventListener("click", copySystemRecoveryCode);
els.newPasswordConfirm.addEventListener("input", () => {
  els.newPasswordConfirm.setCustomValidity("");
});

els.reportBtn.addEventListener("click", generateReport);
els.reportPreviewBtn.addEventListener("click", previewReport);
els.aiExternalSendConfirm.addEventListener("change", updateAiGenerateAvailability);
els.aiGenerateBtn.addEventListener("click", generateAiReportDraft);
els.aiApplyBtn.addEventListener("click", applyAiDraftToPreview);
els.aiDiscardBtn.addEventListener("click", discardAiReportDraft);
els.summarySourceBtn.addEventListener("click", () => generateEvidenceSummary("source", null, els.summarySourceBtn));
els.summaryFilteredBtn.addEventListener("click", () => generateEvidenceSummary("filtered", null, els.summaryFilteredBtn));
els.saveReviewBtn.addEventListener("click", saveReview);
els.selectAllRows.addEventListener("click", () => setRowChecks("all"));
els.invertRows.addEventListener("click", () => setRowChecks("invert"));
els.reviewSourceFilter.addEventListener("change", () => {
  applyReviewFilters();
  clearEvidenceSummary();
  invalidateReportForScopeChange();
});
els.reviewCategoryFilter.addEventListener("change", () => {
  applyReviewFilters();
  clearEvidenceSummary();
  invalidateReportForScopeChange();
});
els.reviewSentimentFilter.addEventListener("change", () => {
  applyReviewFilters();
  clearEvidenceSummary();
  invalidateReportForScopeChange();
});
els.clearReviewFilters.addEventListener("click", () => {
  els.reviewSourceFilter.value = "";
  els.reviewCategoryFilter.value = "";
  els.reviewSentimentFilter.value = "";
  applyReviewFilters();
  clearEvidenceSummary();
  invalidateReportForScopeChange();
});
els.monitorBtn.addEventListener("click", createMonitorPlan);
els.monitorRefreshBtn.addEventListener("click", () => {
  loadMonitors()
    .then(() => setStatus("监测状态已刷新"))
    .catch((error) => {
      setStatus("监测状态刷新失败", "error");
      addLog(error.message);
    });
});
els.monitorPlanList.addEventListener("click", (event) => {
  const card = event.target.closest("[data-monitor-id]");
  if (!card) return;
  state.selectedMonitorId = card.dataset.monitorId;
  loadMonitors(state.selectedMonitorId).catch((error) => addLog(error.message));
});
els.monitorDetail.addEventListener("click", (event) => {
  const button = event.target.closest("[data-monitor-action]");
  if (!button) return;
  runMonitorAction(button.dataset.monitorAction);
});

els.toggleAccounts.addEventListener("click", () => {
  const hidden = els.accountGrid.classList.toggle("hidden");
  els.siteSessionCard.classList.toggle("hidden", hidden);
  els.toggleAccounts.textContent = hidden ? "展开" : "收起";
});
els.siteLoginUrl.addEventListener("input", () => {
  els.siteLoginUrl.setCustomValidity("");
  renderSiteSessionStatus();
});
els.openSiteLoginBtn.addEventListener("click", openSiteLogin);
els.saveSiteSessionBtn.addEventListener("click", saveSiteSession);
els.closeSiteLoginBtn.addEventListener("click", closeSiteLogin);
els.clearSiteSessionBtn.addEventListener("click", clearSiteSession);
els.testAllAccountsBtn.addEventListener("click", testAllAccounts);
els.clearSourceLogBtn.addEventListener("click", clearSourceLog);
els.toggleHistoryBtn.addEventListener("click", toggleTaskHistory);
els.closeHistoryDetail.addEventListener("click", closeHistoryDetail);
els.loadHistoryBtn.addEventListener("click", loadHistoryTask);
els.reuseHistoryBtn.addEventListener("click", reuseHistoryConditions);
els.deleteHistoryBtn.addEventListener("click", deleteHistoryTask);
els.createHistoryBackupBtn.addEventListener("click", () => {
  openHistoryDialog(els.historyBackupDialog, els.historyBackupForm);
  els.historyBackupPassphrase.focus();
});
els.restoreHistoryBackupBtn.addEventListener("click", () => {
  openHistoryDialog(els.historyRestoreDialog, els.historyRestoreForm);
  els.historyRestoreFile.focus();
});
els.historyBackupForm.addEventListener("submit", createHistoryBackup);
els.historyRestoreForm.addEventListener("submit", restoreHistoryBackup);
els.historyBackupPassphrase.addEventListener("input", () => {
  els.historyBackupPassphrase.setCustomValidity("");
});
els.historyBackupPassphraseConfirm.addEventListener("input", () => {
  els.historyBackupPassphraseConfirm.setCustomValidity("");
});
els.historyRestoreFile.addEventListener("change", () => {
  els.historyRestoreFile.setCustomValidity("");
});
document.querySelectorAll("[data-dialog-close]").forEach((button) => {
  button.addEventListener("click", () => {
    const dialog = document.getElementById(button.dataset.dialogClose);
    if (dialog) closeHistoryDialog(dialog);
  });
});
els.useSystemProxy.addEventListener("change", () => {
  addSourceLog(`系统代理已${els.useSystemProxy.checked ? "启用" : "关闭"}`, "info");
});
els.saveDiagnostics.addEventListener("change", () => {
  addSourceLog(`失败诊断快照已${els.saveDiagnostics.checked ? "启用" : "关闭"}`, "info");
});

els.accountGrid.addEventListener("click", (event) => {
  const button = event.target.closest("[data-action]");
  if (!button) return;
  const card = button.closest(".account-card");
  if (button.dataset.action === "open-login") {
    openLoginPage(card);
  } else if (button.dataset.action === "save-browser-session") {
    saveBrowserSession(card);
  } else if (button.dataset.action === "close-browser-session") {
    closeBrowserSession(card);
  } else if (button.dataset.action === "test-account") {
    testAccount(card);
  } else if (button.dataset.action === "save-account") {
    saveAccount(card);
  } else if (button.dataset.action === "clear-account") {
    clearAccount(card);
  }
});

document.querySelectorAll("[data-select]").forEach((button) => {
  button.addEventListener("click", () => {
    const target = button.dataset.select === "stable" ? els.stableSources : els.socialPlatforms;
    const inputs = [...target.querySelectorAll("input")];
    const allChecked = inputs.every((input) => input.checked);
    inputs.forEach((input) => {
      input.checked = !allChecked;
    });
    updateSelectButtons();
    updateSourceSummary();
    const groupName = button.dataset.select === "stable" ? "政府官网" : "社交平台";
    addSourceLog(`${groupName}已${allChecked ? "全部取消" : "全部选择"}`, "info");
  });
});

document.querySelectorAll("input[name='sourceStrategy']").forEach((input) => {
  input.addEventListener("change", updateSourceSummary);
});

document.querySelectorAll("[data-view-target]").forEach((button) => {
  button.addEventListener("click", () => activateView(button.dataset.viewTarget));
});

els.globalOperationsToggle.addEventListener("click", () => {
  setGlobalOperationsExpanded(!state.globalOperationsExpanded);
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && state.globalOperationsExpanded) {
    setGlobalOperationsExpanded(false);
    els.globalOperationsToggle.focus();
  }
});

activateView(location.hash.replace("#", "") || "task", false);
setGlobalOperationsExpanded(false);

loadIdentity().then(loadOptions).catch((error) => {
  setStatus("加载失败", "error");
  addLog(error.message);
});
