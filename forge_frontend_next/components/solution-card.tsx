import { Button } from './ui/button';

export type Solution = {
  id: string;
  number: string;
  name: string;
  image: string;
  description: string;
  actionLabel: string;
};

export function SolutionCard({ solution, onSelect }: { solution: Solution; onSelect: () => void }) {
  return <article className={`solution-card ${solution.id}`}>
    <img className="solution-cover" src={solution.image} alt="" />
    <span className="solution-shade" /><span>{solution.number}</span>
    <h3>NarrativeOS <b>{solution.name}</b></h3>
    <p>{solution.description}</p>
    <Button variant="unstyled" type="button" onClick={onSelect}>{solution.actionLabel} <i>→</i></Button>
  </article>;
}
