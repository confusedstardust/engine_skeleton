export type Job = {
  id: string;
  status: string;
  phase?: string | null;
  error?: string | null;
  title?: string;
  source_material?: string;
  draft_revision?: number;
  published_revision?: number;
  build_state?: "NONE" | "DRAFT" | "CURRENT" | "STALE" | "BUILDING" | "FAILED";
  dirty_scopes?: string[];
  has_published_build?: boolean;
  created_at?: string;
  updated_at?: string;
  artifacts?: Record<string, string>;
  options?: {
    classroom_topic?: string;
    voice_enabled?: boolean;
    generate_assets?: boolean;
    generation_mode?: string;
    [key: string]: unknown;
  };
};

export type NodeArtifact = {
  key: string;
  phase: string;
  phase_status: string;
  title: string;
  description: string;
  path: string;
  content_type: "json" | "text";
  exists: boolean;
  content: string | null;
};

export type NodesResponse = {
  job: Job;
  nodes: NodeArtifact[];
  scenes: NodeArtifact[];
};

export type SceneConnectionReport = {
  status: "passed" | "failed" | "skipped";
  reason?: string;
  expected_scene_count?: number;
  reachable: string[];
  fixes: Array<{ code: string; scene_file: string; target?: string }>;
  errors: Array<{ code: string; scene_file?: string; message: string }>;
};
