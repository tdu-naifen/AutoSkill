import { Modal, App } from "obsidian";
import type AutoSkillPlugin from "./main";
import type { ProposalDetail } from "./types";

export class ProposalDetailModal extends Modal {
    plugin: AutoSkillPlugin;
    proposalId: string;

    constructor(app: App, plugin: AutoSkillPlugin, proposalId: string) {
        super(app);
        this.plugin = plugin;
        this.proposalId = proposalId;
    }

    async onOpen(): Promise<void> {
        const { contentEl } = this;
        contentEl.empty();
        contentEl.createEl("p", { text: "Loading..." });

        try {
            const detail = await this.plugin.api.getProposalDetail(this.proposalId);
            contentEl.empty();
            this.renderDetail(detail);
        } catch {
            contentEl.empty();
            contentEl.createEl("p", { text: "Failed to load proposal", cls: "autoskill-error" });
        }
    }

    private renderDetail(detail: ProposalDetail): void {
        const { contentEl } = this;

        contentEl.createEl("h2", { text: detail.name });
        contentEl.createEl("p", { text: `Type: ${detail.proposal_type} | Confidence: ${Math.round(detail.confidence * 100)}%` });
        contentEl.createEl("p", { text: `Source: ${detail.source_path}` });

        contentEl.createEl("h4", { text: "Summary" });
        contentEl.createEl("p", { text: detail.summary });

        contentEl.createEl("h4", { text: "Source Excerpts" });
        const pre = contentEl.createEl("pre");
        pre.createEl("code", { text: detail.source_excerpts });

        contentEl.createEl("h4", { text: "Suggested Trigger" });
        contentEl.createEl("p", { text: detail.suggested_trigger });

        const actions = contentEl.createDiv({ cls: "autoskill-proposal-actions" });
        const acceptBtn = actions.createEl("button", { text: "Accept & Generate Skill", cls: "mod-cta" });
        const rejectBtn = actions.createEl("button", { text: "Reject" });

        acceptBtn.addEventListener("click", async () => {
            await this.plugin.api.reviewProposal(detail.id, true);
            this.close();
        });
        rejectBtn.addEventListener("click", async () => {
            await this.plugin.api.reviewProposal(detail.id, false);
            this.close();
        });
    }

    onClose(): void {
        this.contentEl.empty();
    }
}
