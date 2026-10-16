export type QuizOption = {
  id: string;
  text: string;
};

export type QuizQuestion = {
  id: string;
  type: "single_choice" | "judgement";
  prompt: string;
  options: QuizOption[];
  correct_option_ids: string[];
  explanation: string;
  knowledge_point: string;
  difficulty: "基础" | "进阶" | "挑战";
  teaching_tip: string;
};

export type QuizPlan = {
  title: string;
  introduction: string;
  questions: QuizQuestion[];
};

export type QuizResponse = {
  status: "NOT_GENERATED" | "QUEUED" | "RUNNING" | "READY" | "FAILED";
  error?: string | null;
  quiz?: QuizPlan | null;
  can_manage?: boolean;
};
