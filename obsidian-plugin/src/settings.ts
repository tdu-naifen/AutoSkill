import { App, PluginSettingTab, Setting } from "obsidian";
import type AutoSkillPlugin from "./main";

export interface AutoSkillSettings {
    backendUrl: string;
    embeddingModel: string;
    taggingModel: string;
    fastPathThreshold: number;
    maxTags: number;
    pollInterval: number;
}

export const DEFAULT_SETTINGS: AutoSkillSettings = {
    backendUrl: "http://localhost:8420",
    embeddingModel: "nomic-embed-text",
    taggingModel: "gemma-4-26b-a4b-it-4bit",
    fastPathThreshold: 0.9,
    maxTags: 20,
    pollInterval: 30000,
};

export class AutoSkillSettingTab extends PluginSettingTab {
    plugin: AutoSkillPlugin;

    constructor(app: App, plugin: AutoSkillPlugin) {
        super(app, plugin);
        this.plugin = plugin;
    }

    display(): void {
        const { containerEl } = this;
        containerEl.empty();
        containerEl.createEl("h2", { text: "AutoSkill Settings" });

        new Setting(containerEl)
            .setName("Backend URL")
            .setDesc("URL of the AutoSkill Python backend")
            .addText(text => text
                .setPlaceholder("http://localhost:8420")
                .setValue(this.plugin.settings.backendUrl)
                .onChange(async (value) => {
                    this.plugin.settings.backendUrl = value;
                    await this.plugin.saveSettings();
                }));

        new Setting(containerEl)
            .setName("Embedding model")
            .setDesc("Model name for embeddings")
            .addText(text => text
                .setValue(this.plugin.settings.embeddingModel)
                .onChange(async (value) => {
                    this.plugin.settings.embeddingModel = value;
                    await this.plugin.saveSettings();
                }));

        new Setting(containerEl)
            .setName("Tagging model")
            .setDesc("LLM model for auto-tagging")
            .addText(text => text
                .setValue(this.plugin.settings.taggingModel)
                .onChange(async (value) => {
                    this.plugin.settings.taggingModel = value;
                    await this.plugin.saveSettings();
                }));

        new Setting(containerEl)
            .setName("Fast path threshold")
            .setDesc("Similarity threshold for inheriting tags (0.0–1.0)")
            .addText(text => text
                .setValue(String(this.plugin.settings.fastPathThreshold))
                .onChange(async (value) => {
                    const num = parseFloat(value);
                    if (!isNaN(num) && num >= 0 && num <= 1) {
                        this.plugin.settings.fastPathThreshold = num;
                        await this.plugin.saveSettings();
                    }
                }));

        new Setting(containerEl)
            .setName("Max tags per document")
            .setDesc("Maximum number of tags assigned to each document")
            .addText(text => text
                .setValue(String(this.plugin.settings.maxTags))
                .onChange(async (value) => {
                    const num = parseInt(value);
                    if (!isNaN(num) && num > 0) {
                        this.plugin.settings.maxTags = num;
                        await this.plugin.saveSettings();
                    }
                }));

        new Setting(containerEl)
            .setName("Poll interval (ms)")
            .setDesc("How often to check backend status")
            .addText(text => text
                .setValue(String(this.plugin.settings.pollInterval))
                .onChange(async (value) => {
                    const num = parseInt(value);
                    if (!isNaN(num) && num >= 5000) {
                        this.plugin.settings.pollInterval = num;
                        await this.plugin.saveSettings();
                    }
                }));

        // Connection test button
        new Setting(containerEl)
            .setName("Test connection")
            .setDesc("Check if the backend is reachable")
            .addButton(button => button
                .setButtonText("Test")
                .onClick(async () => {
                    try {
                        const health = await this.plugin.api.health();
                        button.setButtonText(`✓ ${health.documents} docs`);
                        setTimeout(() => button.setButtonText("Test"), 3000);
                    } catch {
                        button.setButtonText("✗ Failed");
                        setTimeout(() => button.setButtonText("Test"), 3000);
                    }
                }));
    }
}
