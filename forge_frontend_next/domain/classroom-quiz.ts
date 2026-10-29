import type { QuizPlan, QuizQuestion } from './quiz';

export type Assignment = { id: string; job_id: string; class_id: string; name: string; class_name: string; status: 'OPEN' | 'CLOSED'; submitted_count: number; quiz_version_id: string; created_at: string };
export type ShareLink = { assignment_id: string; link_id: string; token: string; url: string; reused?: boolean };
export type StudentSession = { id: string; credential: string };
export type StudentQuestion = Pick<QuizQuestion, 'id' | 'type' | 'prompt' | 'options'> & Partial<QuizQuestion>;
export type Attempt = { id: string; assignment_id: string; assignment_name: string; assignment_status: 'OPEN' | 'CLOSED'; display_name: string; status: 'DRAFT' | 'SUBMITTED' | 'VOID'; submitted_at: string | null; quiz: Omit<QuizPlan, 'questions'> & { questions: StudentQuestion[] }; answers: Record<string, { selected_option_id: string; is_correct: boolean }> };
export type Submission = { id: string; display_name: string; submitted_at: string };
export type QuizStatistics = { submitted_count: number; latest_submission: string | null; questions: { id: string; type?: 'single_choice' | 'judgement'; prompt: string; knowledge_point: string; total: number; correct: number; incorrect: number; correct_rate: number | null; options: { id: string; text: string; count: number; rate: number | null; students?: { id: string; name: string }[] }[] }[]; knowledge_points: { name: string; question_ids: string[]; total: number; correct: number; correct_rate: number | null }[] };
export type AnalysisResult = { overview: string; items: { kind: string; text: string; question_ids: string[] }[] };
export type AnalysisSnapshot = { quiz: QuizPlan; statistics: QuizStatistics; attempt_ids: string[] };
export type Analysis = { id: string; status: 'QUEUED' | 'RUNNING' | 'READY' | 'FAILED'; created_at: string; stale: boolean; added_count: number; voided_count: number; error?: string; result: AnalysisResult | null; snapshot: AnalysisSnapshot; previous: { result: AnalysisResult; snapshot: AnalysisSnapshot; created_at: string; stale: boolean; added_count: number; voided_count: number } | null };
