import { Plugin, Notice } from "obsidian";
import { AutoSkillSettingTab, AutoSkillSettings, DEFAULT_SETTINGS } from "./settings";
import { ApiClient } from "./api-client";
import { AutoSkillSidebarView, VIEW_TYPE_AUTOSKILL } from "./sidebar-view";
import { SearchModal } from "./search-modal";

export default class AutoSkillPlugin extends Plugin {
    settings: AutoSkillSettings;
    api: ApiClient;
    private statusBarItem: HTMLElement;
    private healthTimer: number | null = null;

    async onload(): Promise<void> {
        await this.loadSettings();
        this.api = new ApiClient(this.settings.backendUrl);

        // Settings tab
        this.addSettingTab(new AutoSkillSettingTab(this.app, this));

        // Status bar
        this.statusBarItem = this.addStatusBarItem();
        this.statusBarItem.setText("AutoSkill: connecting...");

        // Health check every 10s — recovers quickly after backend restart
        this.checkHealth();
        this.healthTimer = window.setInterval(() => this.checkHealth(), 10000);
        this.registerInterval(this.healthTimer);

        // Sidebar view
        this.registerView(VIEW_TYPE_AUTOSKILL, (leaf) => new AutoSkillSidebarView(leaf, this));

        // Commands
        this.addCommand({
            id: "open-sidebar",
            name: "Open AutoSkill sidebar",
            callback: () => this.activateSidebar(),
        });

        this.addCommand({
            id: "search-knowledge",
            name: "Search Knowledge Graph",
            callback: () => new SearchModal(this.app, this).open(),
        });

        this.addCommand({
            id: "reindex-current-file",
            name: "Re-index current file",
            callback: async () => {
                const file = this.app.workspace.getActiveFile();
                if (!file) {
                    new Notice("No active file");
                    return;
                }
                try {
                    const result = await this.api.reindex(file.path);
                    new Notice(result.message);
                } catch {
                    new Notice("Re-index failed — backend unreachable");
                }
            },
        });

        // Auto-open sidebar on startup
        this.app.workspace.onLayoutReady(() => {
            this.activateSidebar();
        });
    }

    async onunload(): Promise<void> {
        this.app.workspace.detachLeavesOfType(VIEW_TYPE_AUTOSKILL);
    }

    async loadSettings(): Promise<void> {
        this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
    }

    async saveSettings(): Promise<void> {
        await this.saveData(this.settings);
        this.api = new ApiClient(this.settings.backendUrl);
    }

    private async checkHealth(): Promise<void> {
        try {
            const health = await this.api.health();
            this.statusBarItem.setText(`AutoSkill: ${health.documents} docs`);
        } catch {
            this.statusBarItem.setText("AutoSkill: offline");
        }
    }

    private async activateSidebar(): Promise<void> {
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
}
