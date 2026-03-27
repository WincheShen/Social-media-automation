import fs from "fs";
import path from "path";
import yaml from "js-yaml";
import type { AccountConfig } from "./types";

const CONFIG_DIR = path.resolve(process.cwd(), "../config/identities");

export function listAccountFiles(): string[] {
  if (!fs.existsSync(CONFIG_DIR)) return [];
  return fs
    .readdirSync(CONFIG_DIR)
    .filter((f) => f.endsWith(".yaml") || f.endsWith(".yml"))
    .sort();
}

export function readAccount(accountId: string): AccountConfig | null {
  const filePath = path.join(CONFIG_DIR, `${accountId}.yaml`);
  if (!fs.existsSync(filePath)) return null;
  const raw = fs.readFileSync(filePath, "utf-8");
  const data = yaml.load(raw) as Record<string, unknown>;
  return { account_id: accountId, ...data } as AccountConfig;
}

export function readAllAccounts(): AccountConfig[] {
  return listAccountFiles()
    .map((f) => {
      const id = f.replace(/\.ya?ml$/, "");
      return readAccount(id);
    })
    .filter(Boolean) as AccountConfig[];
}

export function writeAccount(accountId: string, config: Partial<AccountConfig>): void {
  const filePath = path.join(CONFIG_DIR, `${accountId}.yaml`);
  // Read existing to preserve fields not in the update
  const existing = readAccount(accountId) || {};
  const merged = { ...existing, ...config };

  // Remove account_id from YAML (it's the filename)
  const { account_id, ...toWrite } = merged as AccountConfig & { account_id: string };
  void account_id;

  const yamlStr = yaml.dump(toWrite, {
    lineWidth: 120,
    noRefs: true,
    quotingType: '"',
    forceQuotes: false,
  });
  fs.writeFileSync(filePath, yamlStr, "utf-8");
}
