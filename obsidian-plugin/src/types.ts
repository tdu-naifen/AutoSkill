/** Shared types for AutoSkill plugin. */

export interface InboxStatus {
    pending_files: number;
    processing: string | null;
    last_indexed: string | null;
    total_documents: number;
    total_chunks: number;
}

export interface TagInfo {
    tag: string;
    document_count: number;
}

export interface TagDocuments {
    tag: string;
    documents: Array<{
        path: string;
        title: string;
        source_type: string;
    }>;
}

export interface Proposal {
    id: string;
    name: string;
    proposal_type: "behavioral" | "reference";
    summary: string;
    source_path: string;
    confidence: number;
    status: "pending" | "accepted" | "rejected";
    created: string;
}

export interface ProposalDetail extends Proposal {
    source_excerpts: string;
    suggested_trigger: string;
}

export interface SearchResult {
    text: string;
    path: string;
    title: string;
    tags: string[];
    source_type: string;
    similarity: number;
}

export interface HealthStatus {
    status: "ok" | "error";
    chromadb: boolean;
    documents: number;
    version: string;
}
