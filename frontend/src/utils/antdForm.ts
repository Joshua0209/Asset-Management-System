// AntD's Form.validateFields() rejects with a structured object on
// failure: { values, errorFields: [...], outOfDate }. A bare `catch {}`
// also swallows real programmer errors (a thrown ReferenceError, a
// rejected unrelated promise, etc.), which is the kind of silent
// failure we want to avoid. Use this helper to confirm an error is
// actually an AntD validation rejection before discarding it.
export function isAntdValidationError(err: unknown): boolean {
  return (
    typeof err === "object" &&
    err !== null &&
    "errorFields" in err &&
    Array.isArray((err as { errorFields?: unknown }).errorFields)
  );
}
