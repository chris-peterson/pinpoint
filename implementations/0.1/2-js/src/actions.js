export function logAction(db, verb, fileId, detail = {}) {
  db.prepare(
    "INSERT INTO actions (verb, file_id, detail) VALUES (?, ?, ?)",
  ).run(verb, fileId, JSON.stringify(detail));
}
