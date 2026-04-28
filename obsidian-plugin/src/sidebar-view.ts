import { ItemView, WorkspaceLeaf } from "obsidian";
import type AutoSkillPlugin from "./main";
import type { InboxStatus, TagInfo, Proposal } from "./types";

export const VIEW_TYPE_AUTOSKILL = "autoskill-sidebar";

export class AutoSkillSidebarView extends ItemView {
    plugin: AutoSkillPlugin;
    private pollTimer: number | null = null;
    private backoffMs: number;
    private failCount = 0;

    constructor(leaf: WorkspaceLeaf, plugin: AutoSkillPlugin) {
        super(leaf);
        this.plugin = plugin;
        this.backoffMs = plugin.settings.pollInterval;
    }

    getViewType(): string { return VIEW_TYPE_AUTOSKILL; }
    getDisplayText(): string { return "AutoSkill"; }
    getIcon(): string { return "brain"; }

    async onOpen(): Promise<void> {
        this.renderLoading();
        await this.refresh();
        this.startPolling();
    }

    async onClose(): Promise<void> {
        this.stopPolling();
    }

    private startPolling(): void {
        this.stopPolling();
        this.pollTimer = window.setInterval(() => this.refresh(), this.backoffMs);
    }

    private stopPolling(): void {
        if (this.pollTimer !== null) {
            window.clearInterval(this.pollTimer);
            this.pollTimer = null;
        }
    }

    private renderLoading(): void {
        const container = this.containerEl.children[1];
        container.empty();
        container.createEl("p", { text: "Connecting to backend...", cls: "autoskill-loading" });
    }

    async refresh(): Promise<void> {
        try {
            const [inbox, tags, proposals] = await Promise.all([
                this.plugin.api.getInboxStatus(),
                this.plugin.api.getTags(),
                this.plugin.api.getProposals(),
            ]);
            this.failCount = 0;
            this.backoffMs = this.plugin.settings.pollInterval;
            this.render(inbox, tags, proposals);
        } catch {
            this.failCount++;
            if (this.failCount >= 3) {
                this.backoffMs = Math.min(this.backoffMs * 2, 30000);
                this.stopPolling();
                this.startPolling();
            }
            this.renderError();
        }
    }

    private renderError(): void {
        const container = this.containerEl.children[1];
        container.empty();
        container.createEl("p", {
            text: `Backend unreachable. Retrying in ${Math.round(this.backoffMs / 1000)}s...`,
            cls: "autoskill-error",
        });
    }

    private render(inbox: InboxStatus, tags: TagInfo[], proposals: Proposal[]): void {
        const container = this.containerEl.children[1];
        container.empty();

        // --- Inbox Section ---
        const inboxSection = container.createDiv({ cls: "autoskill-section" });
        const inboxHeader = inboxSection.createEl("h4", { text: "📥 Inbox" });
        inboxHeader.toggleClass("autoskill-collapsible", true);
        const inboxBody = inboxSection.createDiv({ cls: "autoskill-section-body" });
        inboxBody.createEl("p", { text: `Pending: ${inbox.pending_files}` });
        if (inbox.processing) {
            inboxBody.createEl("p", { text: `Processing: ${inbox.processing}`, cls: "autoskill-processing" });
        }
        inboxBody.createEl("p", { text: `Total docs: ${inbox.total_documents} (${inbox.total_chunks} chunks)` });

        // --- Tags Section ---
        const tagSection = container.createDiv({ cls: "autoskill-section" });
        tagSection.createEl("h4", { text: `🏷️ Tags (${tags.length})` });
        const tagBody = tagSection.createDiv({ cls: "autoskill-section-body" });
        if (tags.length === 0) {
            tagBody.createEl("p", { text: "No tags yet", cls: "autoskill-muted" });
        } else {
            const tagList = tagBody.createDiv({ cls: "autoskill-tag-list" });
            for (const tag of tags.slice(0, 50)) {
                const chip = tagList.createEl("span", {
                    text: `${tag.tag} (${tag.document_count})`,
                    cls: "autoskill-tag-chip",
                });
                chip.addEventListener("click", () => {
                    // TODO: open tag detail or filter
                });
            }
        }

        // --- Proposals Section ---
        const proposalSection = container.createDiv({ cls: "autoskill-section" });
        const pending = proposals.filter(p => p.status === "pending");
        proposalSection.createEl("h4", { text: `💡 Proposals (${pending.length} pending)` });
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
}
