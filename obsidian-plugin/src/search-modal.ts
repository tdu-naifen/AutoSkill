import { Modal, App } from "obsidian";
import type AutoSkillPlugin from "./main";
import type { SearchResult } from "./types";

export class SearchModal extends Modal {
    plugin: AutoSkillPlugin;
    private debounceTimer: number | null = null;
    private resultsEl!: HTMLElement;

    constructor(app: App, plugin: AutoSkillPlugin) {
        super(app);
        this.plugin = plugin;
    }

    onOpen(): void {
        const { contentEl } = this;
        contentEl.empty();
        contentEl.createEl("h3", { text: "Search Knowledge Graph" });

        const input = contentEl.createEl("input", {
            type: "text",
            placeholder: "Search...",
            cls: "autoskill-search-input",
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

    private async search(query: string): Promise<void> {
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
        } catch {
            this.resultsEl.createEl("p", { text: "Search failed — backend unreachable", cls: "autoskill-error" });
        }
    }

    onClose(): void {
        this.contentEl.empty();
        if (this.debounceTimer) clearTimeout(this.debounceTimer);
    }
}
