import Database from "better-sqlite3";
import path from "path";
import fs from "fs";

const DB_DIR = path.resolve(process.cwd(), "../data/state");
const DB_PATH = path.join(DB_DIR, "web_tasks.db");

function migrate() {
  if (!fs.existsSync(DB_PATH)) {
    console.log("Database does not exist yet, will be created on first use.");
    return;
  }

  const db = new Database(DB_PATH);
  
  // Check which columns are missing and add them
  const tableInfo = db.pragma("table_info(tasks)") as Array<{ name: string }>;
  const columnNames = tableInfo.map((col) => col.name);
  
  const requiredColumns = [
    { name: "research_data", type: "TEXT" },
    { name: "image_gen_prompt", type: "TEXT" },
    { name: "generated_images", type: "TEXT" },
  ];
  
  let migrated = false;
  for (const col of requiredColumns) {
    if (!columnNames.includes(col.name)) {
      console.log(`Adding ${col.name} column...`);
      db.exec(`ALTER TABLE tasks ADD COLUMN ${col.name} ${col.type}`);
      migrated = true;
    }
  }
  
  if (migrated) {
    console.log("✓ Migration complete");
  } else {
    console.log("✓ Database already up to date");
  }
  
  db.close();
}

migrate();
