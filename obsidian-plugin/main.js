var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __export = (target, all) => {
  for (var name in all)
    __defProp(target, name, { get: all[name], enumerable: true });
};
var __copyProps = (to, from, except, desc) => {
  if (from && typeof from === "object" || typeof from === "function") {
    for (let key of __getOwnPropNames(from))
      if (!__hasOwnProp.call(to, key) && key !== except)
        __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
  }
  return to;
};
var __toCommonJS = (mod) => __copyProps(__defProp({}, "__esModule", { value: true }), mod);

// src/main.ts
var main_exports = {};
__export(main_exports, {
  default: () => AutoSkillPlugin
});
module.exports = __toCommonJS(main_exports);
var import_obsidian5 = require("obsidian");

// src/settings.ts
var import_obsidian = require("obsidian");
var DEFAULT_SETTINGS = {
  backendUrl: "http://localhost:8420",
  embeddingModel: "nomic-embed-text",
  taggingModel: "gemma-4-26b-a4b-it-4bit",
  fastPathThreshold: 0.9,
  maxTags: 20,
  pollInterval: 3e4
};
var AutoSkillSettingTab = class extends import_obsidian.PluginSettingTab {
  constructor(app, plugin) {
    super(app, plugin);
    this.plugin = plugin;
  }
  display() {
    const { containerEl } = this;
    containerEl.empty();
    containerEl.createEl("h2", { text: "AutoSkill Settings" });
    new import_obsidian.Setting(containerEl).setName("Backend URL").setDesc("URL of the AutoSkill Python backend").addText((text) => text.setPlaceholder("http://localhost:8420").setValue(this.plugin.settings.backendUrl).onChange(async (value) => {
      this.plugin.settings.backendUrl = value;
      await this.plugin.saveSettings();
    }));
    new import_obsidian.Setting(containerEl).setName("Embedding model").setDesc("Model name for embeddings").addText((text) => text.setValue(this.plugin.settings.embeddingModel).onChange(async (value) => {
      this.plugin.settings.embeddingModel = value;
      await this.plugin.saveSettings();
    }));
    new import_obsidian.Setting(containerEl).setName("Tagging model").setDesc("LLM model for auto-tagging").addText((text) => text.setValue(this.plugin.settings.taggingModel).onChange(async (value) => {
      this.plugin.settings.taggingModel = value;
      await this.plugin.saveSettings();
    }));
    new import_obsidian.Setting(containerEl).setName("Fast path threshold").setDesc("Similarity threshold for inheriting tags (0.0\u20131.0)").addText((text) => text.setValue(String(this.plugin.settings.fastPathThreshold)).onChange(async (value) => {
      const num = parseFloat(value);
      if (!isNaN(num) && num >= 0 && num <= 1) {
        this.plugin.settings.fastPathThreshold = num;
        await this.plugin.saveSettings();
      }
    }));
    new import_obsidian.Setting(containerEl).setName("Max tags per document").setDesc("Maximum number of tags assigned to each document").addText((text) => text.setValue(String(this.plugin.settings.maxTags)).onChange(async (value) => {
      const num = parseInt(value);
      if (!isNaN(num) && num > 0) {
        this.plugin.settings.maxTags = num;
        await this.plugin.saveSettings();
      }
    }));
    new import_obsidian.Setting(containerEl).setName("Poll interval (ms)").setDesc("How often to check backend status").addText((text) => text.setValue(String(this.plugin.settings.pollInterval)).onChange(async (value) => {
      const num = parseInt(value);
      if (!isNaN(num) && num >= 5e3) {
        this.plugin.settings.pollInterval = num;
        await this.plugin.saveSettings();
      }
    }));
    new import_obsidian.Setting(containerEl).setName("Test connection").setDesc("Check if the backend is reachable").addButton((button) => button.setButtonText("Test").onClick(async () => {
      try {
        const health = await this.plugin.api.health();
        button.setButtonText(`\u2713 ${health.documents} docs`);
        setTimeout(() => button.setButtonText("Test"), 3e3);
      } catch (e) {
        button.setButtonText("\u2717 Failed");
        setTimeout(() => button.setButtonText("Test"), 3e3);
      }
    }));
  }
};

// src/api-client.ts
var import_obsidian2 = require("obsidian");
var ApiClient = class {
  constructor(baseUrl) {
    this.baseUrl = baseUrl;
  }
  async request(path, method = "GET", body) {
    const params = {
      url: `${this.baseUrl}${path}`,
      method,
      headers: { "Content-Type": "application/json" }
    };
    if (body) {
      params.body = JSON.stringify(body);
    }
    const resp = await (0, import_obsidian2.requestUrl)(params);
    return resp.json;
  }
  async health() {
    return this.request("/api/health");
  }
  async getInboxStatus() {
    return this.request("/api/inbox");
  }
  async getTags(prefix = "") {
    const q = prefix ? `?prefix=${encodeURIComponent(prefix)}` : "";
    return this.request(`/api/tags${q}`);
  }
  async getTagDocuments(tag) {
    return this.request(`/api/tags/${encodeURIComponent(tag)}`);
  }
  async getProposals() {
    return this.request("/api/proposals");
  }
  async getProposalDetail(id) {
    return this.request(`/api/proposals/${encodeURIComponent(id)}`);
  }
  async reviewProposal(id, accepted) {
    return this.request(`/api/proposals/${encodeURIComponent(id)}/review`, "POST", { accepted });
  }
  async search(query, n = 10) {
    return this.request(`/api/search?q=${encodeURIComponent(query)}&n=${n}`);
  }
  async reindex(path) {
    return this.request("/api/reindex", "POST", { path });
  }
};

// src/sidebar-view.ts
var import_obsidian3 = require("obsidian");
var VIEW_TYPE_AUTOSKILL = "autoskill-sidebar";
var AutoSkillSidebarView = class extends import_obsidian3.ItemView {
  constructor(leaf, plugin) {
    super(leaf);
    this.pollTimer = null;
    this.failCount = 0;
    this.plugin = plugin;
    this.backoffMs = plugin.settings.pollInterval;
  }
  getViewType() {
    return VIEW_TYPE_AUTOSKILL;
  }
  getDisplayText() {
    return "AutoSkill";
  }
  getIcon() {
    return "brain";
  }
  async onOpen() {
    this.renderLoading();
    await this.refresh();
    this.startPolling();
  }
  async onClose() {
    this.stopPolling();
  }
  startPolling() {
    this.stopPolling();
    this.pollTimer = window.setInterval(() => this.refresh(), this.backoffMs);
  }
  stopPolling() {
    if (this.pollTimer !== null) {
      window.clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
  }
  renderLoading() {
    const container = this.containerEl.children[1];
    container.empty();
    container.createEl("p", { text: "Connecting to backend...", cls: "autoskill-loading" });
  }
  async refresh() {
    try {
      const [inbox, tags, proposals] = await Promise.all([
        this.plugin.api.getInboxStatus(),
        this.plugin.api.getTags(),
        this.plugin.api.getProposals()
      ]);
      this.failCount = 0;
      this.backoffMs = this.plugin.settings.pollInterval;
      this.render(inbox, tags, proposals);
    } catch (e) {
      this.failCount++;
      if (this.failCount >= 3) {
        this.backoffMs = Math.min(this.backoffMs * 2, 3e4);
        this.stopPolling();
        this.startPolling();
      }
      this.renderError();
    }
  }
  renderError() {
    const container = this.containerEl.children[1];
    container.empty();
    container.createEl("p", {
      text: `Backend unreachable. Retrying in ${Math.round(this.backoffMs / 1e3)}s...`,
      cls: "autoskill-error"
    });
  }
  render(inbox, tags, proposals) {
    const container = this.containerEl.children[1];
    container.empty();
    const inboxSection = container.createDiv({ cls: "autoskill-section" });
    const inboxHeader = inboxSection.createEl("h4", { text: "\u{1F4E5} Inbox" });
    inboxHeader.toggleClass("autoskill-collapsible", true);
    const inboxBody = inboxSection.createDiv({ cls: "autoskill-section-body" });
    inboxBody.createEl("p", { text: `Pending: ${inbox.pending_files}` });
    if (inbox.processing) {
      inboxBody.createEl("p", { text: `Processing: ${inbox.processing}`, cls: "autoskill-processing" });
    }
    inboxBody.createEl("p", { text: `Total docs: ${inbox.total_documents} (${inbox.total_chunks} chunks)` });
    const tagSection = container.createDiv({ cls: "autoskill-section" });
    tagSection.createEl("h4", { text: `\u{1F3F7}\uFE0F Tags (${tags.length})` });
    const tagBody = tagSection.createDiv({ cls: "autoskill-section-body" });
    if (tags.length === 0) {
      tagBody.createEl("p", { text: "No tags yet", cls: "autoskill-muted" });
    } else {
      const tagList = tagBody.createDiv({ cls: "autoskill-tag-list" });
      for (const tag of tags.slice(0, 50)) {
        const chip = tagList.createEl("span", {
          text: `${tag.tag} (${tag.document_count})`,
          cls: "autoskill-tag-chip"
        });
        chip.addEventListener("click", () => {
        });
      }
    }
    const proposalSection = container.createDiv({ cls: "autoskill-section" });
    const pending = proposals.filter((p) => p.status === "pending");
    proposalSection.createEl("h4", { text: `\u{1F4A1} Proposals (${pending.length} pending)` });
    const proposalBody = proposalSection.createDiv({ cls: "autoskill-section-body" });
    if (pending.length === 0) {
      proposalBody.createEl("p", { text: "No pending proposals", cls: "autoskill-muted" });
    } else {
      for (const prop of pending) {
        const row = proposalBody.createDiv({ cls: "autoskill-proposal-row" });
        row.createEl("strong", { text: prop.name });
        row.createEl("small", { text: ` (${prop.proposal_type}, ${Math.round(prop.confidence * 100)}%)` });
        row.createEl("p", { text: prop.summary, cls: "autoskill-proposal-summary" });
        const actions = row.createDiv({ cls: "autoskill-proposal-actions" });
        const acceptBtn = actions.createEl("button", { text: "Accept", cls: "mod-cta" });
        const rejectBtn = actions.createEl("button", { text: "Reject" });
        acceptBtn.addEventListener("click", async () => {
          await this.plugin.api.reviewProposal(prop.id, true);
          await this.refresh();
        });
        rejectBtn.addEventListener("click", async () => {
          await this.plugin.api.reviewProposal(prop.id, false);
          await this.refresh();
        });
      }
    }
  }
};

// src/search-modal.ts
var import_obsidian4 = require("obsidian");
var SearchModal = class extends import_obsidian4.Modal {
  constructor(app, plugin) {
    super(app);
    this.debounceTimer = null;
    this.plugin = plugin;
  }
  onOpen() {
    const { contentEl } = this;
    contentEl.empty();
    contentEl.createEl("h3", { text: "Search Knowledge Graph" });
    const input = contentEl.createEl("input", {
      type: "text",
      placeholder: "Search...",
      cls: "autoskill-search-input"
    });
    input.style.width = "100%";
    input.style.marginBottom = "12px";
    input.focus();
    this.resultsEl = contentEl.createDiv({ cls: "autoskill-search-results" });
    input.addEventListener("input", () => {
      if (this.debounceTimer) clearTimeout(this.debounceTimer);
      this.debounceTimer = window.setTimeout(async () => {
        const query = input.value.trim();
        if (query.length < 2) {
          this.resultsEl.empty();
          return;
        }
        await this.search(query);
      }, 300);
    });
  }
  async search(query) {
    this.resultsEl.empty();
    try {
      const results = await this.plugin.api.search(query);
      if (results.length === 0) {
        this.resultsEl.createEl("p", { text: "No results found", cls: "autoskill-muted" });
        return;
      }
      for (const result of results) {
        const card = this.resultsEl.createDiv({ cls: "autoskill-result-card" });
        card.createEl("strong", { text: result.title });
        card.createEl("small", { text: ` (${result.source_type}, ${Math.round(result.similarity * 100)}%)` });
        card.createEl("p", { text: result.text.substring(0, 200) + "..." });
        if (result.tags.length > 0) {
          const tagLine = card.createDiv({ cls: "autoskill-tag-list" });
          for (const tag of result.tags) {
            tagLine.createEl("span", { text: tag, cls: "autoskill-tag-chip" });
          }
        }
        card.addEventListener("click", () => {
          const file = this.app.vault.getAbstractFileByPath(result.path);
          if (file) {
            this.app.workspace.openLinkText(result.path, "");
            this.close();
          }
        });
      }
    } catch (e) {
      this.resultsEl.createEl("p", { text: "Search failed \u2014 backend unreachable", cls: "autoskill-error" });
    }
  }
  onClose() {
    this.contentEl.empty();
    if (this.debounceTimer) clearTimeout(this.debounceTimer);
  }
};

// src/main.ts
var AutoSkillPlugin = class extends import_obsidian5.Plugin {
  constructor() {
    super(...arguments);
    this.healthTimer = null;
  }
  async onload() {
    await this.loadSettings();
    this.api = new ApiClient(this.settings.backendUrl);
    this.addSettingTab(new AutoSkillSettingTab(this.app, this));
    this.statusBarItem = this.addStatusBarItem();
    this.statusBarItem.setText("AutoSkill: connecting...");
    this.checkHealth();
    this.healthTimer = window.setInterval(() => this.checkHealth(), 1e4);
    this.registerInterval(this.healthTimer);
    this.registerView(VIEW_TYPE_AUTOSKILL, (leaf) => new AutoSkillSidebarView(leaf, this));
    this.addCommand({
      id: "open-sidebar",
      name: "Open AutoSkill sidebar",
      callback: () => this.activateSidebar()
    });
    this.addCommand({
      id: "search-knowledge",
      name: "Search Knowledge Graph",
      callback: () => new SearchModal(this.app, this).open()
    });
    this.addCommand({
      id: "reindex-current-file",
      name: "Re-index current file",
      callback: async () => {
        const file = this.app.workspace.getActiveFile();
        if (!file) {
          new import_obsidian5.Notice("No active file");
          return;
        }
        try {
          const result = await this.api.reindex(file.path);
          new import_obsidian5.Notice(result.message);
        } catch (e) {
          new import_obsidian5.Notice("Re-index failed \u2014 backend unreachable");
        }
      }
    });
    this.app.workspace.onLayoutReady(() => {
      this.activateSidebar();
    });
  }
  async onunload() {
    this.app.workspace.detachLeavesOfType(VIEW_TYPE_AUTOSKILL);
  }
  async loadSettings() {
    this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
  }
  async saveSettings() {
    await this.saveData(this.settings);
    this.api = new ApiClient(this.settings.backendUrl);
  }
  async checkHealth() {
    try {
      const health = await this.api.health();
      this.statusBarItem.setText(`AutoSkill: ${health.documents} docs`);
    } catch (e) {
      this.statusBarItem.setText("AutoSkill: offline");
    }
  }
  async activateSidebar() {
    const existing = this.app.workspace.getLeavesOfType(VIEW_TYPE_AUTOSKILL);
    if (existing.length > 0) {
      this.app.workspace.revealLeaf(existing[0]);
      return;
    }
    const leaf = this.app.workspace.getRightLeaf(false);
    if (leaf) {
      await leaf.setViewState({ type: VIEW_TYPE_AUTOSKILL, active: true });
      this.app.workspace.revealLeaf(leaf);
    }
  }
};
