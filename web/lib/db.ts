import Database from "better-sqlite3";
import path from "path";
import fs from "fs";
import type { Task, TaskStatus } from "./types";

const DB_DIR = path.resolve(process.cwd(), "../data/state");
const DB_PATH = path.join(DB_DIR, "web_tasks.db");

function getDb(): Database.Database {
  if (!fs.existsSync(DB_DIR)) {
    fs.mkdirSync(DB_DIR, { recursive: true });
  }
  const db = new Database(DB_PATH);
  db.pragma("journal_mode = WAL");
  db.exec(`
    CREATE TABLE IF NOT EXISTS tasks (
      id TEXT PRIMARY KEY,
      account_id TEXT NOT NULL,
      description TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'created',
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      draft_title TEXT,
      draft_content TEXT,
      draft_tags TEXT,
      research_summary TEXT,
      safety_issues TEXT,
      post_url TEXT,
      error TEXT
    )
  `);
  return db;
}

function rowToTask(row: Record<string, unknown>): Task {
  return {
    id: row.id as string,
    account_id: row.account_id as string,
    description: row.description as string,
    status: row.status as TaskStatus,
    created_at: row.created_at as string,
    updated_at: row.updated_at as string,
    draft_title: (row.draft_title as string) || undefined,
    draft_content: (row.draft_content as string) || undefined,
    draft_tags: row.draft_tags ? JSON.parse(row.draft_tags as string) : undefined,
    research_summary: (row.research_summary as string) || undefined,
    safety_issues: row.safety_issues ? JSON.parse(row.safety_issues as string) : undefined,
    post_url: (row.post_url as string) || undefined,
    error: (row.error as string) || undefined,
  };
}

export function listTasks(accountId?: string): Task[] {
  const db = getDb();
  const rows = accountId
    ? db.prepare("SELECT * FROM tasks WHERE account_id = ? ORDER BY created_at DESC").all(accountId)
    : db.prepare("SELECT * FROM tasks ORDER BY created_at DESC").all();
  db.close();
  return (rows as Record<string, unknown>[]).map(rowToTask);
}

export function getTask(id: string): Task | null {
  const db = getDb();
  const row = db.prepare("SELECT * FROM tasks WHERE id = ?").get(id) as Record<string, unknown> | undefined;
  db.close();
  return row ? rowToTask(row) : null;
}

export function createTask(accountId: string, description: string): Task {
  const db = getDb();
  const id = crypto.randomUUID();
  const now = new Date().toISOString();
  db.prepare(
    "INSERT INTO tasks (id, account_id, description, status, created_at, updated_at) VALUES (?, ?, ?, 'created', ?, ?)"
  ).run(id, accountId, description, now, now);
  db.close();
  return {
    id,
    account_id: accountId,
    description,
    status: "created",
    created_at: now,
    updated_at: now,
  };
}

export function updateTask(id: string, fields: Partial<Task>): Task | null {
  const db = getDb();
  const existing = db.prepare("SELECT * FROM tasks WHERE id = ?").get(id) as Record<string, unknown> | undefined;
  if (!existing) {
    db.close();
    return null;
  }

  const updates: string[] = [];
  const values: unknown[] = [];

  for (const [key, value] of Object.entries(fields)) {
    if (key === "id" || key === "created_at") continue;
    const dbValue =
      key === "draft_tags" || key === "safety_issues"
        ? JSON.stringify(value)
        : value;
    updates.push(`${key} = ?`);
    values.push(dbValue);
  }

  updates.push("updated_at = ?");
  values.push(new Date().toISOString());
  values.push(id);

  db.prepare(`UPDATE tasks SET ${updates.join(", ")} WHERE id = ?`).run(...values);
  const updated = db.prepare("SELECT * FROM tasks WHERE id = ?").get(id) as Record<string, unknown>;
  db.close();
  return rowToTask(updated);
}

export function deleteTask(id: string): boolean {
  const db = getDb();
  const result = db.prepare("DELETE FROM tasks WHERE id = ?").run(id);
  db.close();
  return result.changes > 0;
}
