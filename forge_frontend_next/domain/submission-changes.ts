import type { Submission } from './classroom-quiz';

/** Ignore ordering, but detect new, voided and renamed submissions. */
export function submissionKey(rows: Submission[]): string {
  return JSON.stringify(rows.map(row => [row.id, row.display_name, row.submitted_at]).sort((a, b) => a[0].localeCompare(b[0])));
}
