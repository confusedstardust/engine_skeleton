"use client";

import { useId, useState } from "react";
import { Check, PenLine } from "lucide-react";
import { Button } from "../../components/ui/button";
import { formatAgentChoiceAnswer, type AgentChoiceQuestion, type ClarificationAnswerV2 } from "./agent-choice-protocol";
import styles from "./agent-choice-prompt.module.css";

type Props = {
  choice: AgentChoiceQuestion;
  disabled: boolean;
  onAnswer: (answer: string, structured?: ClarificationAnswerV2) => void;
};

/** End-of-turn choice cards; never executes an option without user input. */
export default function AgentChoicePrompt({ choice, disabled, onAnswer }: Props) {
  const customId = useId();
  const [selected, setSelected] = useState<string[]>([]);
  const [showCustom, setShowCustom] = useState(false);
  const [custom, setCustom] = useState("");
  const unavailable = disabled || (choice.schemaVersion === "2.0" && choice.status !== "pending");

  function submit(ids: string[], freeText = "") {
    if (unavailable || (!ids.length && !freeText.trim())) return;
    const answer = formatAgentChoiceAnswer(choice, ids, freeText);
    if (answer) {
      if (choice.schemaVersion === "2.0" && choice.clarificationId) {
        onAnswer(answer, {
          clarification_id: choice.clarificationId,
          selected_option_ids: ids,
          custom_text: freeText.trim(),
        });
      } else onAnswer(answer);
    }
  }

  return <section className={styles.card} aria-label="选择下一步">
    <p className={styles.question}>{choice.question}</p>
    <div className={styles.options} role="group" aria-label={choice.multiple ? "可多选" : "请选择一项"}>
      {choice.options.map(option => {
        const checked = selected.includes(option.id);
        return <Button key={option.id} variant="unstyled" className={styles.option}
          disabled={unavailable} aria-pressed={choice.multiple ? checked : undefined}
          onClick={() => {
            if (!choice.multiple) { submit([option.id]); return; }
            setSelected(current => current.includes(option.id)
              ? current.filter(id => id !== option.id) : [...current, option.id]);
          }}>
          <span className={[styles.selector, checked ? styles.checked : ""].filter(Boolean).join(" ")}
            aria-hidden="true">{checked ? <Check size={14} strokeWidth={2.5} /> : null}</span>
          <span className={styles.optionText}>
            <strong>{option.label}</strong>
            {option.description ? <small>{option.description}</small> : null}
          </span>
        </Button>;
      })}
      {choice.allowCustom &&
        <Button variant="unstyled"
          className={[styles.option, showCustom ? styles.selectedOther : ""].filter(Boolean).join(" ")}
          disabled={unavailable} aria-expanded={showCustom} onClick={() => setShowCustom(value => !value)}>
          <span className={styles.selector} aria-hidden="true"><PenLine size={14} /></span>
          <span className={styles.optionText}><strong>其他（自己填写）</strong></span>
        </Button>}
    </div>
    {showCustom && choice.allowCustom && <div className={styles.custom}>
      <label htmlFor={customId}>补充你的选择或要求</label>
      <textarea id={customId} value={custom} rows={2} maxLength={2000}
        disabled={unavailable} placeholder="也可以直接描述你希望怎么做…"
        onChange={event => setCustom(event.target.value)}
        onKeyDown={event => {
          if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
            event.preventDefault();
            submit(choice.multiple ? selected : [], custom);
          }
        }} />
    </div>}
    {choice.multiple || showCustom ? <div className={styles.footer}>
      <Button variant="primary" size="sm" disabled={unavailable ||
        (!selected.length && !(showCustom && custom.trim()))}
        onClick={() => submit(choice.multiple ? selected : [], showCustom ? custom : "")}>
        确认选择
      </Button>
    </div> : null}
    {!unavailable && choice.multiple && <p className={styles.hint}>可选择多项后确认</p>}
  </section>;
}
