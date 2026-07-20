import { useState, type FormEvent } from "react";

export type SupportFormLabels = {
  title: string;
  body: string;
  firstName: string;
  email: string;
  question: string;
  submit: string;
  cancel: string;
  privacy: string;
  invalidEmail: string;
};

export function SupportRequestForm({
  labels,
  initialQuestion,
  onSubmit,
  onCancel
}: {
  labels: SupportFormLabels;
  initialQuestion?: string;
  onSubmit: (values: { firstName: string; email: string; question: string }) => Promise<void>;
  onCancel: () => void;
}) {
  const [firstName, setFirstName] = useState("");
  const [email, setEmail] = useState("");
  const [question, setQuestion] = useState(initialQuestion || "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim())) {
      setError(labels.invalidEmail);
      return;
    }
    setSubmitting(true);
    try {
      await onSubmit({ firstName: firstName.trim(), email: email.trim(), question: question.trim() });
    } catch (submissionError) {
      setError(submissionError instanceof Error ? submissionError.message : "The support request could not be sent.");
      setSubmitting(false);
    }
  };

  return (
    <form className="gw-support-form" onSubmit={(event) => void submit(event)}>
      <div className="gw-support-form-heading">
        <strong>{labels.title}</strong>
        <p>{labels.body}</p>
      </div>
      <label>
        <span>{labels.firstName}</span>
        <input value={firstName} onChange={(event) => setFirstName(event.target.value)} maxLength={80} autoComplete="given-name" required />
      </label>
      <label>
        <span>{labels.email}</span>
        <input value={email} onChange={(event) => setEmail(event.target.value)} type="email" maxLength={254} autoComplete="email" required />
      </label>
      <label>
        <span>{labels.question}</span>
        <textarea value={question} onChange={(event) => setQuestion(event.target.value)} rows={4} maxLength={4000} required />
      </label>
      <p className="gw-support-form-privacy">{labels.privacy}</p>
      {error ? <p className="gw-support-form-error" role="alert">{error}</p> : null}
      <div className="gw-support-form-actions">
        <button type="button" className="gw-secondary-button" onClick={onCancel} disabled={submitting}>{labels.cancel}</button>
        <button type="submit" className="gw-primary-button" disabled={submitting}>{submitting ? "..." : labels.submit}</button>
      </div>
    </form>
  );
}
