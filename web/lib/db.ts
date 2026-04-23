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
      research_data TEXT,
      safety_issues TEXT,
      image_gen_prompt TEXT,
      generated_images TEXT,
      post_url TEXT,
      error TEXT
    )
  `);

  // Idempotent migrations: ensure all expected columns exist on pre-existing tables
  const existingCols = new Set(
    (db.prepare("PRAGMA table_info(tasks)").all() as { name: string }[]).map(
      (r) => r.name
    )
  );
  const requiredCols: Record<string, string> = {
    draft_title: "TEXT",
    draft_content: "TEXT",
    draft_tags: "TEXT",
    research_summary: "TEXT",
    research_data: "TEXT",
    safety_issues: "TEXT",
    image_gen_prompt: "TEXT",
    generated_images: "TEXT",
    post_url: "TEXT",
    error: "TEXT",
  };
  for (const [col, type] of Object.entries(requiredCols)) {
    if (!existingCols.has(col)) {
      db.exec(`ALTER TABLE tasks ADD COLUMN ${col} ${type}`);
    }
  }

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
    research_data: row.research_data ? JSON.parse(row.research_data as string) : undefined,
    safety_issues: row.safety_issues ? JSON.parse(row.safety_issues as string) : undefined,
    image_gen_prompt: (row.image_gen_prompt as string) || undefined,
    generated_images: row.generated_images ? JSON.parse(row.generated_images as string) : undefined,
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
      key === "draft_tags" || key === "safety_issues" || key === "research_data" || key === "generated_images"
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

// ---------------------------------------------------------------------------
// Dashboard Statistics
// ---------------------------------------------------------------------------

export interface DashboardStats {
  totalTasks: number;
  todayTasks: number;
  reviewing: number;
  published: number;
  failed: number;
  running: number;
  byAccount: Record<string, {
    total: number;
    published: number;
    reviewing: number;
  }>;
  recentTrend: {
    date: string;
    count: number;
    published: number;
  }[];
}

export function getDashboardStats(): DashboardStats {
  const db = getDb();
  
  // Basic counts
  const totalTasks = (db.prepare("SELECT COUNT(*) as count FROM tasks").get() as { count: number }).count;
  
  const today = new Date().toISOString().split("T")[0];
  const todayTasks = (db.prepare("SELECT COUNT(*) as count FROM tasks WHERE created_at LIKE ?").get(`${today}%`) as { count: number }).count;
  
  const reviewing = (db.prepare("SELECT COUNT(*) as count FROM tasks WHERE status = 'reviewing'").get() as { count: number }).count;
  const published = (db.prepare("SELECT COUNT(*) as count FROM tasks WHERE status = 'published'").get() as { count: number }).count;
  const failed = (db.prepare("SELECT COUNT(*) as count FROM tasks WHERE status = 'failed'").get() as { count: number }).count;
  const running = (db.prepare("SELECT COUNT(*) as count FROM tasks WHERE status = 'running'").get() as { count: number }).count;
  
  // By account
  const accountRows = db.prepare(`
    SELECT 
      account_id,
      COUNT(*) as total,
      SUM(CASE WHEN status = 'published' THEN 1 ELSE 0 END) as published,
      SUM(CASE WHEN status = 'reviewing' THEN 1 ELSE 0 END) as reviewing
    FROM tasks
    GROUP BY account_id
  `).all() as { account_id: string; total: number; published: number; reviewing: number }[];
  
  const byAccount: Record<string, { total: number; published: number; reviewing: number }> = {};
  for (const row of accountRows) {
    byAccount[row.account_id] = {
      total: row.total,
      published: row.published,
      reviewing: row.reviewing,
    };
  }
  
  // Recent 7-day trend
  const trendRows = db.prepare(`
    SELECT 
      DATE(created_at) as date,
      COUNT(*) as count,
      SUM(CASE WHEN status = 'published' THEN 1 ELSE 0 END) as published
    FROM tasks
    WHERE created_at >= DATE('now', '-7 days')
    GROUP BY DATE(created_at)
    ORDER BY date DESC
  `).all() as { date: string; count: number; published: number }[];
  
  db.close();
  
  return {
    totalTasks,
    todayTasks,
    reviewing,
    published,
    failed,
    running,
    byAccount,
    recentTrend: trendRows,
  };
}

export interface EngagementStats {
  totalLikes: number;
  totalComments: number;
  totalSearches: number;
  todayLikes: number;
  todayComments: number;
  byAccount: Record<string, {
    likes: number;
    comments: number;
  }>;
}

export function getEngagementStats(): EngagementStats {
  const engagementDbPath = path.join(DB_DIR, "engagement_history.db");
  
  // Return empty stats if engagement DB doesn't exist
  if (!fs.existsSync(engagementDbPath)) {
    return {
      totalLikes: 0,
      totalComments: 0,
      totalSearches: 0,
      todayLikes: 0,
      todayComments: 0,
      byAccount: {},
    };
  }
  
  const db = new Database(engagementDbPath);
  
  const today = new Date().toISOString().split("T")[0];
  
  const totalLikes = (db.prepare("SELECT COUNT(*) as count FROM engagement_history WHERE action_type = 'like'").get() as { count: number }).count;
  const totalComments = (db.prepare("SELECT COUNT(*) as count FROM engagement_history WHERE action_type = 'comment'").get() as { count: number }).count;
  const totalSearches = (db.prepare("SELECT COUNT(*) as count FROM engagement_history WHERE action_type = 'search'").get() as { count: number }).count;
  
  const todayLikes = (db.prepare("SELECT COUNT(*) as count FROM engagement_history WHERE action_type = 'like' AND created_at LIKE ?").get(`${today}%`) as { count: number }).count;
  const todayComments = (db.prepare("SELECT COUNT(*) as count FROM engagement_history WHERE action_type = 'comment' AND created_at LIKE ?").get(`${today}%`) as { count: number }).count;
  
  const accountRows = db.prepare(`
    SELECT 
      account_id,
      SUM(CASE WHEN action_type = 'like' THEN 1 ELSE 0 END) as likes,
      SUM(CASE WHEN action_type = 'comment' THEN 1 ELSE 0 END) as comments
    FROM engagement_history
    GROUP BY account_id
  `).all() as { account_id: string; likes: number; comments: number }[];
  
  const byAccount: Record<string, { likes: number; comments: number }> = {};
  for (const row of accountRows) {
    byAccount[row.account_id] = {
      likes: row.likes,
      comments: row.comments,
    };
  }
  
  db.close();
  
  return {
    totalLikes,
    totalComments,
    totalSearches,
    todayLikes,
    todayComments,
    byAccount,
  };
}
