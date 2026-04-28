import { requestUrl, RequestUrlParam } from "obsidian";
import type { InboxStatus, TagInfo, TagDocuments, Proposal, ProposalDetail, SearchResult, HealthStatus } from "./types";

export class ApiClient {
    constructor(private baseUrl: string) {}

    private async request<T>(path: string, method = "GET", body?: unknown): Promise<T> {
        const params: RequestUrlParam = {
            url: `${this.baseUrl}${path}`,
            method,
            headers: { "Content-Type": "application/json" },
        };
        if (body) {
            params.body = JSON.stringify(body);
        }
        const resp = await requestUrl(params);
        return resp.json as T;
    }

    async health(): Promise<HealthStatus> {
        return this.request("/api/health");
    }

    async getInboxStatus(): Promise<InboxStatus> {
        return this.request("/api/inbox");
    }

    async getTags(prefix = ""): Promise<TagInfo[]> {
        const q = prefix ? `?prefix=${encodeURIComponent(prefix)}` : "";
        return this.request(`/api/tags${q}`);
    }

    async getTagDocuments(tag: string): Promise<TagDocuments> {
        return this.request(`/api/tags/${encodeURIComponent(tag)}`);
    }

    async getProposals(): Promise<Proposal[]> {
        return this.request("/api/proposals");
    }

    async getProposalDetail(id: string): Promise<ProposalDetail> {
        return this.request(`/api/proposals/${encodeURIComponent(id)}`);
    }

    async reviewProposal(id: string, accepted: boolean): Promise<{ message: string }> {
        return this.request(`/api/proposals/${encodeURIComponent(id)}/review`, "POST", { accepted });
    }

    async search(query: string, n = 10): Promise<SearchResult[]> {
        return this.request(`/api/search?q=${encodeURIComponent(query)}&n=${n}`);
    }

    async reindex(path: string): Promise<{ message: string }> {
        return this.request("/api/reindex", "POST", { path });
    }
}
